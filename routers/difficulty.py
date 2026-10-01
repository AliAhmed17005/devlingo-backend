import random
import os
import datetime
import pickle
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from firebase_admin import firestore
import pandas as pd
from sklearn.linear_model import LogisticRegression

router = APIRouter()

# Lazy Firestore Client resolver to prevent startup crashes when offline
db_client = None
def get_db():
    global db_client
    if db_client is None:
        try:
            db_client = firestore.client()
        except ValueError:
            raise HTTPException(
                status_code=503, 
                detail="Firebase Admin SDK is not initialized. Please configure serviceAccount.json or GOOGLE_CREDS_JSON."
            )
    return db_client

class DifficultyUpdateReq(BaseModel):
    user_id: str
    problem_id: str
    topic_id: str
    correct: bool
    time_taken: float
    hour_of_day: int

@router.get("/")
async def test_difficulty():
    """
    Test endpoint for Difficulty router
    """
    return {
        "status": "success",
        "message": "Difficulty router is active"
    }

@router.post("/update")
async def update_difficulty(req: DifficultyUpdateReq):
    try:
        db = get_db()
        # 1. Get current user skill rating
        user_ref = db.collection("users").document(req.user_id)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        skill_ratings = user_data.get("skillRatings", {})
        old_skill = float(skill_ratings.get(req.topic_id, 1000.0))

        # 2. Get problem Elo rating
        problem_ref = db.collection("problems").document(req.problem_id)
        problem_doc = problem_ref.get()
        problem_data = problem_doc.to_dict() if problem_doc.exists else {}
        old_difficulty = float(problem_data.get("eloRating", 1000.0))

        # 3. Compute expected success probability
        expected = 1.0 / (1.0 + 10.0 ** ((old_difficulty - old_skill) / 400.0))

        # 4. K factor
        K = 32.0
        actual = 1.0 if req.correct else 0.0

        # 5. new_skill
        new_skill = old_skill + K * (actual - expected)

        # 6. new_difficulty
        new_difficulty = old_difficulty + K * (expected - actual)

        # 7. Update Firestore user doc
        user_ref.set({"skillRatings": {req.topic_id: new_skill}}, merge=True)

        # 8. Update Firestore problem doc
        problem_ref.set({"eloRating": new_difficulty}, merge=True)

        # 9. Compute recentAccuracy and daysSincePractice from prior sessions
        sessions_ref = user_ref.collection("sessions")
        prior_query = sessions_ref.where("topicId", "==", req.topic_id).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(5)
        prior_docs = list(prior_query.stream())

        now = datetime.datetime.now(datetime.timezone.utc)

        # daysSincePractice calculation
        if prior_docs:
            last_session_time = prior_docs[0].get("timestamp")
            if last_session_time:
                # Ensure timezone aware
                if last_session_time.tzinfo is None:
                    last_session_time = last_session_time.replace(tzinfo=datetime.timezone.utc)
                delta = now - last_session_time
                days_since_practice = max(0.0, delta.total_seconds() / 86400.0)
            else:
                days_since_practice = 30.0
        else:
            days_since_practice = 30.0

        # recentAccuracy calculation (including current session)
        past_correct_count = 1 if req.correct else 0
        total_sessions_count = 1
        for doc in prior_docs[:4]:
            total_sessions_count += 1
            doc_data = doc.to_dict()
            passed = doc_data.get("passed")
            if passed is None:
                passed = (doc_data.get("score", 0) == 100)
            if passed:
                past_correct_count += 1
        recent_accuracy = (past_correct_count / total_sessions_count) * 100.0

        # Log new session
        session_data = {
            "problemId": req.problem_id,
            "topicId": req.topic_id,
            "score": 100 if req.correct else 0,
            "passed": req.correct,
            "timeTaken": req.time_taken,
            "skillAtTime": old_skill,
            "problemDifficulty": old_difficulty,
            "expectedSuccess": expected,
            "hourOfDay": req.hour_of_day,
            "recentAccuracy": recent_accuracy,
            "daysSincePractice": days_since_practice,
            "timestamp": now
        }
        sessions_ref.add(session_data)

        # 12. Return result
        return {
            "new_skill": new_skill,
            "new_difficulty": new_difficulty,
            "expected_success": expected,
            "skill_change": new_skill - old_skill,
            "was_correct": req.correct
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating difficulty rating: {str(e)}")

@router.get("/next-problem/{user_id}/{topic_id}")
async def get_next_problem(user_id: str, topic_id: str):
    try:
        db = get_db()
        # 1. Get user skill rating
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        skill_ratings = user_data.get("skillRatings", {})
        user_skill = float(skill_ratings.get(topic_id, 1000.0))

        # 2. Get all problems for this topic
        problems_ref = db.collection("problems")
        problems_query = problems_ref.where("topicId", "==", topic_id)
        problems_docs = list(problems_query.stream())

        # Determine descriptive difficulty level based on ELO
        if user_skill < 800:
            diff_level = "easy"
        elif user_skill < 1200:
            diff_level = "medium"
        elif user_skill < 1600:
            diff_level = "hard"
        else:
            diff_level = "very_hard"

        # 40% chance to generate a completely new question, or 100% if static pool is empty
        import random
        if not problems_docs or random.random() < 0.4:
            try:
                from routers.content_engine import generate_dynamic_question
                new_prob = generate_dynamic_question(topic_id, diff_level)
                return new_prob
            except Exception as ge:
                print(f"Dynamic content engine generation failed, using static pool fallback: {ge}")
                if not problems_docs:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to generate dynamic question and no static problems are available."
                    )

        # 3. Compute expected success probability for each problem
        flow_candidates = []
        easiest_prob = None
        highest_success_prob = -1.0

        for doc in problems_docs:
            p_data = doc.to_dict()
            p_data["id"] = doc.id
            problem_diff = float(p_data.get("eloRating", 1000.0))

            prob = 1.0 / (1.0 + 10.0 ** ((problem_diff - user_skill) / 400.0))
            p_data["success_probability"] = prob

            # Filter to flow zone [0.55, 0.85]
            if 0.55 <= prob <= 0.85:
                flow_candidates.append(p_data)

            # Track easiest problem (highest success probability / lowest difficulty)
            if prob > highest_success_prob:
                highest_success_prob = prob
                easiest_prob = p_data

        # 5. Decide next problem
        if flow_candidates:
            selected_problem = random.choice(flow_candidates)
        else:
            selected_problem = easiest_prob

        return selected_problem

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding next problem: {str(e)}")

@router.get("/skill-ratings/{user_id}")
async def get_skill_ratings(user_id: str):
    try:
        db = get_db()
        # Get user skill ratings
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        skill_ratings = user_data.get("skillRatings", {})

        # Fetch courses to map topic IDs to titles
        courses_ref = db.collection("courses")
        courses_docs = list(courses_ref.stream())

        topic_map = {}
        for doc in courses_docs:
            c_data = doc.to_dict()
            c_title = c_data.get("title", "Unknown Course")
            for topic in c_data.get("topics", []):
                t_id = topic.get("id")
                t_title = topic.get("title", "Unknown Topic")
                display_name = f"{c_title}: {t_title}"
                if t_id in topic_map:
                    topic_map[t_id].append(display_name)
                else:
                    topic_map[t_id] = [display_name]

        ratings_list = []
        for t_id, rating in skill_ratings.items():
            if t_id in topic_map:
                name = " / ".join(topic_map[t_id])
            else:
                name = f"Topic {t_id}"
            ratings_list.append({
                "topic_id": t_id,
                "rating": rating,
                "name": name
            })

        return {"ratings": ratings_list}

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching skill ratings: {str(e)}")

@router.post("/train-model")
async def train_model():
    try:
        db = get_db()
        # 1. Pull all session logs from Firestore using Collection Group
        sessions_ref = db.collection_group("sessions")
        docs = list(sessions_ref.stream())
        
        samples = []
        for doc in docs:
            data = doc.to_dict()
            passed = data.get("passed")
            if passed is None:
                passed = (data.get("score", 0) == 100)
            
            skill = data.get("skillAtTime")
            difficulty = data.get("problemDifficulty")
            hour_of_day = data.get("hourOfDay")
            recent_accuracy = data.get("recentAccuracy")
            days_since_practice = data.get("daysSincePractice")

            if (skill is not None and 
                difficulty is not None and 
                hour_of_day is not None and 
                recent_accuracy is not None and 
                days_since_practice is not None):
                samples.append({
                    "skill": float(skill),
                    "difficulty": float(difficulty),
                    "hour_of_day": int(hour_of_day),
                    "recent_accuracy": float(recent_accuracy),
                    "days_since_practice": float(days_since_practice),
                    "passed": 1 if passed else 0
                })

        # 2. Check if enough samples exist
        if len(samples) <= 50:
            return {
                "status": "need more data",
                "current_samples": len(samples)
            }

        # 3. Build DataFrame and train model
        df = pd.DataFrame(samples)
        X = df[["skill", "difficulty", "hour_of_day", "recent_accuracy", "days_since_practice"]]
        y = df["passed"]

        model = LogisticRegression(max_iter=1000)
        model.fit(X, y)
        accuracy = float(model.score(X, y))

        coefs = model.coef_[0]
        features = ["skill", "difficulty", "hour_of_day", "recent_accuracy", "days_since_practice"]
        feature_importance = {features[i]: float(coefs[i]) for i in range(len(features))}

        # 4. Save model
        os.makedirs("models", exist_ok=True)
        model_path = os.path.join("models", "success_predictor.pkl")
        with open(model_path, "wb") as f:
            pickle.dump(model, f)

        return {
            "status": "success",
            "accuracy": accuracy,
            "feature_importance": feature_importance,
            "training_samples": len(samples)
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error training model: {str(e)}")

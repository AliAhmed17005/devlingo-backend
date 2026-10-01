from fastapi import APIRouter
from pydantic import BaseModel
from firebase_admin import firestore
import math, random

router = APIRouter(prefix="/difficulty")
db = firestore.client()
K  = 32

class Attempt(BaseModel):
    user_id:    str
    problem_id: str
    topic_id:   str
    correct:    bool
    time_taken: int

def elo_update(skill, difficulty, correct):
    expected      = 1 / (1 + math.pow(10, (difficulty - skill) / 400))
    actual        = 1 if correct else 0
    new_skill     = round(skill      + K * (actual   - expected), 1)
    new_difficulty= round(difficulty + K * (expected - actual),   1)
    return new_skill, new_difficulty, round(expected, 3)

@router.post("/update")
def update_elo(a: Attempt):
    user_ref  = db.collection("users").document(a.user_id)
    prob_ref  = db.collection("problems").document(a.problem_id)
    user_data = user_ref.get().to_dict() or {}
    prob_data = prob_ref.get().to_dict() or {}
    skill      = user_data.get("skillRatings", {}).get(a.topic_id, 1000)
    difficulty = prob_data.get("eloRating", 1000)
    new_skill, new_diff, expected = elo_update(skill, difficulty, a.correct)
    user_ref.update({f"skillRatings.{a.topic_id}": new_skill})
    prob_ref.update({"eloRating": new_diff})
    user_ref.collection("sessions").add({
        "topicId":    a.topic_id,
        "problemId":  a.problem_id,
        "score":      100 if a.correct else 0,
        "passed":     a.correct,
        "skillAtTime":skill,
        "timeTaken":  a.time_taken,
        "timestamp":  firestore.SERVER_TIMESTAMP
    })
    return {
        "new_skill":       new_skill,
        "skill_change":    round(new_skill - skill, 1),
        "expected_success":expected,
        "was_correct":     a.correct
    }

@router.get("/next-problem/{user_id}/{topic_id}")
def next_problem(user_id: str, topic_id: str):
    user_data  = db.collection("users").document(user_id).get().to_dict() or {}
    skill      = user_data.get("skillRatings", {}).get(topic_id, 1000)
    problems   = db.collection("problems").where("topicId","==",topic_id).stream()
    candidates = []
    fallback   = None
    for p in problems:
        d    = p.to_dict()
        diff = d.get("eloRating", 1000)
        prob = 1 / (1 + math.pow(10, (diff - skill) / 400))
        d["id"]           = p.id
        d["prob_success"] = round(prob * 100)
        if 0.55 <= prob <= 0.85:
            candidates.append(d)
        if fallback is None:
            fallback = d
    return random.choice(candidates) if candidates else (fallback or {"error": "no problems found"})

@router.get("/next-problem/{user_id}/{topic_id}/harder")
def next_problem_harder(user_id: str, topic_id: str):
    user_data  = db.collection("users").document(user_id).get().to_dict() or {}
    skill      = user_data.get("skillRatings", {}).get(topic_id, 1000)
    problems   = db.collection("problems").where("topicId","==",topic_id).stream()
    candidates = []
    fallback   = None
    for p in problems:
        d    = p.to_dict()
        diff = d.get("eloRating", 1000)
        prob = 1 / (1 + math.pow(10, (diff - skill) / 400))
        d["id"]           = p.id
        d["prob_success"] = round(prob * 100)
        if 0.30 <= prob <= 0.55:
            candidates.append(d)
        if fallback is None:
            fallback = d
    return random.choice(candidates) if candidates else (fallback or {"error": "no problems found"})

@router.get("/next-problem/{user_id}/{topic_id}/easier")
def next_problem_easier(user_id: str, topic_id: str):
    user_data  = db.collection("users").document(user_id).get().to_dict() or {}
    skill      = user_data.get("skillRatings", {}).get(topic_id, 1000)
    problems   = db.collection("problems").where("topicId","==",topic_id).stream()
    candidates = []
    fallback   = None
    for p in problems:
        d    = p.to_dict()
        diff = d.get("eloRating", 1000)
        prob = 1 / (1 + math.pow(10, (diff - skill) / 400))
        d["id"]           = p.id
        d["prob_success"] = round(prob * 100)
        if 0.85 <= prob <= 0.98:
            candidates.append(d)
        if fallback is None:
            fallback = d
    return random.choice(candidates) if candidates else (fallback or {"error": "no problems found"})

@router.get("/skills/{user_id}")
def get_skills(user_id: str):
    d = db.collection("users").document(user_id).get().to_dict() or {}
    return {"skill_ratings": d.get("skillRatings", {})}

@router.get("/skill-history/{user_id}/{topic_id}")
def skill_history(user_id: str, topic_id: str):
    sessions = db.collection("users").document(user_id)\
        .collection("sessions")\
        .where("topicId","==",topic_id)\
        .order_by("timestamp", direction=firestore.Query.ASCENDING)\
        .limit(20).stream()
    history = []
    for s in sessions:
        d = s.to_dict()
        history.append({
            "skill":      d.get("skillAtTime", 1000),
            "score":      d.get("score", 0),
            "passed":     d.get("passed", False),
            "timeTaken":  d.get("timeTaken", 0)
        })
    return {"history": history}

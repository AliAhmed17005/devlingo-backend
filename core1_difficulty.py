from typing import Optional
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

def resolve_user_skill(user_data: dict, topic_id: str):
    skill_ratings = user_data.get("skillRatings", {})
    if topic_id in skill_ratings and skill_ratings[topic_id] is not None:
        return float(skill_ratings[topic_id])
    
    # If not yet rated for this topic, look at currentLevel set by prior topic score
    user_level = user_data.get("currentLevel", "easy")
    default_elos = {"easy": 900.0, "medium": 1200.0, "hard": 1500.0}
    return default_elos.get(user_level, 900.0)

def skill_to_level(skill: float) -> str:
    if skill >= 1350:
        return "hard"
    elif skill >= 1050:
        return "medium"
    return "easy"

@router.post("/update")
def update_elo(a: Attempt):
    user_ref  = db.collection("users").document(a.user_id)
    prob_ref  = db.collection("problems").document(a.problem_id)
    user_data = user_ref.get().to_dict() or {}
    prob_data = prob_ref.get().to_dict() or {}
    skill      = resolve_user_skill(user_data, a.topic_id)
    difficulty = prob_data.get("eloRating", 1000)
    new_skill, new_diff, expected = elo_update(skill, difficulty, a.correct)
    
    # Update skill and currentLevel based on new skill
    updated_level = skill_to_level(new_skill)
    user_ref.update({
        f"skillRatings.{a.topic_id}": new_skill,
        "currentLevel": updated_level
    })
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
        "was_correct":     a.correct,
        "currentLevel":    updated_level
    }

@router.get("/next-problem/{user_id}/{topic_id}")
def next_problem(user_id: str, topic_id: str, exclude: Optional[str] = None):
    exclude_set = set([x.strip() for x in exclude.split(",") if x.strip()]) if exclude else set()
    user_data  = db.collection("users").document(user_id).get().to_dict() or {}
    skill      = resolve_user_skill(user_data, topic_id)
    target_diff = skill_to_level(skill)
    
    problems   = db.collection("problems").where("topicId","==",topic_id).stream()
    tier_unseen = []
    flow_unseen = []
    unseen_all  = []
    tier_seen   = []
    seen_all    = []
    
    for p in problems:
        d    = p.to_dict()
        diff = d.get("eloRating", 1000)
        prob = 1 / (1 + math.pow(10, (diff - skill) / 400))
        d["id"]           = p.id
        d["prob_success"] = round(prob * 100)
        
        is_seen = p.id in exclude_set
        matches_tier = d.get("difficulty") == target_diff
        in_flow = 0.40 <= prob <= 0.88
        
        if is_seen:
            seen_all.append(d)
            if matches_tier:
                tier_seen.append(d)
        else:
            unseen_all.append(d)
            if matches_tier:
                tier_unseen.append(d)
            if in_flow:
                flow_unseen.append(d)

    # Priority 1: Unseen question matching the target difficulty tier
    if tier_unseen:
        return random.choice(tier_unseen)
    # Priority 2: Unseen question in the adaptive flow zone
    if flow_unseen:
        return random.choice(flow_unseen)
    # Priority 3: Any unseen question for this topic
    if unseen_all:
        return random.choice(unseen_all)
    # Fallback to seen questions if user exhausted the topic pool
    if tier_seen:
        return random.choice(tier_seen)
    if seen_all:
        return random.choice(seen_all)
    return {"error": "no problems found"}

@router.get("/next-problem/{user_id}/{topic_id}/harder")
def next_problem_harder(user_id: str, topic_id: str, exclude: Optional[str] = None):
    exclude_set = set([x.strip() for x in exclude.split(",") if x.strip()]) if exclude else set()
    user_data  = db.collection("users").document(user_id).get().to_dict() or {}
    skill      = resolve_user_skill(user_data, topic_id)
    problems   = db.collection("problems").where("topicId","==",topic_id).stream()
    candidates = []
    unseen_all = []
    seen_all   = []
    for p in problems:
        d    = p.to_dict()
        diff = d.get("eloRating", 1000)
        prob = 1 / (1 + math.pow(10, (diff - skill) / 400))
        d["id"]           = p.id
        d["prob_success"] = round(prob * 100)
        if p.id in exclude_set:
            seen_all.append(d)
            continue
        unseen_all.append(d)
        if 0.25 <= prob <= 0.55 or d.get("difficulty") == "hard":
            candidates.append(d)
    if candidates:
        return random.choice(candidates)
    if unseen_all:
        return random.choice(unseen_all)
    return random.choice(seen_all) if seen_all else {"error": "no problems found"}

@router.get("/next-problem/{user_id}/{topic_id}/easier")
def next_problem_easier(user_id: str, topic_id: str, exclude: Optional[str] = None):
    exclude_set = set([x.strip() for x in exclude.split(",") if x.strip()]) if exclude else set()
    user_data  = db.collection("users").document(user_id).get().to_dict() or {}
    skill      = resolve_user_skill(user_data, topic_id)
    problems   = db.collection("problems").where("topicId","==",topic_id).stream()
    candidates = []
    unseen_all = []
    seen_all   = []
    for p in problems:
        d    = p.to_dict()
        diff = d.get("eloRating", 1000)
        prob = 1 / (1 + math.pow(10, (diff - skill) / 400))
        d["id"]           = p.id
        d["prob_success"] = round(prob * 100)
        if p.id in exclude_set:
            seen_all.append(d)
            continue
        unseen_all.append(d)
        if 0.70 <= prob <= 0.98 or d.get("difficulty") == "easy":
            candidates.append(d)
    if candidates:
        return random.choice(candidates)
    if unseen_all:
        return random.choice(unseen_all)
    return random.choice(seen_all) if seen_all else {"error": "no problems found"}

@router.get("/skills/{user_id}")
@router.get("/skill-ratings/{user_id}")
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

from fastapi import APIRouter
from firebase_admin import firestore
import math

router = APIRouter(prefix="/matching")
db     = firestore.client()
TOPICS = ["variables","loops","functions","lists","dictionaries","files","oop"]

def cosine_similarity(a, b):
    dot   = sum(ai * bi for ai, bi in zip(a, b))
    mag_a = math.sqrt(sum(ai**2 for ai in a))
    mag_b = math.sqrt(sum(bi**2 for bi in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0

def build_vector(skill_ratings: dict):
    return [max(0, min(1, (skill_ratings.get(t, 1000) - 800) / 400))
            for t in TOPICS]

@router.get("/find-match/{user_id}")
def find_match(user_id: str):
    try:
        all_users = db.collection("users").stream()
        users = []
        for u in all_users:
            data = u.to_dict()
            users.append({
                "uid":  u.id,
                "name": data.get("name", "User"),
                "vec":  build_vector(data.get("skillRatings", {}))
            })
    except Exception:
        return {"error": "Could not fetch users"}

    me = next((u for u in users if u["uid"] == user_id), None)
    if not me:        return {"error": "User not found"}
    if len(users) < 2:return {"error": "Need at least 2 users in the system"}

    gap_vec    = [1 - v for v in me["vec"]]
    best_comp  = None; best_cs  = -1
    best_buddy = None; best_bs  = -1

    for u in users:
        if u["uid"] == user_id:
            continue
        cs = cosine_similarity(gap_vec, u["vec"])
        bs = cosine_similarity(me["vec"], u["vec"])
        if cs > best_cs:  best_cs  = cs;  best_comp  = u
        if bs > best_bs:  best_bs  = bs;  best_buddy = u

    weak       = [TOPICS[i] for i, v in enumerate(me["vec"]) if v < 0.4][:3]
    comp_strong= ([TOPICS[i] for i, v in enumerate(best_comp["vec"]) if v > 0.6][:3]
                  if best_comp else [])

    return {
        "complement": {
            "user_id":    best_comp["uid"],
            "name":       best_comp["name"],
            "match_score":round(best_cs * 100),
            "strong_in":  comp_strong
        } if best_comp else None,
        "study_buddy": {
            "user_id":   best_buddy["uid"],
            "name":      best_buddy["name"],
            "similarity":round(best_bs * 100)
        } if best_buddy else None,
        "your_weak_topics": weak,
        "total_users":      len(users)
    }

@router.get("/leaderboard")
def leaderboard():
    try:
        users = db.collection("users")\
            .order_by("totalPoints", direction=firestore.Query.DESCENDING)\
            .limit(10).stream()
        board = []
        for i, u in enumerate(users, 1):
            d = u.to_dict()
            board.append({
                "rank":         i,
                "name":         d.get("name","User"),
                "totalPoints":  d.get("totalPoints", 0),
                "currentStreak":d.get("currentStreak", 0),
                "level":        d.get("currentLevel","easy")
            })
        return {"leaderboard": board}
    except Exception:
        return {"leaderboard": []}

from fastapi import APIRouter
from pydantic import BaseModel
from firebase_admin import firestore
from datetime import datetime, timedelta
from typing import List

router = APIRouter(prefix="/scheduling")
db     = firestore.client()

class GoalRequest(BaseModel):
    user_id:         str
    goal_title:      str
    deadline:        str
    topics:          List[str]
    available_hours: float = 1.5
    calendar_events: List[dict] = []

class EventRequest(BaseModel):
    user_id:    str
    title:      str
    event_date: str
    event_type: str = "competition"
    notes:      str = ""

@router.post("/create-plan")
def create_plan(req: GoalRequest):
    try:
        deadline  = datetime.fromisoformat(req.deadline)
    except Exception:
        return {"error": "Invalid deadline format. Use YYYY-MM-DD"}
    today     = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_left = (deadline - today).days
    if days_left <= 0:
        return {"error": "Deadline has already passed"}
    if not req.topics:
        return {"error": "Please select at least one topic"}

    sessions_per_topic = max(1, days_left // len(req.topics))
    schedule   = []
    current    = today + timedelta(days=1)
    topic_idx  = 0
    topic_count= 0

    while current < deadline and topic_idx < len(req.topics):
        if current.weekday() != 6:
            end_hour = 9 + int(req.available_hours)
            schedule.append({
                "date":      current.strftime("%Y-%m-%d"),
                "topic":     req.topics[topic_idx],
                "title":     f"DevLingo: {req.topics[topic_idx]}",
                "start":     current.strftime("%Y-%m-%d") + "T09:00:00",
                "end":       current.strftime("%Y-%m-%d") + f"T{end_hour:02d}:00:00",
                "completed": False
            })
            topic_count += 1
            if topic_count >= sessions_per_topic:
                topic_idx  += 1
                topic_count = 0
        current += timedelta(days=1)

    db.collection("users").document(req.user_id)\
        .collection("studyPlans").add({
            "goal_title":      req.goal_title,
            "deadline":        req.deadline,
            "topics":          req.topics,
            "available_hours": req.available_hours,
            "sessions_created":len(schedule),
            "schedule":        schedule,
            "created_at":      firestore.SERVER_TIMESTAMP,
            "timestamp":       firestore.SERVER_TIMESTAMP
        })

    return {
        "sessions_created": len(schedule),
        "days_remaining":   days_left,
        "schedule":         schedule,
        "status":           "success"
    }

@router.post("/add-event")
def add_event(req: EventRequest):
    db.collection("users").document(req.user_id)\
        .collection("calendarEvents").add({
            "title":      req.title,
            "event_date": req.event_date,
            "event_type": req.event_type,
            "notes":      req.notes,
            "timestamp":  firestore.SERVER_TIMESTAMP
        })
    return {"status": "success", "event": req.title, "date": req.event_date}

@router.get("/plans/{user_id}")
def get_plans(user_id: str):
    try:
        plans = db.collection("users").document(user_id)\
            .collection("studyPlans")\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)\
            .limit(5).stream()
        return {"plans": [p.to_dict() for p in plans]}
    except Exception:
        return {"plans": []}

@router.get("/events/{user_id}")
def get_events(user_id: str):
    try:
        events = db.collection("users").document(user_id)\
            .collection("calendarEvents")\
            .order_by("event_date")\
            .stream()
        return {"events": [e.to_dict() for e in events]}
    except Exception:
        return {"events": []}

@router.post("/mark-complete/{user_id}/{plan_id}/{session_date}")
def mark_session_complete(user_id: str, plan_id: str, session_date: str):
    plan_ref = db.collection("users").document(user_id)\
        .collection("studyPlans").document(plan_id)
    plan_data = plan_ref.get().to_dict()
    if not plan_data:
        return {"error": "Plan not found"}
    schedule = plan_data.get("schedule", [])
    for session in schedule:
        if session.get("date") == session_date:
            session["completed"] = True
    plan_ref.update({"schedule": schedule})
    return {"status": "marked complete"}

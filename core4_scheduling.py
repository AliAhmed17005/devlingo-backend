from fastapi import APIRouter
from pydantic import BaseModel
from firebase_admin import firestore
from datetime import datetime, timedelta
from typing import List, Optional

router = APIRouter(prefix="/scheduling")
db     = firestore.client()

class GoalRequest(BaseModel):
    user_id:               str
    goal_title:            str
    deadline:              str
    topics:                List[str]
    topic_ids:             Optional[List[str]] = []
    available_hours:       float = 1.5
    questions_per_session: Optional[int] = None
    calendar_events:       List[dict] = []
    plan_mode:             str = "custom"  # "adaptive" or "custom"
    course_id:             Optional[str] = "python-basics"
    set_as_active:         Optional[bool] = True

class SetActivePlanRequest(BaseModel):
    user_id: str
    plan_id: str

class EventRequest(BaseModel):
    user_id:    str
    title:      str
    event_date: str
    event_type: str = "competition"
    notes:      str = ""

def calculate_questions_per_session(hours: float, explicit_q: Optional[int] = None) -> int:
    if explicit_q and explicit_q > 0:
        return int(explicit_q)
    hrs = float(hours)
    if hrs <= 0.6:   # ~30 mins: 10 to 15 questions
        return 12
    elif hrs <= 0.9: # ~45 mins
        return 16
    elif hrs <= 1.2: # ~1 hour: 20 to 25 questions
        return 22
    elif hrs <= 1.7: # ~1.5 hours
        return 30
    else:            # ~2+ hours
        return min(50, max(10, int(round(hrs * 20))))

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

    user_doc = {}
    try:
        snap = db.collection("users").document(req.user_id).get()
        if snap.exists:
            user_doc = snap.to_dict() or {}
    except Exception:
        pass
    skill_ratings = user_doc.get("skillRatings", {})

    def get_topic_elo(t_identifier: str) -> float:
        clean_id = t_identifier.strip().lower()
        for k, v in skill_ratings.items():
            if k.strip().lower() == clean_id:
                try:
                    return float(v)
                except Exception:
                    pass
        norm_t = "".join(c for c in clean_id if c.isalnum())
        for k, v in skill_ratings.items():
            norm_k = "".join(c for c in k.strip().lower() if c.isalnum())
            if norm_k == norm_t or norm_k in norm_t or norm_t in norm_k:
                try:
                    return float(v)
                except Exception:
                    pass
        return 1000.0

    def get_difficulty(elo: float) -> str:
        if elo < 900:
            return "Easy"
        elif elo <= 1100:
            return "Medium"
        else:
            return "Hard"

    def get_pace(elo: float, days: int, num_topics: int) -> str:
        ratio = days / max(1, num_topics)
        if elo < 950 or ratio < 2:
            return "Intensive Pace"
        elif elo <= 1100:
            return "Steady Pace"
        else:
            return "Accelerated Pace"

    active_topics = list(req.topics)
    if req.plan_mode == "adaptive":
        active_topics.sort(key=lambda t: get_topic_elo(t))

    questions_count = calculate_questions_per_session(req.available_hours, req.questions_per_session)

    sessions_per_topic = max(1, days_left // len(active_topics))
    schedule    = []
    current     = today + timedelta(days=1)
    topic_idx   = 0
    topic_count = 0

    while current < deadline and topic_idx < len(active_topics):
        if current.weekday() != 6:  # Skip Sundays for rest
            end_hour = 9 + int(req.available_hours)
            t_curr = active_topics[topic_idx]
            t_elo  = round(get_topic_elo(t_curr), 1)
            t_diff = get_difficulty(t_elo)
            t_pace = get_pace(t_elo, days_left, len(active_topics))

            target_count = sessions_per_topic
            if req.plan_mode == "adaptive" and t_elo < 990:
                target_count = min(sessions_per_topic + 1, 4)

            focus_label = "Priority Focus (Weak Topic)" if (req.plan_mode == "adaptive" and t_elo < 1000) else "Targeted Mastery"

            schedule.append({
                "date":                  current.strftime("%Y-%m-%d"),
                "topic":                 t_curr,
                "title":                 f"DevLingo: {t_curr}",
                "start":                 current.strftime("%Y-%m-%d") + "T09:00:00",
                "end":                   current.strftime("%Y-%m-%d") + f"T{end_hour:02d}:00:00",
                "completed":             False,
                "elo":                   t_elo,
                "difficulty":            t_diff,
                "pace":                  t_pace,
                "plan_mode":             req.plan_mode,
                "course_id":             req.course_id or "python-basics",
                "questions_per_session": questions_count,
                "focus":                 focus_label
            })
            topic_count += 1
            if topic_count >= target_count:
                topic_idx  += 1
                topic_count = 0
        current += timedelta(days=1)

    plan_doc = {
        "goal_title":            req.goal_title,
        "deadline":              req.deadline,
        "topics":                req.topics,
        "topic_ids":             req.topic_ids or [],
        "available_hours":       req.available_hours,
        "questions_per_session": questions_count,
        "plan_mode":             req.plan_mode,
        "course_id":             req.course_id or "python-basics",
        "sessions_created":      len(schedule),
        "schedule":              schedule,
        "created_at":            firestore.SERVER_TIMESTAMP,
        "timestamp":             firestore.SERVER_TIMESTAMP
    }

    doc_ref = db.collection("users").document(req.user_id).collection("studyPlans").add(plan_doc)
    plan_id = doc_ref[1].id if isinstance(doc_ref, tuple) else getattr(doc_ref, 'id', None)

    active_goal_payload = {
        "id":                    plan_id,
        "goal_title":            req.goal_title,
        "deadline":              req.deadline,
        "plan_mode":             req.plan_mode,
        "course_id":             req.course_id or "python-basics",
        "selected_topics":       req.topic_ids if req.topic_ids else req.topics,
        "selected_topic_titles": req.topics,
        "available_hours":       req.available_hours,
        "questions_per_session": questions_count,
        "sessions_created":      len(schedule),
        "activated_at":          datetime.now().isoformat()
    }

    if req.set_as_active:
        try:
            db.collection("users").document(req.user_id).set({"activeGoalPlan": active_goal_payload}, merge=True)
        except Exception as e:
            print("Failed to set activeGoalPlan in user doc:", e)

    return {
        "id":                    plan_id,
        "goal_title":            req.goal_title,
        "plan_mode":             req.plan_mode,
        "course_id":             req.course_id or "python-basics",
        "sessions_created":      len(schedule),
        "days_remaining":        days_left,
        "questions_per_session": questions_count,
        "active_goal_plan":      active_goal_payload,
        "schedule":              schedule,
        "status":                "success"
    }

@router.post("/set-active-plan")
def set_active_plan(req: SetActivePlanRequest):
    try:
        plan_ref = db.collection("users").document(req.user_id).collection("studyPlans").document(req.plan_id)
        plan_snap = plan_ref.get()
        if not plan_snap.exists:
            return {"error": "Plan not found"}
        plan_data = plan_snap.to_dict()
        q_count = plan_data.get("questions_per_session") or calculate_questions_per_session(plan_data.get("available_hours", 1.5))
        active_goal_payload = {
            "id":                    req.plan_id,
            "goal_title":            plan_data.get("goal_title", "Study Plan"),
            "deadline":              plan_data.get("deadline", ""),
            "plan_mode":             plan_data.get("plan_mode", "custom"),
            "course_id":             plan_data.get("course_id", "python-basics"),
            "selected_topics":       plan_data.get("topic_ids") or plan_data.get("topics", []),
            "selected_topic_titles": plan_data.get("topics", []),
            "available_hours":       plan_data.get("available_hours", 1.5),
            "questions_per_session": q_count,
            "sessions_created":      plan_data.get("sessions_created", len(plan_data.get("schedule", []))),
            "activated_at":          datetime.now().isoformat()
        }
        db.collection("users").document(req.user_id).set({"activeGoalPlan": active_goal_payload}, merge=True)
        return {"status": "success", "activeGoalPlan": active_goal_payload}
    except Exception as e:
        return {"error": str(e)}

@router.post("/drop-active-plan/{user_id}")
def drop_active_plan(user_id: str):
    try:
        db.collection("users").document(user_id).update({"activeGoalPlan": firestore.DELETE_FIELD})
        return {"status": "success", "message": "Goal plan dropped successfully"}
    except Exception as e:
        return {"error": str(e)}

@router.delete("/delete-plan/{user_id}/{plan_id}")
def delete_plan(user_id: str, plan_id: str):
    try:
        db.collection("users").document(user_id).collection("studyPlans").document(plan_id).delete()
        user_snap = db.collection("users").document(user_id).get()
        if user_snap.exists:
            user_doc = user_snap.to_dict() or {}
            if user_doc.get("activeGoalPlan", {}).get("id") == plan_id:
                db.collection("users").document(user_id).update({"activeGoalPlan": firestore.DELETE_FIELD})
        return {"status": "success", "message": "Plan deleted"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/add-event")
def add_event(req: EventRequest):
    db.collection("users").document(req.user_id).collection("calendarEvents").add({
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
        plans = db.collection("users").document(user_id).collection("studyPlans").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
        return {"plans": [p.to_dict() for p in plans]}
    except Exception:
        return {"plans": []}

@router.get("/events/{user_id}")
def get_events(user_id: str):
    try:
        events = db.collection("users").document(user_id).collection("calendarEvents").order_by("event_date").stream()
        return {"events": [e.to_dict() for e in events]}
    except Exception:
        return {"events": []}

@router.post("/mark-complete/{user_id}/{plan_id}/{session_date}")
def mark_session_complete(user_id: str, plan_id: str, session_date: str):
    plan_ref = db.collection("users").document(user_id).collection("studyPlans").document(plan_id)
    plan_data = plan_ref.get().to_dict()
    if not plan_data:
        return {"error": "Plan not found"}
    schedule = plan_data.get("schedule", [])
    for session in schedule:
        if session.get("date") == session_date:
            session["completed"] = True
    plan_ref.update({"schedule": schedule})
    return {"status": "marked complete"}

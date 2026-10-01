from fastapi import APIRouter
from pydantic import BaseModel
from firebase_admin import firestore
from typing import List
import google.generativeai as genai
import os

router = APIRouter(prefix="/agent")
db     = firestore.client()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
llm = genai.GenerativeModel("gemini-1.5-flash")

SENTIMENT_SCORES = {
    "confident":  1.0,
    "neutral":    0.5,
    "confused":   0.25,
    "frustrated": 0.1
}

class StateRequest(BaseModel):
    user_id:         str
    messages:        List[str]
    retries:         int
    time_taken:      int
    recent_accuracy: float

class ChatRequest(BaseModel):
    user_id: str
    message: str
    topic:   str
    level:   str
    score:   int

@router.post("/classify-state")
def classify_state(req: StateRequest):
    retry_penalty = min(req.retries * 0.1, 0.4)
    pace_score    = max(0, 1.0 - (req.time_taken / 300))
    recent_text   = " | ".join(req.messages[-3:])

    try:
        raw = llm.generate_content(
            f"Classify this student message as ONE word only.\n"
            f"Options: confident, neutral, frustrated, confused\n"
            f"Message: {recent_text}\n"
            f"Reply with one word only:"
        ).text.strip().lower()
        raw = raw.replace(".", "").replace(",", "").split()[0]
        sentiment = raw if raw in SENTIMENT_SCORES else "neutral"
    except Exception:
        sentiment = "neutral"

    sentiment_score = SENTIMENT_SCORES[sentiment]

    confidence = max(0, min(1,
        0.35 * req.recent_accuracy +
        0.30 * sentiment_score     +
        0.20 * pace_score          -
        0.15 * retry_penalty
    ))
    confidence = round(confidence, 3)

    if confidence < 0.35:
        action  = "decrease_difficulty"
        message = "Let us slow down and try an easier problem."
    elif confidence > 0.72:
        action  = "increase_difficulty"
        message = "Great work -- ready for a harder challenge!"
    else:
        action  = "maintain"
        message = None

    db.collection("stateLog").add({
        "userId":     req.user_id,
        "sentiment":  sentiment,
        "confidence": confidence,
        "action":     action,
        "signals": {
            "accuracy":      req.recent_accuracy,
            "pace":          round(pace_score, 2),
            "retry_penalty": round(retry_penalty, 2)
        },
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    return {
        "sentiment":  sentiment,
        "confidence": confidence,
        "action":     action,
        "message":    message,
        "signals": {
            "accuracy":      req.recent_accuracy,
            "pace_score":    round(pace_score, 2),
            "retry_penalty": round(retry_penalty, 2)
        }
    }

@router.post("/chat")
def chat(req: ChatRequest):
    try:
        reply = llm.generate_content(
            f"You are Aria, a Python tutor for DevLingo learning platform.\n"
            f"Student level: {req.level}\n"
            f"Current topic: {req.topic}\n"
            f"Last score: {req.score}%\n\n"
            f"STRICT RULES you must always follow:\n"
            f"1. NEVER write Python code, syntax, or solutions for the student\n"
            f"2. NEVER reveal the answer or expected output\n"
            f"3. NEVER complete the student code even partially\n"
            f"4. You MAY explain concepts in plain English\n"
            f"5. You MAY give real-world analogies\n"
            f"6. You MAY ask guiding questions to help them think\n"
            f"7. You MAY explain error messages without fixing them\n"
            f"8. If asked for code say exactly: I cannot write code for you but let me explain the concept so you can figure it out!\n"
            f"9. Keep response under 80 words\n"
            f"10. Be warm, encouraging, and Socratic\n\n"
            f"Student message: {req.message}\n"
            f"Your response:"
        ).text.strip()
        return {"reply": reply}
    except Exception as e:
        return {"reply": "I am having a connection issue. Please try again in a moment."}

@router.get("/log/{user_id}")
def get_log(user_id: str):
    try:
        logs = db.collection("stateLog")\
            .where("userId","==",user_id)\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)\
            .limit(10).stream()
        return {"log": [l.to_dict() for l in logs]}
    except Exception:
        return {"log": []}

@router.get("/mood-chart/{user_id}")
def mood_chart(user_id: str):
    try:
        logs = db.collection("stateLog")\
            .where("userId","==",user_id)\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)\
            .limit(30).stream()
        entries = []
        for l in logs:
            d = l.to_dict()
            entries.append({
                "sentiment":  d.get("sentiment","neutral"),
                "confidence": d.get("confidence", 0.5),
                "action":     d.get("action","maintain")
            })
        return {"entries": list(reversed(entries))}
    except Exception:
        return {"entries": []}

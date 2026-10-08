from fastapi import APIRouter
from pydantic import BaseModel
from firebase_admin import firestore
from typing import List
import google.generativeai as genai
import os

router = APIRouter(prefix="/agent")
db = firestore.client()

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    llm = genai.GenerativeModel("gemini-1.5-flash")
    GEMINI_AVAILABLE = True
    print(f"[Core 2] Gemini configured successfully")
else:
    GEMINI_AVAILABLE = False
    print("[Core 2] WARNING: GEMINI_API_KEY not set — chatbot will use fallback")

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

def _generate_with_gemini(prompt_text: str) -> str:
    # Try gemini-1.5-flash first, then newer active models if 1.5 is deprecated (404)
    models_to_try = ["gemini-1.5-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    last_err = None
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name)
            resp = m.generate_content(prompt_text)
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            last_err = e
            err_msg = str(e).lower()
            if "404" in err_msg or "not found" in err_msg or "no longer available" in err_msg:
                continue
            raise e
    if last_err:
        raise last_err
    raise RuntimeError("No response from Gemini models")

@router.post("/classify-state")
def classify_state(req: StateRequest):
    retry_penalty = min(req.retries * 0.1, 0.4)
    pace_score    = max(0, 1.0 - (req.time_taken / 300))
    recent_text   = " | ".join(req.messages[-3:])

    if GEMINI_AVAILABLE:
        try:
            prompt = (
                f"Classify this student message as ONE word only.\n"
                f"Choose from: confident, neutral, frustrated, confused\n"
                f"Message: {recent_text}\n"
                f"Reply with one word only, nothing else:"
            )
            raw = _generate_with_gemini(prompt).lower()
            raw = raw.replace(".", "").replace(",", "").replace("!", "").split()[0]
            sentiment = raw if raw in SENTIMENT_SCORES else "neutral"
        except Exception as e:
            print(f"[Core 2] Gemini sentiment error: {e}")
            sentiment = "neutral"
    else:
        words = recent_text.lower()
        if any(w in words for w in ["dont get","dont understand","confused","lost","stuck","help"]):
            sentiment = "confused"
        elif any(w in words for w in ["hate","why","nothing","worst","broken","stupid"]):
            sentiment = "frustrated"
        elif any(w in words for w in ["got it","understand","easy","nice","great","perfect"]):
            sentiment = "confident"
        else:
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
        message = "Great work — ready for a harder challenge!"
    else:
        action  = "maintain"
        message = None

    try:
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
    except Exception as e:
        print(f"[Core 2] Firestore write error: {e}")

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
    print(f"[Core 2] Chat request — topic:{req.topic} level:{req.level} gemini:{GEMINI_AVAILABLE}")

    if GEMINI_AVAILABLE:
        try:
            prompt = f"""You are Aria, a Python tutor for DevLingo learning platform.
Student level: {req.level}
Current topic: {req.topic}
Last score: {req.score}%

STRICT RULES you must always follow without exception:
1. NEVER write Python code, syntax, or code solutions for the student
2. NEVER reveal the expected output or the answer
3. NEVER complete or show the student's code even partially
4. You MAY explain concepts clearly in plain English
5. You MAY use real-world analogies to explain ideas
6. You MAY ask Socratic guiding questions
7. You MAY explain what an error message means without fixing it
8. If student asks for code or syntax say exactly:
   I cannot write code for you, but let me explain the concept so you can figure it out!
9. Keep your response under 80 words
10. Be warm, encouraging, and patient

Student message: {req.message}

Your response (remember: NO code, under 80 words):"""

            reply = _generate_with_gemini(prompt)
            print(f"[Core 2] Gemini responded: {reply[:50]}...")
            return {"reply": reply, "source": "gemini"}

        except Exception as e:
            print(f"[Core 2] Gemini chat error: {e}")
            return {
                "reply": f"I am having a connection issue right now. "
                         f"For {req.topic}, try thinking about what the concept "
                         f"does in real life before writing any code. "
                         f"What do you think it means?",
                "source": "fallback",
                "error": str(e)
            }
    else:
        return {
            "reply": "Gemini API key is not configured. Please add GEMINI_API_KEY to your .env file.",
            "source": "no_key"
        }

@router.get("/log/{user_id}")
@router.get("/state-log/{user_id}")
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

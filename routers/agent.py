import os
import datetime
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from firebase_admin import firestore
from openai import OpenAI, AsyncOpenAI

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

# Initialize OpenAI clients
# Note: OpenAI client automatically reads OPENAI_API_KEY from environment variables
openai_api_key = os.getenv("OPENAI_API_KEY")

try:
    if openai_api_key:
        client = OpenAI(api_key=openai_api_key)
        aclient = AsyncOpenAI(api_key=openai_api_key)
    else:
        client = None
        aclient = None
        print("Warning: OPENAI_API_KEY is not set. Sentiment classification will fallback to neutral.")
except Exception as e:
    client = None
    aclient = None
    print(f"Error initializing OpenAI clients: {e}")

class ClassifyStateReq(BaseModel):
    user_id: str
    messages: List[str]
    retries: int
    time_taken: int
    recent_accuracy: float

class LabelDataReq(BaseModel):
    texts: List[str]

def classify_sentiment(messages: List[str]) -> tuple[str, float]:
    sentiment_map = {"confident": 1.0, "neutral": 0.5, "confused": 0.25, "frustrated": 0.1}
    
    if not messages:
        return "neutral", 0.5
        
    last_messages = messages[-3:]
    user_content = "\n".join(last_messages)
    
    if not client:
        print("OpenAI client not initialized. Falling back to neutral.")
        return "neutral", 0.5
        
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system", 
                    "content": "You are analyzing a student's learning session. Classify their emotional state from their messages as exactly one of: confident, neutral, frustrated, confused. Reply with the single word only."
                },
                {"role": "user", "content": user_content}
            ],
            temperature=0.0,
            max_tokens=10
        )
        sentiment_label = response.choices[0].message.content.strip().lower()
        
        # Clean label (extract exact match if LLM returns more text)
        for label in sentiment_map:
            if label in sentiment_label:
                return label, sentiment_map[label]
                
        # If no label matches, return neutral fallback
        return "neutral", 0.5
    except Exception as e:
        print(f"Error during OpenAI sentiment classification: {e}")
        return "neutral", 0.5

async def async_classify_text(text: str) -> str:
    sentiment_map = ["confident", "neutral", "confused", "frustrated"]
    if not aclient:
        return "neutral"
        
    try:
        response = await aclient.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system", 
                    "content": "You are analyzing a student's learning session. Classify their emotional state from their messages as exactly one of: confident, neutral, frustrated, confused. Reply with the single word only."
                },
                {"role": "user", "content": text}
            ],
            temperature=0.0,
            max_tokens=10
        )
        label = response.choices[0].message.content.strip().lower()
        for valid_l in sentiment_map:
            if valid_l in label:
                return valid_l
        return "neutral"
    except Exception as e:
        print(f"Error classifying text '{text}': {e}")
        return "neutral"

@router.get("/")
async def test_agent():
    """
    Test endpoint for Agent router
    """
    return {
        "status": "success",
        "message": "Agent router is active"
    }

@router.post("/classify-state")
async def classify_state(req: ClassifyStateReq):
    try:
        # 1. LLM sentiment classification
        sentiment_label, sentiment_score = classify_sentiment(req.messages)
        
        # 2. Behavioral Signals
        retry_penalty = min(req.retries * 0.1, 0.4)
        pace_score = max(0.0, 1.0 - (req.time_taken / 300.0))
        
        # Clamp all values to 0-1
        retry_penalty = max(0.0, min(1.0, retry_penalty))
        pace_score = max(0.0, min(1.0, pace_score))
        
        # Scale recent accuracy to [0, 1] if passed as percentage > 1.0
        acc_scaled = req.recent_accuracy
        if acc_scaled > 1.0:
            acc_scaled = acc_scaled / 100.0
        acc_scaled = max(0.0, min(1.0, acc_scaled))
        
        # 3. Fusion Formula
        confidence = (0.35 * acc_scaled) + (0.30 * sentiment_score) + (0.20 * pace_score) - (0.15 * retry_penalty)
        confidence = max(0.0, min(1.0, confidence))
        
        # 4. Decision logic
        if confidence < 0.35:
            action = "decrease_difficulty"
            message = "Let's slow down and try an easier challenge."
        elif confidence > 0.72:
            action = "increase_difficulty"
            message = "Excellent progress — raising the difficulty!"
        else:
            action = "maintain"
            message = None
            
        # 5. Log to Firestore
        db = get_db()
        now = datetime.datetime.now(datetime.timezone.utc)
        
        log_entry = {
            "userId": req.user_id,
            "sentiment": sentiment_label,
            "sentimentScore": sentiment_score,
            "confidence": confidence,
            "action": action,
            "message": message,
            "behavioralSignals": {
                "retries": req.retries,
                "time_taken": req.time_taken,
                "recent_accuracy": req.recent_accuracy,
                "pace_score": pace_score
            },
            "timestamp": now
        }
        db.collection("stateLog").add(log_entry)
        
        # 6. Return response
        return {
            "sentiment": sentiment_label,
            "confidence": confidence,
            "action": action,
            "message": message,
            "signals": {
                "retries": req.retries,
                "time_taken": req.time_taken,
                "recent_accuracy": req.recent_accuracy,
                "pace_score": pace_score,
                "retry_penalty": retry_penalty,
                "sentiment_score": sentiment_score
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error classifying student state: {str(e)}")

@router.post("/label-data")
async def label_data(req: LabelDataReq):
    try:
        tasks = [async_classify_text(text) for text in req.texts]
        labels = await asyncio.gather(*tasks)
        
        results = []
        for text, label in zip(req.texts, labels):
            results.append({"text": text, "label": label})
            
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error labelling dataset: {str(e)}")

@router.get("/state-log/{user_id}")
async def get_state_log(user_id: str):
    try:
        db = get_db()
        logs_ref = db.collection("stateLog")
        query = logs_ref.where("userId", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(20)
        docs = list(query.stream())
        
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            
            # Serialize timestamp to string
            ts = data.get("timestamp")
            if ts:
                if hasattr(ts, "isoformat"):
                    data["timestamp"] = ts.isoformat()
                else:
                    data["timestamp"] = str(ts)
            results.append(data)
            
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching state logs: {str(e)}")

@router.get("/mood-chart/{user_id}")
async def get_mood_chart(user_id: str):
    try:
        db = get_db()
        logs_ref = db.collection("stateLog")
        query = logs_ref.where("userId", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(30)
        docs = list(query.stream())
        
        # Reverse to chronological order (oldest first)
        docs.reverse()
        
        dates = []
        sentiments = []
        confidences = []
        actions = []
        
        for doc in docs:
            data = doc.to_dict()
            
            # Format timestamp
            ts = data.get("timestamp")
            date_str = ""
            if ts:
                if hasattr(ts, "strftime"):
                    date_str = ts.strftime("%Y-%m-%d %H:%M")
                elif hasattr(ts, "isoformat"):
                    date_str = ts.isoformat()
                else:
                    date_str = str(ts)
            dates.append(date_str)
            sentiments.append(data.get("sentiment", "neutral"))
            confidences.append(float(data.get("confidence", 0.5)))
            actions.append(data.get("action", "maintain"))
            
        return {
            "dates": dates,
            "sentiments": sentiments,
            "confidences": confidences,
            "actions": actions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching mood chart: {str(e)}")

import warnings
warnings.filterwarnings('ignore')

from fastapi import APIRouter
from pydantic import BaseModel
from firebase_admin import firestore
from datetime import datetime, timedelta
import smtplib, os, statistics
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import google.generativeai as genai

router = APIRouter(prefix="/reporting")
db     = firestore.client()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
llm = genai.GenerativeModel("gemini-1.5-flash")

class ReportRequest(BaseModel):
    user_id: str

@router.post("/weekly-report")
def weekly_report(req: ReportRequest):
    week_ago = datetime.now() - timedelta(days=7)
    try:
        sessions = db.collection("users").document(req.user_id)\
            .collection("sessions")\
            .where("timestamp",">=",week_ago).stream()
        data = [s.to_dict() for s in sessions]
    except Exception:
        data = []

    if len(data) < 2:
        return {"status": "not enough data", "sessions": len(data)}

    scores    = [d.get("score", 0) for d in data]
    avg       = round(statistics.mean(scores), 1)
    best      = max(scores)
    total     = len(scores)
    half      = len(scores) // 2
    first_avg = statistics.mean(scores[:half]) if half > 0 else avg
    last_avg  = statistics.mean(scores[half:]) if half > 0 else avg
    trend     = ("improving" if last_avg > first_avg + 5
                 else "declining" if last_avg < first_avg - 5
                 else "stable")
    stdev     = statistics.stdev(scores) if len(scores) >= 3 else 1
    anomalies = sum(1 for s in scores if abs(s - avg) / stdev > 1.8)
    topics    = list({d.get("topicId","") for d in data if d.get("topicId")})
    total_mins= round(sum(d.get("timeTaken",0) for d in data) / 60, 1)

    try:
        summary = llm.generate_content(
            f"Write a 3 sentence encouraging weekly Python learning summary.\n"
            f"Average score: {avg}%. Trend: {trend}. Sessions completed: {total}.\n"
            f"Topics studied: {', '.join(topics)}. Time studied: {total_mins} minutes.\n"
            f"Anomalies detected: {anomalies}.\n"
            f"End with one specific actionable tip."
        ).text.strip()
    except Exception:
        summary = f"You completed {total} sessions this week with an average score of {avg}%. Your trend is {trend}. Keep pushing forward!"

    user_doc = db.collection("users").document(req.user_id).get().to_dict() or {}
    email    = user_doc.get("email","")

    if email:
        try:
            _send_email(email, avg, trend, total, best, summary, anomalies, topics, total_mins)
        except Exception as e:
            print(f"Email failed: {e}")

    db.collection("users").document(req.user_id)\
        .collection("weeklyReports").add({
            "avg_score":    avg,
            "best_score":   best,
            "trend":        trend,
            "total_sessions": total,
            "topics":       topics,
            "anomalies":    anomalies,
            "total_minutes":total_mins,
            "summary":      summary,
            "timestamp":    firestore.SERVER_TIMESTAMP
        })

    return {
        "avg_score": avg,
        "best_score":best,
        "trend":     trend,
        "sessions":  total,
        "topics":    topics,
        "anomalies": anomalies,
        "total_minutes": total_mins,
        "summary":   summary,
        "emailed":   bool(email)
    }

@router.get("/history/{user_id}")
def report_history(user_id: str):
    try:
        reports = db.collection("users").document(user_id)\
            .collection("weeklyReports")\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)\
            .limit(8).stream()
        return {"reports": [r.to_dict() for r in reports]}
    except Exception:
        return {"reports": []}

def _send_email(to, avg, trend, total, best, summary, anomalies, topics, mins):
    msg            = MIMEMultipart("alternative")
    msg["Subject"] = "Your DevLingo Weekly Report"
    msg["From"]    = os.getenv("GMAIL_SENDER")
    msg["To"]      = to
    color = "#34d399" if trend=="improving" else "#f87171" if trend=="declining" else "#fbbf24"
    arrow = "Improving" if trend=="improving" else "Declining" if trend=="declining" else "Stable"
    anomaly_block = ""
    if anomalies > 0:
        anomaly_block = (
            '<div style="background:#451a03;border:1px solid #f59e0b;border-radius:10px;'
            'padding:12px;margin-bottom:12px">'
            '<p style="color:#fbbf24;margin:0">' + str(anomalies) + ' unusual session(s) detected this week.</p></div>'
        )
    html = (
        '<div style="font-family:sans-serif;max-width:520px;background:#0d1117;'
        'color:#f0f4ff;border-radius:14px;padding:24px;margin:0 auto">'
        '<h2 style="color:#818cf8;margin:0 0 16px">DevLingo Weekly Report</h2>'
        '<div style="display:flex;gap:10px;margin-bottom:16px">'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Average Score</p>'
        '<p style="color:#818cf8;font-size:26px;font-weight:700;margin:4px 0">' + str(avg) + '%</p></div>'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Trend</p>'
        '<p style="color:' + color + ';font-size:18px;font-weight:700;margin:4px 0">' + arrow + '</p></div>'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Sessions</p>'
        '<p style="color:#34d399;font-size:26px;font-weight:700;margin:4px 0">' + str(total) + '</p></div>'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Time Studied</p>'
        '<p style="color:#fbbf24;font-size:20px;font-weight:700;margin:4px 0">' + str(mins) + 'm</p></div></div>'
        + anomaly_block +
        '<div style="background:#1e2433;border-left:4px solid #6366f1;'
        'border-radius:10px;padding:16px;margin-bottom:12px">'
        '<p style="color:#818cf8;font-size:11px;font-weight:600;'
        'margin:0 0 8px;text-transform:uppercase">AI Coach Says</p>'
        '<p style="color:#f0f4ff;line-height:1.6;margin:0">' + summary + '</p></div>'
        '<p style="color:#4a5568;font-size:11px;text-align:center;margin:0">'
        'DevLingo -- Keep Learning Every Day</p></div>'
    )
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.getenv("GMAIL_SENDER"), os.getenv("GMAIL_APP_PASSWORD"))
        smtp.send_message(msg)

import os
import io
import base64
import datetime
import statistics
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

# Initialize FastAPI router
router = APIRouter(prefix="/reporting", tags=["reporting"])

# Initialize Firestore
import firebase_admin
from firebase_admin import firestore

if not firebase_admin._apps:
    try:
        firebase_admin.initialize_app()
    except Exception as e:
        print(f"Firebase initialization warning: {e}")

db_client = None
def get_db():
    global db_client
    if db_client is None:
        try:
            db_client = firestore.client()
        except Exception:
            raise HTTPException(
                status_code=503, 
                detail="Firebase Admin SDK is not initialized. Please configure serviceAccount.json or GOOGLE_CREDS_JSON."
            )
    return db_client

# Initialize OpenAI Client
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# Matplotlib configuration (non-interactive backend)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── HELPER FUNCTION FOR REPORT GENERATION ──

def _generate_weekly_report_data(user_id: str):
    db = get_db()
    today = datetime.datetime.now(datetime.timezone.utc)
    seven_days_ago = today - datetime.timedelta(days=7)
    
    # 1. Pull sessions from last 7 days
    sessions_ref = db.collection("users").document(user_id).collection("sessions")
    query = sessions_ref.where("timestamp", ">=", seven_days_ago)
    docs = list(query.stream())
    
    total_sessions = len(docs)
    if total_sessions < 2:
        return {
            "status": "not enough data",
            "sessions_found": total_sessions
        }
        
    sessions_data = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        ts = d.get("timestamp")
        if ts:
            if hasattr(ts, "to_datetime"):
                d["timestamp_dt"] = ts.to_datetime()
            elif isinstance(ts, datetime.datetime):
                d["timestamp_dt"] = ts
            else:
                try:
                    d["timestamp_dt"] = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except ValueError:
                    d["timestamp_dt"] = today
        else:
            d["timestamp_dt"] = today
        sessions_data.append(d)
        
    # Sort chronologically
    sessions_data.sort(key=lambda x: x["timestamp_dt"])
    
    # 3. Compute statistics
    scores = [float(s.get("score", 0)) for s in sessions_data]
    avg_score = round(statistics.mean(scores), 1)
    best_score = max(scores)
    worst_score = min(scores)
    
    total_time_minutes = sum(float(s.get("timeTaken", 0)) for s in sessions_data) / 60.0
    topics_covered = list(set(s.get("topicId") for s in sessions_data if s.get("topicId")))
    
    # Trend calculation
    if len(scores) >= 3:
        first_3_avg = statistics.mean(scores[:3])
        last_3_avg = statistics.mean(scores[-3:])
    else:
        first_3_avg = statistics.mean(scores)
        last_3_avg = statistics.mean(scores)
        
    if last_3_avg > first_3_avg:
        trend = "improving"
    elif last_3_avg < first_3_avg:
        trend = "declining"
    else:
        trend = "stable"
        
    # Streak days (consecutive days with at least 1 session)
    dates = sorted(list(set(s["timestamp_dt"].date() for s in sessions_data)))
    streak_days = 0
    if dates:
        streak = 1
        max_streak = 1
        for i in range(1, len(dates)):
            if (dates[i] - dates[i-1]).days == 1:
                streak += 1
                max_streak = max(max_streak, streak)
            elif (dates[i] - dates[i-1]).days > 1:
                streak = 1
        streak_days = max_streak
        
    # 4. Anomaly detection (z-score)
    anomalies = []
    if len(scores) >= 4:
        mean = statistics.mean(scores)
        stdev = statistics.stdev(scores)
        if stdev == 0:
            stdev = 1.0
        for s in sessions_data:
            s_score = float(s.get("score", 0))
            if abs(s_score - mean) / stdev > 1.8:
                anomalies.append(s)
                
    # 5. Generate Matplotlib chart
    fig, ax = plt.subplots(figsize=(8, 3), facecolor='#0d1117')
    ax.set_facecolor('#0d1117')
    
    session_nums = list(range(1, len(scores) + 1))
    ax.plot(session_nums, scores, color='#6366f1', marker='o', linewidth=2, label='Score')
    ax.axhline(avg_score, color='#8892a4', linestyle='--', alpha=0.7, label=f'Mean ({avg_score})')
    
    if len(anomalies) > 0:
        anomaly_indices = []
        anomaly_scores = []
        for idx, s in enumerate(sessions_data):
            if s["id"] in [anom["id"] for anom in anomalies]:
                anomaly_indices.append(idx + 1)
                anomaly_scores.append(float(s.get("score", 0)))
        ax.scatter(anomaly_indices, anomaly_scores, color='#ef4444', s=80, zorder=5, label='Anomaly')
        
    ax.set_ylim(0, 105)
    ax.set_xlim(0.5, len(scores) + 0.5)
    ax.set_title("Weekly Progress", color='#f0f4ff', fontsize=12, fontweight='bold')
    ax.tick_params(colors='#8892a4', labelsize=9)
    ax.spines['bottom'].set_color('#2d3748')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#2d3748')
    ax.grid(True, color='#2d3748', linestyle=':', alpha=0.5)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    buf.seek(0)
    chart_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    
    # 6. LLM Natural Language Summary
    prompt_text = f"""
    Here are the user's statistics for the past week:
    - Total sessions: {total_sessions}
    - Average score: {avg_score}%
    - Best score: {best_score}%
    - Worst score: {worst_score}%
    - Total study time: {total_time_minutes:.1f} minutes
    - Unique topics covered: {", ".join(topics_covered)}
    - Performance trend: {trend}
    - Study streak: {streak_days} days
    - Anomaly sessions: {len(anomalies)}
    """
    
    summary_text = "Keep up the hard work studying on DevLingo!"
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are DevLingo's progress coach. Write a warm, encouraging 3-sentence progress summary. Be specific about the numbers. End with one concrete actionable tip."
                },
                {
                    "role": "user",
                    "content": prompt_text
                }
            ],
            max_tokens=120,
            temperature=0.7
        )
        summary_text = response.choices[0].message.content.strip()
    except Exception as llm_err:
        print(f"LLM reporting generation error: {llm_err}")
        
    # Week Label: e.g. "Aug 14-20" or "Jul 28 - Aug 3"
    yesterday = today - datetime.timedelta(days=1)
    if seven_days_ago.month == yesterday.month:
        week_label = f"{seven_days_ago.strftime('%b')} {seven_days_ago.day}-{yesterday.day}"
    else:
        week_label = f"{seven_days_ago.strftime('%b')} {seven_days_ago.day} - {yesterday.strftime('%b')} {yesterday.day}"
        
    return {
        "status": "success",
        "avg_score": avg_score,
        "best_score": best_score,
        "worst_score": worst_score,
        "total_sessions": total_sessions,
        "total_time_minutes": total_time_minutes,
        "topics_covered": topics_covered,
        "trend": trend,
        "streak_days": streak_days,
        "anomalies_count": len(anomalies),
        "summary_text": summary_text,
        "chart_base64": chart_base64,
        "week_label": week_label
    }

# ── ROUTER ENDPOINTS ──

@router.post("/generate-weekly/{user_id}")
async def generate_weekly(user_id: str):
    try:
        db = get_db()
        report = _generate_weekly_report_data(user_id)
        if report.get("status") == "not enough data":
            return report
            
        # 8. Save report to Firestore collection users/{user_id}/weeklyReports
        report_data = {
            "avg_score": report["avg_score"],
            "best_score": report["best_score"],
            "worst_score": report["worst_score"],
            "total_sessions": report["total_sessions"],
            "total_time_minutes": report["total_time_minutes"],
            "topics_covered": report["topics_covered"],
            "trend": report["trend"],
            "streak_days": report["streak_days"],
            "anomalies_count": report["anomalies_count"],
            "summary_text": report["summary_text"],
            "chart_base64": report["chart_base64"],
            "week_label": report["week_label"],
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        db.collection("users").document(user_id).collection("weeklyReports").add(report_data)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-email/{user_id}")
async def send_email(user_id: str):
    try:
        db = get_db()
        # 1. Generate weekly report data
        report = _generate_weekly_report_data(user_id)
        if report.get("status") == "not enough data":
            return report
            
        # 2. Get user email and name from Firestore
        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists():
            raise HTTPException(status_code=404, detail="User profile not found")
            
        user_data = user_doc.to_dict()
        email = user_data.get("email")
        name = user_data.get("name") or user_data.get("displayName") or "Student"
        
        if not email:
            raise HTTPException(status_code=400, detail="User email not found in profile")
            
        # Trend indicators: ↑ improving green, ↓ declining red, → stable gray
        trend = report["trend"]
        if trend == "improving":
            trend_indicator = '<span style="color:#10b981; font-weight:bold; font-family:sans-serif;">↑ Improving</span>'
        elif trend == "declining":
            trend_indicator = '<span style="color:#ef4444; font-weight:bold; font-family:sans-serif;">↓ Declining</span>'
        else:
            trend_indicator = '<span style="color:#8892a4; font-weight:bold; font-family:sans-serif;">→ Stable</span>'
            
        # Anomaly note
        anomaly_note = ""
        if report["anomalies_count"] > 0:
            anomaly_note = f"""
            <div style="background-color:rgba(239,68,68,0.1); border:1px solid #ef4444; border-radius:6px; padding:15px; margin-top:20px; font-family:sans-serif;">
              <p style="color:#ef4444; font-weight:600; margin:0 0 4px; font-size:14px;">Anomaly Detected</p>
              <p style="color:#8892a4; margin:0; font-size:13px; line-height:1.5;">
                We detected {report['anomalies_count']} session(s) where your score was significantly different from your average. 
                This might indicate a challenging concept. Don't worry—mistakes are part of learning!
              </p>
            </div>
            """
            
        # 3. Build HTML email using table grids for high client compatibility
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin:0; padding:20px; background-color:#0f1117; color:#f0f4ff;">
          <div style="max-width:600px; margin:0 auto; background-color:#1a1f2e; border:1px solid #2d3748; border-radius:12px; padding:30px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
            <!-- Header -->
            <div style="text-align:center; padding-bottom:20px; border-bottom:1px solid #2d3748; margin-bottom:20px;">
              <h2 style="color:#6366f1; font-weight:600; margin:0; font-size:24px; font-family:sans-serif;">DevLingo Weekly Report</h2>
              <p style="color:#8892a4; font-size:14px; margin:5px 0 0 0; font-family:sans-serif;">Week of {report['week_label']}</p>
            </div>
            
            <!-- Greeting -->
            <p style="font-size:16px; line-height:1.5; margin-bottom:20px; font-family:sans-serif; color:#f0f4ff;">Hi {name},</p>
            
            <!-- Summary Paragraph -->
            <p style="font-size:15px; line-height:1.6; color:#e2e8f0; background-color:#161b27; border-left:3px solid #6366f1; padding:15px; border-radius:4px; margin-bottom:25px; font-family:sans-serif;">
              {report['summary_text']}
            </p>
            
            <!-- Stats Table Grid -->
            <table cellpadding="0" cellspacing="10" border="0" width="100%" style="margin-bottom:25px;">
              <tr>
                <td width="50%" align="center" style="background-color:#161b27; border:1px solid #2d3748; padding:15px; border-radius:8px; font-family:sans-serif;">
                  <span style="font-size:12px; color:#8892a4; display:block; margin-bottom:4px;">Average Score</span>
                  <strong style="font-size:20px; color:#f0f4ff;">{report['avg_score']}%</strong>
                </td>
                <td width="50%" align="center" style="background-color:#161b27; border:1px solid #2d3748; padding:15px; border-radius:8px; font-family:sans-serif;">
                  <span style="font-size:12px; color:#8892a4; display:block; margin-bottom:4px;">Sessions</span>
                  <strong style="font-size:20px; color:#f0f4ff;">{report['total_sessions']}</strong>
                </td>
              </tr>
              <tr>
                <td width="50%" align="center" style="background-color:#161b27; border:1px solid #2d3748; padding:15px; border-radius:8px; font-family:sans-serif;">
                  <span style="font-size:12px; color:#8892a4; display:block; margin-bottom:4px;">Time Studied</span>
                  <strong style="font-size:20px; color:#f0f4ff;">{report['total_time_minutes']:.1f}m</strong>
                </td>
                <td width="50%" align="center" style="background-color:#161b27; border:1px solid #2d3748; padding:15px; border-radius:8px; font-family:sans-serif;">
                  <span style="font-size:12px; color:#8892a4; display:block; margin-bottom:4px;">Trend</span>
                  <div>{trend_indicator}</div>
                </td>
              </tr>
            </table>
            
            <!-- Chart Image -->
            <div style="text-align:center; margin-bottom:25px;">
              <img src="data:image/png;base64,{report['chart_base64']}" alt="Weekly Progress Chart" style="max-width:100%; border-radius:8px; border:1px solid #2d3748;">
            </div>
            
            <!-- Anomaly Note -->
            {anomaly_note}
            
            <!-- Footer -->
            <div style="text-align:center; padding-top:20px; border-top:1px solid #2d3748; margin-top:25px; color:#8892a4; font-size:13px; font-family:sans-serif;">
              <p style="margin:0 0 5px 0;">Keep learning — DevLingo</p>
            </div>
          </div>
        </body>
        </html>
        """
        
        # 4. Dispatch email using smtplib
        sender = os.getenv("GMAIL_SENDER")
        password = os.getenv("GMAIL_APP_PASSWORD")
        
        if not sender or not password:
            raise HTTPException(status_code=500, detail="Mail server environment variables not configured.")
            
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Your DevLingo Weekly Report - {report['week_label']}"
        msg['From'] = f"DevLingo Progress Coach <{sender}>"
        msg['To'] = email
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, email, msg.as_string())
            
        return {
            "sent": True,
            "to": email,
            "report_summary": f"{report['avg_score']}% {report['trend']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{user_id}")
async def get_history(user_id: str):
    try:
        db = get_db()
        docs = db.collection("users").document(user_id).collection("weeklyReports") \
                 .order_by("timestamp", direction=firestore.Query.DESCENDING) \
                 .limit(8) \
                 .stream()
                 
        results = []
        for doc in docs:
            data = doc.to_dict()
            ts = data.get("timestamp")
            timestamp_str = ""
            if ts:
                if hasattr(ts, "to_datetime"):
                    timestamp_str = ts.to_datetime().isoformat()
                elif isinstance(ts, datetime.datetime):
                    timestamp_str = ts.isoformat()
                else:
                    timestamp_str = str(ts)
                    
            results.append({
                "week_label": data.get("week_label"),
                "avg_score": data.get("avg_score"),
                "trend": data.get("trend"),
                "total_sessions": data.get("total_sessions"),
                "timestamp": timestamp_str
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

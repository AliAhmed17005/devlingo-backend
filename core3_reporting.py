import warnings
warnings.filterwarnings('ignore')

from fastapi import APIRouter
from pydantic import BaseModel
from firebase_admin import firestore
from datetime import datetime, timedelta, timezone
import smtplib, os, statistics, asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any

router = APIRouter(prefix="/reporting", tags=["reporting"])
db     = firestore.client()

class ReportRequest(BaseModel):
    user_id: str
    email: Optional[str] = None
    force: Optional[bool] = False

def _parse_timestamp(ts) -> Optional[datetime]:
    if not ts:
        return None
    if hasattr(ts, "to_datetime"):
        return ts.to_datetime().replace(tzinfo=None)
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return None

def generate_and_send_user_weekly_report(user_id: str, user_doc: Optional[Dict[str, Any]] = None, email_override: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """
    Core function to evaluate user sessions, build statistics,
    and send an automated or manual weekly performance report.
    Guarantees that reports are ONLY sent if at least 1 session has been completed.
    """
    week_ago = datetime.now() - timedelta(days=7)

    # 1. Fetch sessions from the last 7 days
    try:
        sessions_stream = db.collection("users").document(user_id)\
            .collection("sessions")\
            .where("timestamp", ">=", week_ago).stream()
        data = [s.to_dict() for s in sessions_stream]
    except Exception as e:
        print(f"[Reporting] Error fetching weekly sessions for {user_id}: {e}")
        data = []

    # If no sessions in the last 7 days, check if user has EVER completed any session
    if not data or len(data) == 0:
        try:
            all_sessions = list(db.collection("users").document(user_id)\
                .collection("sessions").limit(1).stream())
            has_any = len(all_sessions) > 0
        except Exception:
            has_any = False

        if not has_any:
            return {
                "status": "not enough data",
                "sessions": 0,
                "message": "No study sessions found. Please complete at least 1 study session before generating your performance report.",
                "emailed": False,
                "email_error": "Cannot send report: User has not completed any study sessions."
            }
        else:
            return {
                "status": "not enough data",
                "sessions": 0,
                "message": "No study sessions completed in the last 7 days. Complete a study session this week to generate an active report!",
                "emailed": False,
                "email_error": "No study sessions completed in the past 7 days."
            }

    # 2. Check frequency throttle unless forced
    if not force:
        try:
            recent_reports = list(db.collection("users").document(user_id)\
                .collection("weeklyReports")\
                .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                .limit(1).stream())
            if recent_reports:
                last_rep = recent_reports[0].to_dict()
                last_ts = _parse_timestamp(last_rep.get("timestamp"))
                if last_ts and (datetime.now() - last_ts).total_seconds() < 6 * 86400:
                    return {
                        "status": "skipped",
                        "reason": "already_sent_recently",
                        "sessions": len(data),
                        "message": "Weekly report was already generated within the past 6 days.",
                        "emailed": False
                    }
        except Exception as e:
            print(f"[Reporting] Error checking previous reports for {user_id}: {e}")

    # 3. Calculate True Performance Metrics (Zero dummy mock data)
    scores = [float(d.get("score", 0)) for d in data]
    avg = round(statistics.mean(scores), 1)
    best = round(max(scores), 1)
    worst = round(min(scores), 1)
    total = len(data)
    half = len(scores) // 2
    first_avg = statistics.mean(scores[:half]) if half > 0 else avg
    last_avg = statistics.mean(scores[half:]) if half > 0 else avg
    trend = ("improving" if last_avg > first_avg + 3
             else "declining" if last_avg < first_avg - 3
             else "stable")
    stdev = statistics.stdev(scores) if len(scores) >= 3 else 1
    anomalies = sum(1 for s in scores if abs(s - avg) / (stdev or 1) > 1.8)
    topics = list({d.get("topicId", "") for d in data if d.get("topicId")}) or ["Python Practice"]
    total_mins = round(sum(float(d.get("timeTaken", 0)) for d in data) / 60, 1)

    summary = (
        f"You completed {total} session(s) this week with an average score of {avg}%. "
        f"Your learning trend is currently {trend}. "
        f"Keep practicing daily to consolidate your Python problem-solving mastery!"
    )

    # Optional AI enrichment with strict 3s timeout
    try:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            llm = genai.GenerativeModel("gemini-1.5-flash")
            res = llm.generate_content(
                f"Write a 3 sentence encouraging weekly Python learning summary.\n"
                f"Average score: {avg}%. Trend: {trend}. Sessions completed: {total}.\n"
                f"Topics studied: {', '.join(topics)}. Time studied: {total_mins} minutes.\n"
                f"End with one specific actionable tip.",
                request_options={"timeout": 3.0}
            )
            if res and res.text:
                summary = res.text.strip()
    except Exception:
        pass

    # 4. Determine recipient email
    if not user_doc:
        try:
            user_snap = db.collection("users").document(user_id).get()
            if user_snap.exists:
                user_doc = user_snap.to_dict() or {}
            else:
                user_doc = {}
        except Exception:
            user_doc = {}

    recipient_email = (email_override or user_doc.get("email", "")).strip()
    emailed = False
    email_error = None

    if recipient_email:
        try:
            emailed = _send_email(recipient_email, avg, trend, total, best, summary, anomalies, topics, total_mins)
            if not emailed:
                email_error = "SMTP credentials missing or rejected"
        except Exception as e:
            print(f"[Reporting] Email dispatch failed for {recipient_email}: {e}")
            emailed = False
            email_error = str(e)
    else:
        email_error = "No recipient email address provided in profile"

    # 5. Persist report to Firestore
    report_data = {
        "avg_score": avg,
        "best_score": best,
        "worst_score": worst,
        "trend": trend,
        "total_sessions": total,
        "sessions": total,
        "topics": topics,
        "anomalies": anomalies,
        "total_minutes": total_mins,
        "summary": summary,
        "emailed": emailed,
        "email_error": email_error,
        "recipient_email": recipient_email,
        "timestamp": firestore.SERVER_TIMESTAMP
    }

    try:
        db.collection("users").document(user_id)\
            .collection("weeklyReports").add(report_data)
    except Exception as e:
        print(f"[Reporting] Failed to save report to Firestore: {e}")

    return {
        "status": "success",
        "avg_score": avg,
        "best_score": best,
        "trend": trend,
        "sessions": total,
        "topics": topics,
        "anomalies": anomalies,
        "total_minutes": total_mins,
        "summary": summary,
        "emailed": emailed,
        "email_error": email_error,
        "recipient_email": recipient_email
    }

@router.post("/weekly-report")
def weekly_report(req: ReportRequest):
    """
    On-demand endpoint triggered by user clicking 'Send Weekly Report' in Frontend.
    Force=True allows generating when requested, but enforces >= 1 session.
    """
    return generate_and_send_user_weekly_report(
        user_id=req.user_id,
        email_override=req.email,
        force=True
    )

def dispatch_all_weekly_reports(force: bool = False) -> Dict[str, Any]:
    """
    Scans all users and automatically dispatches weekly reports
    to those who completed >= 1 session and are due (every 7 days).
    """
    stats = {
        "total_users": 0,
        "dispatched": 0,
        "skipped_opt_out": 0,
        "skipped_no_email": 0,
        "skipped_no_sessions": 0,
        "skipped_recent": 0,
        "failed": 0
    }

    try:
        users_stream = db.collection("users").stream()
        for doc in users_stream:
            stats["total_users"] += 1
            user_id = doc.id
            user_data = doc.to_dict() or {}

            # Check if user opted out in settings
            if user_data.get("weeklyReport") is False:
                stats["skipped_opt_out"] += 1
                continue

            # Check email
            email = user_data.get("email", "").strip()
            if not email:
                stats["skipped_no_email"] += 1
                continue

            try:
                res = generate_and_send_user_weekly_report(
                    user_id=user_id,
                    user_doc=user_data,
                    email_override=email,
                    force=force
                )
                if res.get("status") == "success":
                    stats["dispatched"] += 1
                elif res.get("status") == "not enough data":
                    stats["skipped_no_sessions"] += 1
                elif res.get("reason") == "already_sent_recently":
                    stats["skipped_recent"] += 1
                else:
                    stats["skipped_no_sessions"] += 1
            except Exception as e:
                print(f"[WeeklyScheduler] Failed processing user {user_id}: {e}")
                stats["failed"] += 1

    except Exception as e:
        print(f"[WeeklyScheduler] Batch dispatch error: {e}")

    return stats

@router.post("/dispatch-all")
def dispatch_all():
    """Manual or external webhook trigger to run the weekly dispatch for all users."""
    return dispatch_all_weekly_reports(force=False)

async def automated_weekly_reports_scheduler():
    """
    Background worker running inside FastAPI event loop.
    Checks all users hourly and automatically emails weekly reports
    to students who have completed sessions and reached the 7-day cadence.
    """
    # Wait 45 seconds on server startup before initial run
    await asyncio.sleep(45)
    while True:
        try:
            print("[WeeklyReportScheduler] â° Checking for users due for automated weekly report...")
            res = dispatch_all_weekly_reports(force=False)
            print(f"[WeeklyReportScheduler] âœ… Weekly check completed: Dispatched={res['dispatched']}, SkippedNoSessions={res['skipped_no_sessions']}, SkippedRecent={res['skipped_recent']}")
        except Exception as e:
            print(f"[WeeklyReportScheduler] âŒ Scheduler encountered error: {e}")
        # Run cadence check every 1 hour (3600 seconds)
        await asyncio.sleep(3600)

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
    sender = os.getenv("GMAIL_SENDER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("[Reporting] GMAIL_SENDER or GMAIL_APP_PASSWORD not set in environment.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your DevLingo Weekly Performance Report"
    msg["From"] = f"DevLingo <{sender}>"
    msg["To"] = to

    color = "#34d399" if trend == "improving" else "#f87171" if trend == "declining" else "#fbbf24"
    arrow = "Improving" if trend == "improving" else "Declining" if trend == "declining" else "Stable"
    anomaly_block = ""
    if anomalies > 0:
        anomaly_block = (
            '<div style="background:#451a03;border:1px solid #f59e0b;border-radius:10px;'
            'padding:12px;margin-bottom:12px">'
            f'<p style="color:#fbbf24;margin:0">{anomalies} unusual session(s) detected this week.</p></div>'
        )
    html = (
        '<div style="font-family:sans-serif;max-width:520px;background:#0d1117;'
        'color:#f0f4ff;border-radius:14px;padding:24px;margin:0 auto">'
        '<h2 style="color:#818cf8;margin:0 0 16px">DevLingo Weekly Report</h2>'
        '<div style="display:flex;gap:10px;margin-bottom:16px">'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Average Score</p>'
        f'<p style="color:#818cf8;font-size:26px;font-weight:700;margin:4px 0">{avg}%</p></div>'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Trend</p>'
        f'<p style="color:{color};font-size:18px;font-weight:700;margin:4px 0">{arrow}</p></div>'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Sessions</p>'
        f'<p style="color:#34d399;font-size:26px;font-weight:700;margin:4px 0">{total}</p></div>'
        '<div style="background:#1e2433;border-radius:10px;padding:14px;flex:1;text-align:center">'
        '<p style="color:#8892a4;font-size:11px;margin:0">Time Studied</p>'
        f'<p style="color:#fbbf24;font-size:20px;font-weight:700;margin:4px 0">{mins}m</p></div></div>'
        + anomaly_block +
        '<div style="background:#1e2433;border-left:4px solid #6366f1;'
        'border-radius:10px;padding:16px;margin-bottom:12px">'
        '<p style="color:#818cf8;font-size:11px;font-weight:600;'
        'margin:0 0 8px;text-transform:uppercase">AI Coach Says</p>'
        f'<p style="color:#f0f4ff;line-height:1.6;margin:0">{summary}</p></div>'
        '<p style="color:#4a5568;font-size:11px;text-align:center;margin:0">'
        'DevLingo -- Keep Learning Every Day</p></div>'
    )
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    return True
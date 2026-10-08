import warnings
warnings.filterwarnings("ignore")

import os, json, asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()

creds_json = os.getenv("GOOGLE_CREDS_JSON")
if creds_json and creds_json.strip():
    try:
        cred_dict = json.loads(creds_json)
        cred = credentials.Certificate(cred_dict)
    except Exception as e:
        print(f"Error loading GOOGLE_CREDS_JSON from env: {e}")
        if os.path.exists("serviceAccount.json"):
            cred = credentials.Certificate("serviceAccount.json")
        else:
            raise e
elif os.path.exists("serviceAccount.json"):
    cred = credentials.Certificate("serviceAccount.json")
else:
    raise ValueError("Missing Firebase credentials! Please add GOOGLE_CREDS_JSON to Railway Environment Variables.")

firebase_admin.initialize_app(cred)
db = firestore.client()

app = FastAPI(title="DevLingo Backend", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

from core1_difficulty import router as r1
from core2_agent      import router as r2
from core3_reporting  import router as r3, automated_weekly_reports_scheduler
from core4_scheduling import router as r4
from core5_codehealth import router as r5
from core6_matching   import router as r6

for r in [r1, r2, r3, r4, r5, r6]:
    app.include_router(r)

@app.on_event("startup")
async def startup_event():
    # Launch automated weekly email reports scheduler in background
    asyncio.create_task(automated_weekly_reports_scheduler())
    print("[DevLingo] Automated weekly report background scheduler launched.")

@app.get("/")
def root():
    return {
        "status": "DevLingo Backend running",
        "version": "2.0",
        "cores": [
            "difficulty", "agent", "reporting",
            "scheduling", "codehealth", "matching"
        ]
    }

@app.get("/health")
def health():
    return {"status": "ok"}
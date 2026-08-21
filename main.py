import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="DevLingo Backend",
    description="FastAPI Backend for DevLingo FYP",
    version="2.0"
)

# CORS middleware allowing all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firebase Admin SDK
firebase_initialized = False

# Try loading from serviceAccount.json
service_account_path = "serviceAccount.json"
if os.path.exists(service_account_path):
    try:
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        firebase_initialized = True
        print("Firebase Admin SDK initialized from serviceAccount.json")
    except Exception as e:
        print(f"Error initializing Firebase with serviceAccount.json: {e}")

# Fallback to GOOGLE_CREDS_JSON environment variable
if not firebase_initialized:
    google_creds_json = os.getenv("GOOGLE_CREDS_JSON")
    if google_creds_json:
        try:
            creds_dict = json.loads(google_creds_json)
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
            firebase_initialized = True
            print("Firebase Admin SDK initialized from GOOGLE_CREDS_JSON environment variable")
        except Exception as e:
            print(f"Error initializing Firebase with GOOGLE_CREDS_JSON env var: {e}")
    else:
        print("Warning: Neither serviceAccount.json nor GOOGLE_CREDS_JSON environment variable was found. Firebase Admin SDK not initialized.")

# Import and register routers
from routers import (
    code_health_router,
    difficulty_router,
    agent_router,
    reporting_router,
)

app.include_router(code_health_router, prefix="/code_health", tags=["Code Health"])
app.include_router(difficulty_router, prefix="/difficulty", tags=["Difficulty"])
app.include_router(agent_router, prefix="/agent", tags=["Agent"])
app.include_router(reporting_router, prefix="/reporting", tags=["Reporting"])

@app.get("/")
async def root():
    return {
        "status": "DevLingo Backend running",
        "version": "2.0",
        "cores": ["difficulty", "agent", "reporting", "code_health"]
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "firebase_initialized": firebase_initialized
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

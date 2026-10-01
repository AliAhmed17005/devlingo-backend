import os
import json
import random
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from firebase_admin import firestore
from openai import OpenAI

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

# Initialize OpenAI Client
openai_api_key = os.getenv("OPENAI_API_KEY")
client = None
if openai_api_key and "paste-your-key-here" not in openai_api_key:
    try:
        client = OpenAI(api_key=openai_api_key)
    except Exception as e:
        print(f"Error initializing OpenAI in Content Engine: {e}")

class GenerateConceptReq(BaseModel):
    topic_id: str
    difficulty_level: str  # easy, medium, hard, very_hard

class GenerateProblemReq(BaseModel):
    topic_id: str
    difficulty_level: str  # easy, medium, hard, very_hard

# Helper function to get topic title from Firestore
def get_topic_title(topic_id: str) -> str:
    try:
        db = get_db()
        courses_ref = db.collection("courses")
        courses_docs = list(courses_ref.stream())
        for doc in courses_docs:
            c_data = doc.to_dict()
            for topic in c_data.get("topics", []):
                if topic.get("id") == topic_id:
                    return topic.get("title", topic_id)
    except Exception:
        pass
    return topic_id

def _get_local_fallback_question(topic_id: str, difficulty_level: str):
    title = get_topic_title(topic_id)
    if difficulty_level == "easy":
        return {
            "id": "dyn_" + str(random.randint(1000, 9999)),
            "type": "mcq",
            "title": f"Intro to {title}",
            "description": f"Which of the following represents a basic implementation of {title} in Python?",
            "options": [
                "Using default values and keywords",
                "Importing an external library",
                "Writing raw bytes to sockets",
                "None of the above"
            ],
            "correctAnswer": 0,
            "explanation": f"Basic python {title} is implemented natively without complex libraries.",
            "topicId": topic_id,
            "courseId": "python-basics",
            "difficulty": "easy",
            "eloRating": 800.0
        }
    else:
        return {
            "id": "dyn_" + str(random.randint(1000, 9999)),
            "type": "coding",
            "title": f"Advanced {title} Challenge",
            "description": f"Write a Python script that showcases advanced usage of {title}. Output should print the word 'Success'.",
            "starterCode": f"# Write your solution for {title} here\nprint('Success')",
            "expectedOutput": "Success",
            "explanation": f"The starter code prints 'Success' demonstrating the correct setup.",
            "topicId": topic_id,
            "courseId": "python-basics",
            "difficulty": "medium",
            "eloRating": 1200.0
        }

# Core logic for generating questions
def generate_dynamic_question(topic_id: str, difficulty_level: str):
    # Fallback to local stub question generation if OpenAI client is missing or unconfigured
    if not client:
        print("Warning: OpenAI client not configured. Generating standard fallback question.")
        return _get_local_fallback_question(topic_id, difficulty_level)

    topic_title = get_topic_title(topic_id)
    
    prompt = f"""
    You are an expert Python programming tutor. Generate a unique, high-quality practice question for the topic "{topic_title}" at a "{difficulty_level}" level.
    The difficulty levels are defined as:
    - easy: Basic syntax, simple loops, variables, standard built-in functions.
    - medium: Intermediate logic, list comprehensions, dictionary operations, nested structures, basic OOP.
    - hard: Advanced structures, exceptions handling, decorators, generators, algorithms, system concepts.
    - very_hard: Complex system design, optimization, meta-programming, deep algorithmic optimization, concurrency.

    You can generate either a Multiple Choice Question (type: "mcq") or a Coding Challenge (type: "coding").
    Choose the type randomly or based on suitability for the difficulty.

    You MUST output your response in strict JSON format matching the schema below:
    {{
        "type": "mcq" or "coding",
        "title": "A short, descriptive title",
        "description": "The problem statement. For coding challenges, explain what input/output is expected. Use markdown and code blocks if needed.",
        "options": ["Option 0", "Option 1", "Option 2", "Option 3"], // Only if type is "mcq", MUST have exactly 4 choices
        "correctAnswer": 0 or 1 or 2 or 3, // Only if type is "mcq", index of correct option
        "starterCode": "starter python code template", // Only if type is "coding"
        "expectedOutput": "The exact stdout printed by the correct solution", // Only if type is "coding"
        "explanation": "Detailed explanation of the solution and concept."
    }}
    Ensure all quotes are escaped properly and output ONLY the valid JSON, no surrounding chat or text block markdown code wrappers.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a backend server API generating strict JSON output."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800
        )
        
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        problem_data = json.loads(text)
        
        # ELO mapping based on difficulty
        elo_map = {
            "easy": 800.0,
            "medium": 1200.0,
            "hard": 1500.0,
            "very_hard": 1800.0
        }
        
        problem_data["topicId"] = topic_id
        
        # Get courseId from Firestore
        db = get_db()
        courses_ref = db.collection("courses")
        courses_docs = list(courses_ref.stream())
        course_id = "python-basics"
        for doc in courses_docs:
            c_data = doc.to_dict()
            for t in c_data.get("topics", []):
                if t.get("id") == topic_id:
                    course_id = doc.id
                    break
        problem_data["courseId"] = course_id
        problem_data["difficulty"] = "easy" if difficulty_level == "easy" else "medium" if difficulty_level == "medium" else "hard"
        problem_data["eloRating"] = elo_map.get(difficulty_level, 1000.0)

        # Save to Firestore in background
        doc_ref = db.collection("problems").document()
        doc_ref.set(problem_data)
        
        problem_data["id"] = doc_ref.id
        return problem_data

    except Exception as e:
        print(f"Warning: OpenAI problem generation failed ({e}). Falling back to local question.")
        return _get_local_fallback_question(topic_id, difficulty_level)

def _get_local_fallback_concept(topic_id: str, difficulty_level: str):
    title = get_topic_title(topic_id)
    return {
        "title": f"Understanding {title} ({difficulty_level})",
        "explanation": f"### Introduction to {title}\nThis is a standard tutorial explanation detailing structural logic, basic rules, and common syntax patterns when dealing with {title}.",
        "codeSnippet": f"# Demonstration of {title}\ndef demo():\n    print('Working with {title}')\n\ndemo()",
        "keyTakeaways": [
            f"Understand how python parses {title}.",
            "Avoid common logic antipatterns in implementation.",
            "Ensure robust, clean modular syntax."
        ]
    }

@router.post("/generate-concept")
async def generate_concept(req: GenerateConceptReq):
    if not client:
        # Fallback explanation if OpenAI client is missing or unconfigured
        return _get_local_fallback_concept(req.topic_id, req.difficulty_level)

    topic_title = get_topic_title(req.topic_id)
    
    prompt = f"""
    You are an expert Python programming tutor. Generate an educational concept card / brief tutorial for the topic "{topic_title}" at a "{req.difficulty_level}" difficulty level.
    The response MUST be in strict JSON format:
    {{
        "title": "Topic Title",
        "explanation": "Markdown tutorial explanation of the concept tailored to this difficulty level.",
        "codeSnippet": "Demonstrative code snippet showing the concept in action.",
        "keyTakeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"]
    }}
    Ensure all quotes are escaped properly and output ONLY the valid JSON, no surrounding chat or text block markdown code wrappers.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a backend server API generating strict JSON output."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1000
        )
        
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        concept_data = json.loads(text)
        return concept_data
    except Exception as e:
        print(f"Warning: OpenAI concept generation failed ({e}). Falling back to local concept.")
        return _get_local_fallback_concept(req.topic_id, req.difficulty_level)

@router.post("/generate-problem")
async def generate_problem(req: GenerateProblemReq):
    return generate_dynamic_question(req.topic_id, req.difficulty_level)

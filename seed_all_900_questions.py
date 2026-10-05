import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

sa_path = "serviceAccount.json"
cred = credentials.Certificate(sa_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

print("Loading topics.json...")
with open(os.path.join("data", "topics.json"), "r", encoding="utf-8") as f:
    topics_list = json.load(f)

formatted_topics = []
for t in topics_list:
    formatted_topics.append({
        "id": t["topicId"],
        "title": t["topic"],
        "order": t["order"],
        "xp": 50 + (t["order"] * 5)
    })

# Update python-basics course document in Firestore
db.collection("courses").document("python-basics").set({
    "title": "Python Fundamentals",
    "description": "Master Python from fundamentals to advanced concepts with adaptive AI questions",
    "category": "Programming",
    "level": "Beginner",
    "lessons": 900,
    "weeks": 12,
    "instructor": "Dr. Sarah Khan",
    "rating": 4.9,
    "enrolled": 15400,
    "color": "#6366f1",
    "icon": "🐍",
    "topics": formatted_topics
}, merge=True)

print(f"Updated python-basics course document with {len(formatted_topics)} topics!")

print("Loading python_questions_900.json...")
with open(os.path.join("data", "python_questions_900.json"), "r", encoding="utf-8") as f:
    questions = json.load(f)

print(f"Seeding {len(questions)} questions into Firestore collection 'problems' in batches...")

batch = db.batch()
count = 0
total_seeded = 0

for q in questions:
    doc_id = q["id"]
    doc_ref = db.collection("problems").document(doc_id)

    prob_data = {
        "id": doc_id,
        "courseId": "python-basics",
        "topicId": q["topicId"],
        "topic": q.get("topic", ""),
        "subtopic": q.get("subtopic", ""),
        "title": f"{q.get('topic', '')} — {q.get('subtopic', '')}",
        "question": q.get("question", ""),
        "options": q.get("options", []),
        "correctIndex": q.get("correctIndex", 0),
        "correctAnswer": q.get("correctIndex", 0),
        "explanation": q.get("explanation", ""),
        "eloRating": q.get("eloRating", 1000),
        "difficulty": q.get("difficulty", "easy"),
        "type": q.get("type", "mcq"),
        "referenceSolution": q.get("referenceSolution", "")
    }

    batch.set(doc_ref, prob_data, merge=True)
    count += 1
    total_seeded += 1

    if count == 400:
        batch.commit()
        print(f"Committed batch of {count} questions (Total: {total_seeded})")
        batch = db.batch()
        count = 0

if count > 0:
    batch.commit()
    print(f"Committed final batch of {count} questions (Total: {total_seeded})")

# Initialize skillRatings baseline for test users across all 15 topics
default_skills = {t["topicId"]: 1000 for t in topics_list}
for email in ["ali@devlingo.com", "sara@devlingo.com", "bilal@devlingo.com"]:
    users = list(db.collection("users").where("email", "==", email).stream())
    for u in users:
        db.collection("users").document(u.id).update({"skillRatings": default_skills})
        print(f"Initialized 15 topic skillRatings for user: {email}")

print("=== SEEDING COMPLETED SUCCESSFULLY ===")

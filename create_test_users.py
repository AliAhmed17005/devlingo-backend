import firebase_admin
from firebase_admin import credentials, auth, firestore

# 1. Initialize Firebase Admin SDK from serviceAccount.json
cred = credentials.Certificate("serviceAccount.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 3. Test Users Data
users_data = [
    {
        "displayName": "Ali Ahmed",
        "email": "ali@devlingo.com",
        "password": "Test123456",
        "tagId": "DV-001",
        "totalPoints": 0,
        "currentStreak": 0,
        "skillRatings": {
            "variables": 1000,
            "loops": 1000,
            "functions": 1000,
            "lists": 1000,
            "dictionaries": 1000,
            "files": 1000,
            "oop": 1000
        }
    },
    {
        "displayName": "Sara Khan",
        "email": "sara@devlingo.com",
        "password": "Test123456",
        "tagId": "DV-002",
        "totalPoints": 150,
        "currentStreak": 3,
        "skillRatings": {
            "variables": 1080,
            "loops": 950,
            "functions": 1100,
            "lists": 890,
            "dictionaries": 1020,
            "files": 970,
            "oop": 1060
        }
    },
    {
        "displayName": "Bilal Ahmed",
        "email": "bilal@devlingo.com",
        "password": "Test123456",
        "tagId": "DV-003",
        "totalPoints": 300,
        "currentStreak": 7,
        "skillRatings": {
            "variables": 1150,
            "loops": 1200,
            "functions": 1050,
            "lists": 1180,
            "dictionaries": 1090,
            "files": 1130,
            "oop": 1220
        }
    }
]

for user_info in users_data:
    try:
        # Create user in Firebase Auth
        user_record = auth.create_user(
            email=user_info["email"],
            password=user_info["password"],
            display_name=user_info["displayName"]
        )
    except auth.EmailAlreadyExistsError:
        print(f"{user_info['email']} already exists")
        continue
    except Exception as e:
        if "already exists" in str(e).lower() or "email_exists" in str(e).lower():
            print(f"{user_info['email']} already exists")
            continue
        else:
            print(f"Error creating {user_info['email']}: {e}")
            continue

    # 4. Write document to Firestore collection "users" using UID
    user_doc = {
        "name": user_info["displayName"],
        "email": user_info["email"],
        "tagId": user_info["tagId"],
        "currentLevel": "easy",
        "totalPoints": user_info["totalPoints"],
        "currentStreak": user_info["currentStreak"],
        "enrolledCourses": [{"courseId": "python-basics"}],
        "skillRatings": user_info["skillRatings"],
        "isPro": False,
        "bio": "",
        "location": "",
        "createdAt": firestore.SERVER_TIMESTAMP
    }

    db.collection("users").document(user_record.uid).set(user_doc)

    # 5. Print after each user
    print(f"Created: {user_info['displayName']} \u2014 UID: {user_record.uid} \u2014 Login: {user_info['email']} / Test123456")

# 6. Print at end
print("=== ALL TEST USERS READY ===")
print("Login at your Vercel URL with any of these:")
print("ali@devlingo.com / Test123456")
print("sara@devlingo.com / Test123456")
print("bilal@devlingo.com / Test123456")

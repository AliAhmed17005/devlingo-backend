import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccount.json")
app = firebase_admin.initialize_app(cred, name="seeder")
db = firestore.client(app)

# === COURSE ===
db.collection("courses").document("python-basics").set({
    "title": "Python Fundamentals",
    "description": "Learn Python from scratch with adaptive difficulty",
    "language": "python",
    "totalTopics": 7,
    "topics": [
        {"id":"variables",    "title":"Variables and Types",     "order":1, "icon":"\U0001f524"},
        {"id":"loops",        "title":"Loops and Iteration",     "order":2, "icon":"\U0001f504"},
        {"id":"functions",    "title":"Functions",               "order":3, "icon":"\u2699\ufe0f"},
        {"id":"lists",        "title":"Lists and Arrays",        "order":4, "icon":"\U0001f4cb"},
        {"id":"dictionaries", "title":"Dictionaries",            "order":5, "icon":"\U0001f4d6"},
        {"id":"files",        "title":"File Handling",           "order":6, "icon":"\U0001f4c1"},
        {"id":"oop",          "title":"Object Oriented Python",  "order":7, "icon":"\U0001f3d7\ufe0f"},
    ]
})
print("Created: Course python-basics")

problems = [
    # === VARIABLES ===
    {
        "title": "Variable Creation",
        "question": "What is the correct way to create a variable in Python?",
        "options": ["x = 5", "var x = 5", "int x = 5", "x := 5"],
        "correctAnswer": 0,
        "explanation": "Python uses simple assignment with = sign",
        "type": "mcq", "difficulty": "easy", "topicId": "variables", "eloRating": 1000
    },
    {
        "title": "Float Type Check",
        "question": "What will print(type(3.14)) output?",
        "options": ["<class 'int'>", "<class 'float'>", "<class 'double'>", "<class 'number'>"],
        "correctAnswer": 1,
        "explanation": "3.14 is a floating point number so type() returns float",
        "type": "mcq", "difficulty": "medium", "topicId": "variables", "eloRating": 1000
    },
    {
        "title": "Valid Python String",
        "question": "Which of these is a valid Python string?",
        "options": ["'Hello'", '"Hello"', 'He said "Hi"', "All of the above"],
        "correctAnswer": 3,
        "explanation": "Python accepts both single and double quotes and allows the other type inside",
        "type": "mcq", "difficulty": "medium", "topicId": "variables", "eloRating": 1000
    },
    {
        "title": "Type Converter",
        "description": "Write a function convert_types(val) that takes any value and returns a tuple of (int version, float version, string version) of that value. Example: convert_types(42) returns (42, 42.0, '42')",
        "starterCode": "def convert_types(val):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "variables", "eloRating": 1000
    },
    {
        "title": "Variable Swapper",
        "description": "Write a function swap_values(a, b) that returns a tuple with the values swapped without using a temporary variable. Example: swap_values(1, 2) returns (2, 1)",
        "starterCode": "def swap_values(a, b):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "variables", "eloRating": 1000
    },
    # === LOOPS ===
    {
        "title": "Range Function",
        "question": "What does range(5) produce?",
        "options": ["[0,1,2,3,4]", "[1,2,3,4,5]", "[0,5]", "[1,5]"],
        "correctAnswer": 0,
        "explanation": "range(5) produces numbers from 0 up to but not including 5",
        "type": "mcq", "difficulty": "easy", "topicId": "loops", "eloRating": 1000
    },
    {
        "title": "Range with Step",
        "question": "What is the output of: for i in range(2,10,3): print(i)",
        "options": ["2 5 8", "2 5 8 11", "2 4 6 8", "0 3 6 9"],
        "correctAnswer": 0,
        "explanation": "range(2,10,3) starts at 2, stops before 10, steps by 3: 2, 5, 8",
        "type": "mcq", "difficulty": "medium", "topicId": "loops", "eloRating": 1000
    },
    {
        "title": "Loop Exit",
        "question": "Which statement immediately exits a loop?",
        "options": ["exit", "stop", "break", "continue"],
        "correctAnswer": 2,
        "explanation": "break immediately terminates the loop and continues after it",
        "type": "mcq", "difficulty": "medium", "topicId": "loops", "eloRating": 1000
    },
    {
        "title": "Sum Even Numbers",
        "description": "Write a function sum_even(numbers) that returns the sum of all even numbers in a list. Example: sum_even([1,2,3,4,5,6]) returns 12",
        "starterCode": "def sum_even(numbers):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "loops", "eloRating": 1000
    },
    {
        "title": "Find Maximum",
        "description": "Write a function find_max(numbers) that returns the largest number in a list WITHOUT using the max() function. Example: find_max([3,1,4,1,5,9]) returns 9",
        "starterCode": "def find_max(numbers):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "loops", "eloRating": 1000
    },
    # === FUNCTIONS ===
    {
        "title": "Function Keyword",
        "question": "What keyword is used to define a function in Python?",
        "options": ["function", "def", "func", "define"],
        "correctAnswer": 1,
        "explanation": "Python uses 'def' keyword followed by the function name",
        "type": "mcq", "difficulty": "easy", "topicId": "functions", "eloRating": 1000
    },
    {
        "title": "No Return Value",
        "question": "What does a function return if it has no return statement?",
        "options": ["0", "False", "None", "An error"],
        "correctAnswer": 2,
        "explanation": "Python functions return None by default if no return statement is present",
        "type": "mcq", "difficulty": "medium", "topicId": "functions", "eloRating": 1000
    },
    {
        "title": "Default Parameters",
        "question": "What is a default parameter?",
        "options": ["A parameter that is required", "A parameter with a preset value", "A parameter that returns nothing", "A parameter that accepts any type"],
        "correctAnswer": 1,
        "explanation": "Default parameters have a value that is used when the argument is not provided",
        "type": "mcq", "difficulty": "medium", "topicId": "functions", "eloRating": 1000
    },
    {
        "title": "Factorial Calculator",
        "description": "Write a recursive function factorial(n) that returns n! (n factorial). Example: factorial(5) returns 120. Handle n=0 which should return 1.",
        "starterCode": "def factorial(n):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "functions", "eloRating": 1000
    },
    {
        "title": "FizzBuzz Function",
        "description": "Write a function fizzbuzz(n) that returns a list of strings from 1 to n where multiples of 3 are 'Fizz', multiples of 5 are 'Buzz', and multiples of both are 'FizzBuzz'. Example: fizzbuzz(5) returns ['1','2','Fizz','4','Buzz']",
        "starterCode": "def fizzbuzz(n):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "functions", "eloRating": 1000
    },
    # === LISTS ===
    {
        "title": "Adding to List",
        "question": "How do you add an item to the end of a list?",
        "options": ["list.add(item)", "list.push(item)", "list.append(item)", "list.insert(item)"],
        "correctAnswer": 2,
        "explanation": "The append() method adds an item to the end of a list",
        "type": "mcq", "difficulty": "easy", "topicId": "lists", "eloRating": 1000
    },
    {
        "title": "Negative Indexing",
        "question": "What does list[-1] return?",
        "options": ["An error", "The first element", "The last element", "None"],
        "correctAnswer": 2,
        "explanation": "Negative indexing in Python counts from the end, -1 is the last element",
        "type": "mcq", "difficulty": "medium", "topicId": "lists", "eloRating": 1000
    },
    {
        "title": "List Slicing",
        "question": "What is the output of: print([1,2,3][1:3])",
        "options": ["[1,2]", "[2,3]", "[1,2,3]", "[2]"],
        "correctAnswer": 1,
        "explanation": "Slicing [1:3] returns elements at index 1 and 2 (not including 3)",
        "type": "mcq", "difficulty": "medium", "topicId": "lists", "eloRating": 1000
    },
    {
        "title": "Remove Duplicates",
        "description": "Write a function remove_duplicates(lst) that returns a new list with all duplicate values removed while keeping the original order. Example: remove_duplicates([1,2,2,3,1,4]) returns [1,2,3,4]",
        "starterCode": "def remove_duplicates(lst):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "lists", "eloRating": 1000
    },
    {
        "title": "Flatten Nested List",
        "description": "Write a function flatten(nested) that takes a list of lists and returns a single flat list. Example: flatten([[1,2],[3,4],[5]]) returns [1,2,3,4,5]",
        "starterCode": "def flatten(nested):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "lists", "eloRating": 1000
    },
    # === DICTIONARIES ===
    {
        "title": "Dictionary Access",
        "question": "How do you access a value in a dictionary?",
        "options": ["dict.get_value(key)", "dict[key]", "dict.access(key)", "dict->key"],
        "correctAnswer": 1,
        "explanation": "Dictionary values are accessed using square brackets with the key",
        "type": "mcq", "difficulty": "easy", "topicId": "dictionaries", "eloRating": 1000
    },
    {
        "title": "Dict Get Method",
        "question": "What does dict.get('key', 'default') do if key does not exist?",
        "options": ["Raises KeyError", "Returns None", "Returns 'default'", "Returns empty string"],
        "correctAnswer": 2,
        "explanation": "The get() method returns the default value when the key is not found",
        "type": "mcq", "difficulty": "medium", "topicId": "dictionaries", "eloRating": 1000
    },
    {
        "title": "Dictionary Keys",
        "question": "How do you get all keys of a dictionary?",
        "options": ["dict.all_keys()", "dict.keys()", "dict.get_keys()", "list(dict)"],
        "correctAnswer": 1,
        "explanation": "The keys() method returns a view of all dictionary keys",
        "type": "mcq", "difficulty": "medium", "topicId": "dictionaries", "eloRating": 1000
    },
    {
        "title": "Word Counter",
        "description": "Write a function word_count(text) that takes a string and returns a dictionary where keys are words and values are how many times each word appears. Example: word_count('hello world hello') returns {'hello':2,'world':1}",
        "starterCode": "def word_count(text):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "dictionaries", "eloRating": 1000
    },
    {
        "title": "Dict Merger",
        "description": "Write a function merge_dicts(dict1, dict2) that merges two dictionaries. If a key exists in both, add the values together. Example: merge_dicts({'a':1,'b':2},{'b':3,'c':4}) returns {'a':1,'b':5,'c':4}",
        "starterCode": "def merge_dicts(dict1, dict2):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "dictionaries", "eloRating": 1000
    },
    # === FILES ===
    {
        "title": "File Read Mode",
        "question": "Which mode opens a file for reading in Python?",
        "options": ["'w'", "'r'", "'a'", "'x'"],
        "correctAnswer": 1,
        "explanation": "Mode 'r' opens a file for reading. It is the default mode.",
        "type": "mcq", "difficulty": "easy", "topicId": "files", "eloRating": 1000
    },
    {
        "title": "With Statement",
        "question": "What does the 'with' statement do when opening files?",
        "options": ["Reads faster", "Automatically closes the file", "Allows writing only", "Encrypts the file"],
        "correctAnswer": 1,
        "explanation": "The 'with' statement ensures the file is automatically closed even if an error occurs",
        "type": "mcq", "difficulty": "medium", "topicId": "files", "eloRating": 1000
    },
    {
        "title": "Readlines Method",
        "question": "What does file.readlines() return?",
        "options": ["A single string", "A list of lines", "The first line", "A dictionary"],
        "correctAnswer": 1,
        "explanation": "readlines() returns a list where each element is one line from the file",
        "type": "mcq", "difficulty": "medium", "topicId": "files", "eloRating": 1000
    },
    {
        "title": "Line Counter",
        "description": "Write a function count_lines(filename) that opens a file and returns the number of lines it contains. Return 0 if the file does not exist.",
        "starterCode": "def count_lines(filename):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "files", "eloRating": 1000
    },
    {
        "title": "Word Frequency File",
        "description": "Write a function top_words(filename, n) that reads a file and returns the n most common words as a list of tuples (word, count) sorted by count descending.",
        "starterCode": "def top_words(filename, n):\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "files", "eloRating": 1000
    },
    # === OOP ===
    {
        "title": "Class Keyword",
        "question": "What keyword creates a class in Python?",
        "options": ["object", "class", "struct", "type"],
        "correctAnswer": 1,
        "explanation": "Python uses the 'class' keyword to define a class",
        "type": "mcq", "difficulty": "easy", "topicId": "oop", "eloRating": 1000
    },
    {
        "title": "Init Method",
        "question": "What is the purpose of __init__ in a class?",
        "options": ["It deletes the object", "It is the constructor that initializes object attributes", "It is called when the class is imported", "It defines class methods"],
        "correctAnswer": 1,
        "explanation": "__init__ is the constructor method called automatically when an object is created",
        "type": "mcq", "difficulty": "medium", "topicId": "oop", "eloRating": 1000
    },
    {
        "title": "Self Reference",
        "question": "What does 'self' refer to in a class method?",
        "options": ["The class itself", "The current instance of the class", "The parent class", "The method name"],
        "correctAnswer": 1,
        "explanation": "'self' refers to the current instance (object) of the class",
        "type": "mcq", "difficulty": "medium", "topicId": "oop", "eloRating": 1000
    },
    {
        "title": "Bank Account Class",
        "description": "Create a class BankAccount with an __init__ that takes owner name and starting balance. Add methods deposit(amount), withdraw(amount) (reject if insufficient funds returning False), and get_balance(). Example: acc = BankAccount('Ali', 1000); acc.deposit(500); acc.get_balance() returns 1500",
        "starterCode": "class BankAccount:\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "oop", "eloRating": 1000
    },
    {
        "title": "Student Grade Class",
        "description": "Create a class Student with __init__ taking name. Add method add_grade(subject, score), get_average() returning average of all grades, and get_highest() returning the subject with the highest score as a tuple (subject, score).",
        "starterCode": "class Student:\n    pass",
        "type": "coding", "difficulty": "hard", "topicId": "oop", "eloRating": 1000
    },
]

count = 0
for p in problems:
    db.collection("problems").add(p)
    count += 1
    print(f"Created: {p['title']}")

print(f"\nDONE: {count} problems created")

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from firebase_admin import firestore
import ast, subprocess, tempfile, os, sys, time
import google.generativeai as genai

router = APIRouter(prefix="/codehealth")
db     = firestore.client()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
llm = genai.GenerativeModel("gemini-1.5-flash")

def get_complexity(tree):
    results = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            count = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.For, ast.While,
                                      ast.ExceptHandler, ast.BoolOp, ast.Try)):
                    count += 1
            results[node.name] = {
                "complexity": count,
                "line":       node.lineno,
                "risk":       "low" if count <= 5 else "medium" if count <= 10 else "high"
            }
    return results

def detect_antipatterns(tree):
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            for child in ast.walk(node):
                if (child is not node and isinstance(child, ast.AugAssign)
                        and isinstance(child.op, ast.Add)):
                    issues.append({
                        "type":     "string_concat_in_loop",
                        "line":     getattr(child, "lineno", 0),
                        "severity": "medium",
                        "message":  "String concatenation inside loop -- use join() instead",
                        "fix":      "Collect items in a list then use ''.join(list)"
                    })
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({
                "type":     "bare_except",
                "line":     node.lineno,
                "severity": "high",
                "message":  "Bare except clause catches everything including crashes",
                "fix":      "Use 'except Exception as e:' or a specific exception type"
            })
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append({
                        "type":     "mutable_default_arg",
                        "line":     node.lineno,
                        "severity": "high",
                        "message":  f"Mutable default argument in {node.name}() shared across all calls",
                        "fix":      "Use None as default then assign inside the function"
                    })
            if len(node.args.args) > 5:
                issues.append({
                    "type":     "too_many_params",
                    "line":     node.lineno,
                    "severity": "low",
                    "message":  f"{node.name}() has {len(node.args.args)} parameters -- consider a dataclass",
                    "fix":      "Group related parameters into a dictionary or dataclass"
                })
        if isinstance(node, ast.For):
            for child in ast.walk(node):
                if child is not node and isinstance(child, ast.For):
                    issues.append({
                        "type":     "nested_loops",
                        "line":     node.lineno,
                        "severity": "medium",
                        "message":  "Nested loops detected -- possible O(n^2) performance issue",
                        "fix":      "Consider using a dictionary for the inner lookup"
                    })
                    break
    return issues

@router.post("/analyze")
async def analyze_code(file: UploadFile = File(...), user_id: str = "anonymous"):
    try:
        content  = await file.read()
        code_str = content.decode("utf-8")
        lines    = code_str.splitlines()

        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            return JSONResponse(status_code=400,
                content={"error": f"Syntax error at line {e.lineno}: {e.msg}"})

        complexity   = get_complexity(tree)
        antipatterns = detect_antipatterns(tree)

        with tempfile.NamedTemporaryFile(
                suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
            f.write(code_str)
            tmp_path = f.name

        style_issues = []
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pycodestyle",
                 "--max-line-length=100", tmp_path],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split("\n"):
                if line and ":" in line:
                    parts = line.split(":")
                    if len(parts) >= 4:
                        style_issues.append({
                            "line":    parts[1].strip(),
                            "message": ":".join(parts[3:]).strip()
                        })
        except Exception:
            pass

        performance = {}
        try:
            prof = subprocess.run(
                [sys.executable, "-m", "cProfile",
                 "-s", "cumulative", tmp_path],
                capture_output=True, text=True, timeout=5
            )
            output_lines = [l for l in prof.stdout.split("\n") if l.strip()]
            performance  = {"profile": "\n".join(output_lines[:8])}
        except subprocess.TimeoutExpired:
            performance = {"note": "Execution timed out"}
        except Exception:
            performance = {"note": "Could not profile"}

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        high_count = sum(1 for a in antipatterns if a["severity"] == "high")
        med_count  = sum(1 for a in antipatterns if a["severity"] == "medium")
        high_comp  = sum(1 for v in complexity.values() if v["risk"] == "high")
        style_pen  = min(len(style_issues), 20)
        score      = max(0, 100 - high_count*10 - med_count*5 - high_comp*8 - style_pen)
        grade      = "A" if score>=85 else "B" if score>=70 else "C" if score>=55 else "D"

        findings = (
            f"File: {file.filename} ({len(lines)} lines)\n"
            f"Score: {score}/100 Grade: {grade}\n"
            f"Complexity: {complexity}\n"
            f"Anti-patterns: {[i['message'] for i in antipatterns]}\n"
            f"Style issues: {len(style_issues)}"
        )
        try:
            newline = chr(10)
            suggestions = llm.generate_content(
                f"You are a senior Python code reviewer.\n"
                f"Based on these computed analysis findings:\n{findings}\n\n"
                f"And the first 60 lines of code:\n"
                f"```python\n{newline.join(lines[:60])}\n```\n\n"
                f"Give exactly 3 numbered refactoring suggestions.\n"
                f"Each must reference a specific function name or line number from the findings.\n"
                f"Be specific and actionable. Max 200 words total."
            ).text.strip()
        except Exception:
            suggestions = "Run your code through pylint for detailed suggestions."

        result_data = {
            "filename":     file.filename,
            "total_lines":  len(lines),
            "overall_score":score,
            "grade":        grade,
            "complexity":   complexity,
            "antipatterns": antipatterns,
            "style_issues": style_issues[:10],
            "performance":  performance,
            "llm_suggestions": suggestions,
            "timestamp":    time.time()
        }

        if user_id != "anonymous":
            try:
                db.collection("users").document(user_id)\
                    .collection("codeAnalysis").add(result_data)
            except Exception:
                pass

        return result_data

    except Exception as e:
        return JSONResponse(status_code=500,
            content={"error": str(e)})

@router.get("/history/{user_id}")
def analysis_history(user_id: str):
    try:
        analyses = db.collection("users").document(user_id)\
            .collection("codeAnalysis")\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)\
            .limit(5).stream()
        return {"analyses": [a.to_dict() for a in analyses]}
    except Exception:
        return {"analyses": []}

import json
import os
import subprocess
import sys

d = json.load(sys.stdin)
f = d.get("tool_input", {}).get("file_path", "")
f_norm = f.replace(chr(92), "/")
project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").replace(chr(92), "/")

if not (f_norm.startswith(project_dir + "/backend/") and f_norm.endswith(".py")):
    sys.exit(0)

cwd = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", ""), "backend")
result = subprocess.run(
    ["uv", "run", "ruff", "check", "--fix", f],
    cwd=cwd,
    capture_output=True,
    text=True,
)
subprocess.run(["uv", "run", "ruff", "format", f], cwd=cwd)

if result.returncode != 0:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": f"Ruff found issues in {f}:\n{result.stdout}{result.stderr}",
                }
            }
        )
    )

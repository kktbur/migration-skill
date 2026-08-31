import json
import subprocess
import sys


request = json.load(sys.stdin)
completed = subprocess.run(
    ["node", "cli.js", *request["input"]["argv"]],
    capture_output=True,
    text=True,
    check=False,
)
try:
    stdout = json.loads(completed.stdout)
except json.JSONDecodeError:
    stdout = completed.stdout
print(json.dumps({
    "status": "passed",
    "observed": {"exit_code": completed.returncode, "stdout": stdout},
}, sort_keys=True))

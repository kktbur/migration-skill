"""Portable adapter for the source side of the blind benchmark."""

from __future__ import annotations

import json
import subprocess
import sys


request = json.load(sys.stdin)
completed = subprocess.run(
    [sys.executable, "cli.py", *request["input"]["argv"]],
    capture_output=True,
    text=True,
    check=False,
)
try:
    stdout: object = json.loads(completed.stdout)
except json.JSONDecodeError:
    stdout = completed.stdout
print(json.dumps({
    "status": "passed",
    "observed": {"exit_code": completed.returncode, "stdout": stdout},
}, ensure_ascii=False, sort_keys=True))

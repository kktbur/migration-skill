"""Portable target adapter for the Python-to-Node host dogfood run."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


request = json.load(sys.stdin)
node = shutil.which("node") or "node"
completed = subprocess.run(
    [node, "cli.js", *request["input"]["argv"]],
    capture_output=True,
    text=True,
    check=False,
)
try:
    stdout: object = json.loads(completed.stdout)
except json.JSONDecodeError:
    stdout = completed.stdout
print(
    json.dumps(
        {
            "status": "passed",
            "observed": {"exit_code": completed.returncode, "stdout": stdout},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)

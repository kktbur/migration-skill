"""Flask test-client adapter for the portable parity protocol."""

from __future__ import annotations

import json
import sys

from app import app


request = json.load(sys.stdin)
payload = request["input"]
with app.test_client() as client:
    response = client.open(
        path=payload["path"],
        method=payload["method"],
        json=payload.get("json"),
    )
    observed = {"status": response.status_code, "body": response.get_json(silent=True)}
print(json.dumps({"status": "passed", "observed": observed}, ensure_ascii=False, sort_keys=True))

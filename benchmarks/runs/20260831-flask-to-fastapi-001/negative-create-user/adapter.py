"""Flask test-client adapter for the portable parity protocol."""

from __future__ import annotations

import json
import sys

from app import app


def main() -> None:
    request_document = json.load(sys.stdin)
    payload = request_document["input"]
    kwargs: dict[str, object] = {}
    if "query" in payload:
        kwargs["query_string"] = payload["query"]
    if "json" in payload:
        kwargs["json"] = payload["json"]
    elif "body" in payload:
        kwargs["data"] = payload["body"]
        if payload.get("content_type"):
            kwargs["content_type"] = payload["content_type"]

    with app.test_client() as client:
        response = client.open(
            path=payload["path"],
            method=payload["method"],
            **kwargs,
        )
        observed = {
            "status": response.status_code,
            "body": response.get_json(silent=True),
            "content_type": response.content_type,
        }

    print(
        json.dumps(
            {"status": "passed", "observed": observed},
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""FastAPI test-client adapter for the portable parity protocol."""

from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

from app import app


def main() -> None:
    request_document = json.load(sys.stdin)
    payload = request_document["input"]
    request_kwargs: dict[str, object] = {}
    if "query" in payload:
        request_kwargs["params"] = payload["query"]
    if "json" in payload:
        request_kwargs["json"] = payload["json"]
    elif "body" in payload:
        request_kwargs["content"] = payload["body"]
        if payload.get("content_type"):
            request_kwargs["headers"] = {"content-type": payload["content_type"]}

    with TestClient(app) as client:
        response = client.request(
            method=payload["method"],
            url=payload["path"],
            **request_kwargs,
        )
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        observed = {
            "status": response.status_code,
            "body": body,
            "content_type": response.headers.get("content-type"),
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

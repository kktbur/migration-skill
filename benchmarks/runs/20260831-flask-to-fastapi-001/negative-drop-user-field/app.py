"""Small Flask application used by the blind Flask-to-FastAPI benchmark."""

from __future__ import annotations

from typing import Any

from werkzeug.exceptions import HTTPException

from flask import Flask, Response, jsonify, request


app = Flask(__name__)

INITIAL_USERS: dict[int, dict[str, Any]] = {
    1: {"id": 1, "name": "Ada", "age": 36},
    2: {"id": 2, "name": "Bob", "age": 41},
    3: {"id": 3, "name": "Cara", "age": 29},
    4: {"id": 4, "name": "张三", "age": 28},
}
USERS: dict[int, dict[str, Any]] = {}


def reset_store() -> None:
    """Reset the in-memory store so every public test starts from one state."""

    USERS.clear()
    USERS.update({user_id: dict(user) for user_id, user in INITIAL_USERS.items()})


def _error(message: str, status: int, **extra: Any):
    return jsonify({"error": message, **extra}), status


@app.errorhandler(HTTPException)
def handle_http_error(error: HTTPException):
    if error.code == 404:
        return _error("route not found", 404, path=request.path)
    return _error(
        (error.name or "http error").lower().replace(" ", "_"),
        error.code or 500,
        path=request.path,
    )


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "migration-demo", "version": 1})


@app.get("/users/<int:user_id>")
def get_user(user_id: int):
    user = USERS.get(user_id)
    if user is None:
        return _error("user not found", 404, id=user_id)
    return jsonify({"id": user["id"], "age": user["age"]})


@app.post("/users")
def create_user():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("invalid json", 400)

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return _error("name required", 400, field="name")
    name = name.strip()

    age = payload.get("age", 0)
    if isinstance(age, bool) or not isinstance(age, int):
        return _error("age must be integer", 400, field="age")

    if any(user["name"].casefold() == name.casefold() for user in USERS.values()):
        return _error("user exists", 409, name=name)

    user_id = max(USERS, default=0) + 1
    user = {"id": user_id, "name": name, "age": age}
    USERS[user_id] = user
    return jsonify(user), 201


@app.delete("/users/<int:user_id>")
def delete_user(user_id: int):
    if user_id not in USERS:
        return _error("user not found", 404, id=user_id)
    del USERS[user_id]
    response = Response(status=204)
    response.headers.pop("Content-Type", None)
    return response


@app.get("/search")
def search_users():
    query = request.args.get("q")
    if query is None or not query:
        return _error("query required", 400, field="q")

    folded_query = query.casefold()
    items = [
        user
        for user_id, user in sorted(USERS.items())
        if folded_query in user["name"].casefold()
    ]
    return jsonify({"query": query, "count": len(items), "items": items})


reset_store()

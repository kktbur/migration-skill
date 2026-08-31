"""FastAPI target generated for the blind Flask-to-FastAPI benchmark."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


app = FastAPI()

INITIAL_USERS: dict[int, dict[str, Any]] = {
    1: {"id": 1, "name": "Ada", "age": 36},
    2: {"id": 2, "name": "Bob", "age": 41},
    3: {"id": 3, "name": "Cara", "age": 29},
    4: {"id": 4, "name": "张三", "age": 28},
}
USERS: dict[int, dict[str, Any]] = {}


def reset_store() -> None:
    USERS.clear()
    USERS.update({user_id: dict(user) for user_id, user in INITIAL_USERS.items()})


def _error(message: str, status: int, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": message, **extra},
    )


def _parse_user_id(raw_user_id: str) -> int | None:
    try:
        return int(raw_user_id)
    except ValueError:
        return None


@app.get("/health")
def health():
    return {"ok": True, "service": "migration-demo", "version": 1}


@app.get("/users/{user_id}")
def get_user(user_id: str):
    parsed_id = _parse_user_id(user_id)
    if parsed_id is None:
        return _error("route not found", 404, path=f"/users/{user_id}")

    user = USERS.get(parsed_id)
    if user is None:
        return _error("user not found", 404, id=parsed_id)
    return {"id": user["id"], "age": user["age"]}


@app.post("/users")
async def create_user(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        return _error("invalid json", 400)
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
    return JSONResponse(status_code=201, content=user)


@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    parsed_id = _parse_user_id(user_id)
    if parsed_id is None:
        return _error("route not found", 404, path=f"/users/{user_id}")
    if parsed_id not in USERS:
        return _error("user not found", 404, id=parsed_id)

    del USERS[parsed_id]
    response = Response(status_code=204)
    if "content-type" in response.headers:
        del response.headers["content-type"]
    return response


@app.get("/search")
def search_users(q: str | None = None):
    if q is None or not q:
        return _error("query required", 400, field="q")

    folded_query = q.casefold()
    items = [
        user
        for user_id, user in sorted(USERS.items())
        if folded_query in user["name"].casefold()
    ]
    return {"query": q, "count": len(items), "items": items}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def route_not_found(path: str):
    return _error("route not found", 404, path=f"/{path}")


reset_store()

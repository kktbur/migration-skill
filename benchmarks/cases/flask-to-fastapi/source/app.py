"""Small Flask application used by the Flask-to-FastAPI blind case."""

from flask import Flask, jsonify, request


app = Flask(__name__)
USERS = {1: {"id": 1, "name": "Ada"}}


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/users/<int:user_id>")
def get_user(user_id: int):
    user = USERS.get(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404
    return jsonify(user)


@app.post("/users")
def create_user():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        return jsonify({"error": "name required"}), 400
    user_id = max(USERS) + 1
    user = {"id": user_id, "name": name}
    USERS[user_id] = user
    return jsonify(user), 201

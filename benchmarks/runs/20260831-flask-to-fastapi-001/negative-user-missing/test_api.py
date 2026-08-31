"""Public HTTP behavior tests for the Flask source implementation."""

from __future__ import annotations

import unittest

from app import app, reset_store


class ApiTest(unittest.TestCase):
    def setUp(self):
        app.testing = True
        reset_store()
        self.client = app.test_client()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"ok": True, "service": "migration-demo", "version": 1},
        )

    def test_user_found(self):
        response = self.client.get("/users/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"id": 1, "name": "Ada", "age": 36})

    def test_user_missing(self):
        response = self.client.get("/users/999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "user not found", "id": 999})

    def test_user_invalid_id_uses_json_route_error(self):
        response = self.client.get("/users/not-an-int")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json(),
            {"error": "route not found", "path": "/users/not-an-int"},
        )

    def test_search_normal(self):
        response = self.client.get("/search?q=a")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "query": "a",
                "count": 2,
                "items": [
                    {"id": 1, "name": "Ada", "age": 36},
                    {"id": 3, "name": "Cara", "age": 29},
                ],
            },
        )

    def test_search_empty(self):
        response = self.client.get("/search?q=")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(), {"error": "query required", "field": "q"}
        )

    def test_search_unicode(self):
        response = self.client.get("/search?q=张")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "query": "张",
                "count": 1,
                "items": [{"id": 4, "name": "张三", "age": 28}],
            },
        )

    def test_search_no_match(self):
        response = self.client.get("/search?q=zzz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(), {"query": "zzz", "count": 0, "items": []}
        )

    def test_create_user(self):
        response = self.client.post("/users", json={"name": "Lin", "age": 30})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json(), {"id": 5, "name": "Lin", "age": 30}
        )

    def test_create_no_age_defaults_to_zero(self):
        response = self.client.post("/users", json={"name": "NoAge"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json(), {"id": 5, "name": "NoAge", "age": 0}
        )

    def test_create_missing_name(self):
        response = self.client.post("/users", json={"age": 30})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(), {"error": "name required", "field": "name"}
        )

    def test_create_empty_name(self):
        response = self.client.post("/users", json={"name": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(), {"error": "name required", "field": "name"}
        )

    def test_create_whitespace_name(self):
        response = self.client.post("/users", json={"name": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(), {"error": "name required", "field": "name"}
        )

    def test_create_invalid_age(self):
        response = self.client.post(
            "/users", json={"name": "AgeText", "age": "old"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(), {"error": "age must be integer", "field": "age"}
        )

    def test_create_bool_age_is_rejected(self):
        response = self.client.post(
            "/users", json={"name": "BoolAge", "age": True}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(), {"error": "age must be integer", "field": "age"}
        )

    def test_create_null_name(self):
        response = self.client.post("/users", json={"name": None})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(), {"error": "name required", "field": "name"}
        )

    def test_create_invalid_json(self):
        response = self.client.post(
            "/users", data="not-json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "invalid json"})

    def test_create_duplicate_name_is_case_insensitive(self):
        response = self.client.post("/users", json={"name": "ada", "age": 36})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json(), {"error": "user exists", "name": "ada"}
        )

    def test_delete_existing_returns_empty_204(self):
        response = self.client.delete("/users/2")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.data, b"")
        self.assertIsNone(response.content_type)

    def test_delete_missing(self):
        response = self.client.delete("/users/999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "user not found", "id": 999})

    def test_delete_invalid_id_uses_json_route_error(self):
        response = self.client.delete("/users/not-an-int")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json(),
            {"error": "route not found", "path": "/users/not-an-int"},
        )


if __name__ == "__main__":
    unittest.main()

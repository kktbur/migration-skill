from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app import app, reset_store


class ReadApiTest(unittest.TestCase):
    def setUp(self):
        reset_store()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_user_found(self):
        response = self.client.get("/users/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": 1, "name": "Ada", "age": 36})

    def test_user_missing(self):
        response = self.client.get("/users/999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "user not found", "id": 999})

    def test_user_invalid_id(self):
        response = self.client.get("/users/not-an-int")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"error": "route not found", "path": "/users/not-an-int"},
        )

    def test_search_normal(self):
        response = self.client.get("/search?q=a")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual(
            response.json()["items"],
            [
                {"id": 1, "name": "Ada", "age": 36},
                {"id": 3, "name": "Cara", "age": 29},
            ],
        )

    def test_search_empty(self):
        response = self.client.get("/search?q=")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"error": "query required", "field": "q"}
        )

    def test_search_unicode(self):
        response = self.client.get("/search?q=张")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"],
            [{"id": 4, "name": "张三", "age": 28}],
        )

    def test_search_no_match(self):
        response = self.client.get("/search?q=zzz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"query": "zzz", "count": 0, "items": []})


if __name__ == "__main__":
    unittest.main()

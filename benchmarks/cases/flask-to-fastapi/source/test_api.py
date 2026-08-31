from __future__ import annotations

import unittest

from app import app


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_and_user_lookup(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/users/1").get_json()["name"], "Ada")
        self.assertEqual(self.client.get("/users/999").status_code, 404)

    def test_create_validation(self):
        created = self.client.post("/users", json={"name": "Lin"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/users", json={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()

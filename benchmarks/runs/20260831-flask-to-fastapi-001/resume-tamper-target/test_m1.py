from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app import app


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "service": "migration-demo", "version": 1},
        )


if __name__ == "__main__":
    unittest.main()

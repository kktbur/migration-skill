from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CliTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "cli.py", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_normal_json_and_text(self):
        normal = self.run_cli("--name", "Ada")
        text = self.run_cli("--name", "Ada", "--format", "text")
        self.assertEqual(normal.returncode, 0)
        self.assertEqual(json.loads(normal.stdout), {"greeting": "hello Ada"})
        self.assertEqual(text.returncode, 0)
        self.assertEqual(text.stdout.strip(), "hello Ada")

    def test_error_boundary_unicode_and_uppercase(self):
        empty = self.run_cli("--name", "")
        invalid = self.run_cli("--unknown")
        unicode_name = self.run_cli("--name", "张三")
        uppercase = self.run_cli("--name", "Ada", "--uppercase")
        self.assertEqual(empty.returncode, 2)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(json.loads(unicode_name.stdout), {"greeting": "hello 张三"})
        self.assertEqual(json.loads(uppercase.stdout), {"greeting": "hello ADA"})


if __name__ == "__main__":
    unittest.main()

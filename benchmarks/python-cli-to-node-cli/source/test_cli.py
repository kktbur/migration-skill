import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "cli.py", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_hello(self):
        result = self.run_cli("--name", "Ada")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"greeting": "hello Ada"})

    def test_boundary_and_error(self):
        empty = self.run_cli("--name", "")
        invalid = self.run_cli("--unknown")
        self.assertEqual(empty.returncode, 2)
        self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main()

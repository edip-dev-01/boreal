"""Infrastructure source checks; these do not replace a Docker smoke test."""
from pathlib import Path
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupEnvironmentTests(unittest.TestCase):
    def test_generates_distinct_credentials_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            shutil.copy(ROOT / "scripts/setup_env.py", root / "scripts/setup_env.py")
            first = subprocess.run([sys.executable, str(root / "scripts/setup_env.py")], capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            env_path = root / ".env"
            content = env_path.read_text()
            credentials = re.findall(r"^DB_\w+_PASSWORD=([0-9a-f]+)$", content, flags=re.MULTILINE)
            self.assertEqual(len(credentials), 3)
            self.assertEqual(len(set(credentials)), 3)
            self.assertTrue(all(len(value) == 64 for value in credentials))
            self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)
            self.assertTrue(all(value not in first.stdout for value in credentials))
            second = subprocess.run([sys.executable, str(root / "scripts/setup_env.py")], capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(env_path.read_text(), content)

    def test_example_has_no_password_values(self):
        content = (ROOT / ".env.example").read_text()
        values = re.findall(r"^DB_\w+_PASSWORD=(.*)$", content, flags=re.MULTILINE)
        self.assertEqual(values, ["", "", ""])

    def test_runtime_services_separate_principals(self):
        compose = (ROOT / "compose.yaml").read_text()
        self.assertIn('127.0.0.1:${BOREAL_PORT:-8080}:8080', compose)
        self.assertIn('postgresql://edip_app:', compose)
        self.assertIn('postgresql://edip_ingest:', compose)
        self.assertIn('condition: service_completed_successfully', compose)
        self.assertIn('"--workers", "1"', compose)
        self.assertNotIn('app.testing:app', compose)

    def test_public_safe_scan(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/check_public_safe.py")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

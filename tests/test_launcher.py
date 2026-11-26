import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class LauncherTests(unittest.TestCase):
    def test_host_selection(self):
        script = Path(__file__).resolve().parent.parent / "run.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run.sh").write_bytes(script.read_bytes())
            python = root / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nif [ "$1" = "-m" ] && [ "$2" = "uvicorn" ]; then printf "ARGS:%s\\n" "$*"; fi\n')
            python.chmod(0o755)
            env = os.environ.copy()
            env.pop("HOST", None)
            env["PORT"] = "17860"
            result = subprocess.run(["bash", str(root / "run.sh")], env=env, text=True, capture_output=True, check=True)
            self.assertIn("--host 127.0.0.1 --port 17860", result.stdout)
            env["HOST"] = "0.0.0.0"
            result = subprocess.run(["bash", str(root / "run.sh")], env=env, text=True, capture_output=True, check=True)
            self.assertIn("--host 0.0.0.0 --port 17860", result.stdout)
            self.assertIn("<IP-do-computador>:17860", result.stdout)
            self.assertIn("não exige autenticação", result.stderr)


if __name__ == "__main__":
    unittest.main()

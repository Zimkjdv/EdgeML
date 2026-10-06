import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows batch launcher')
class PredictionLauncherTests(unittest.TestCase):
    def setUp(self):
        if not (ROOT / 'backend/.venv/Scripts/python.exe').exists():
            self.skipTest('Set up backend/.venv before exercising the launcher')

    def invoke(self, arguments):
        # Help and invalid arguments exit before credentials, API or DB access.
        # Pass a native cmd command line, avoiding list2cmdline's C-runtime quote
        # escaping (cmd.exe does not use that escaping for /c commands).
        command = f'cmd.exe /d /s /c ""{ROOT / "run-piapifd-prediction.bat"}" {arguments}"'
        return subprocess.run(command,
            cwd=os.environ.get('SystemRoot', 'C:/Windows'),
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

    def test_help_works_outside_project_directory_without_running_prediction(self):
        result = self.invoke('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('local API 8000', result.stdout)
        self.assertIn('piapifd_prediction.ini', result.stdout)
        self.assertIn('--feature-aliases', result.stdout)
        self.assertNotIn('EdgeML API token:', result.stdout)
        self.assertNotIn('"completed": true', result.stdout)

    def test_python_argument_failure_is_propagated_without_db_access(self):
        result = self.invoke('--batch-size 0')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Batch size must be 1..10000', result.stderr)
        self.assertIn('[ERROR] Prediction stopped', result.stdout)


if __name__ == '__main__':
    unittest.main()

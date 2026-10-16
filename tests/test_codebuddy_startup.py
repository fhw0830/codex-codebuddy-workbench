import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.agents import CodeBuddy, resolve_runtimes


class FailedInput:
    def write(self, value):
        raise BrokenPipeError(32, 'Broken pipe')


class ExitedProcess:
    stdin = FailedInput()
    stdout = io.StringIO('')
    stderr = io.StringIO("Error: Cannot find module 'missing-codebuddy'\ncode: MODULE_NOT_FOUND\n")

    def poll(self):
        return 1


class CodeBuddyStartup(unittest.TestCase):
    def test_failed_cli_is_not_reported_as_ready_with_fallback_model(self):
        failed = subprocess.CompletedProcess([], 1, '', 'Error: Cannot find module codebuddy')
        with tempfile.TemporaryDirectory() as folder, patch('backend.agents.subprocess.run', return_value=failed):
            with self.assertRaisesRegex(RuntimeError, 'Cannot find module'):
                CodeBuddy({'node': 'node', 'codebuddy': 'missing'}, Path(folder)).models()

    def test_unrecognized_help_does_not_invent_a_model(self):
        unknown = subprocess.CompletedProcess([], 0, 'Unsupported CLI help', '')
        with tempfile.TemporaryDirectory() as folder, patch('backend.agents.subprocess.run', return_value=unknown):
            with self.assertRaisesRegex(RuntimeError, '未取得可选模型列表'):
                CodeBuddy({'node': 'node', 'codebuddy': 'cli'}, Path(folder)).models()

    def test_broken_input_reports_the_actual_startup_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch('backend.agents.spawn', return_value=ExitedProcess()):
            with self.assertRaisesRegex(RuntimeError, 'MODULE_NOT_FOUND'):
                CodeBuddy({'node': 'node', 'codebuddy': 'cli'}, Path(folder)).run(
                    'x' * 20000, 'model', lambda text: None, threading.Event(), full_access=True)

    def test_registered_physical_runtime_is_used_outside_packaged_app(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'CODEBUDDY_CLI_PATH': ''}):
            root = Path(folder)
            (root / 'runtime-manifest.json').write_text(json.dumps({'runtime': {'path': str(root / 'real-cache')}}))
            self.assertEqual(resolve_runtimes(root)['codebuddy'], str(root / 'real-cache/bin/codebuddy'))
            (root / 'config.local.json').write_text(json.dumps({'codebuddy': 'explicit-cli'}))
            self.assertEqual(resolve_runtimes(root)['codebuddy'], 'explicit-cli')


if __name__ == '__main__':
    unittest.main()

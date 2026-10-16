"""Run browser-helper unit tests using Node; no network or real agents."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
node = shutil.which('node')
if not node:
    raise SystemExit('Node.js must be on PATH to run JavaScript tests')
tests = sorted((root/'tests').glob('test_*.cjs'))
failed = []
for test in tests:
    result = subprocess.run([node, str(test)], cwd=root, timeout=30)
    if result.returncode:
        failed.append(test.name)
print(f'JavaScript test groups: {len(tests) - len(failed)}/{len(tests)} passed', flush=True)
if failed:
    print('Failed: ' + ', '.join(failed))
    sys.exit(1)

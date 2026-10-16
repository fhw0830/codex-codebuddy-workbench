"""Run the local service with persistent logs, independent of its launcher."""
import os
import contextlib
import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    data = root / 'data'
    data.mkdir(exist_ok=True)
    os.chdir(root)
    sys.path.insert(0, str(root))
    with (data / 'server.stdout.log').open('a', encoding='utf-8', buffering=1) as out, \
            (data / 'server.stderr.log').open('a', encoding='utf-8', buffering=1) as err, \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        stamp = datetime.now().astimezone().isoformat(timespec='seconds')
        print(f'[{stamp}] service starting pid={os.getpid()}', flush=True)
        sys.argv = [str(root / 'server.py'), '--port', '8766']
        try:
            runpy.run_path(str(root / 'server.py'), run_name='__main__')
        except BaseException:
            traceback.print_exc(file=err)
            raise
        finally:
            print(f'[{datetime.now().astimezone().isoformat(timespec="seconds")}] service exited pid={os.getpid()}', flush=True)


if __name__ == '__main__':
    main()

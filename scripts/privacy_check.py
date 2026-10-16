"""Check public source candidates without printing matched confidential values.

This is a publication aid, not a guarantee. Review staged changes as well.
Synthetic credential literals in tests are intentional regression fixtures.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {'.git', 'data', '__pycache__', 'node_modules', '.venv', 'venv', 'artifacts'}
PRIVATE_NAMES = {'config.local.json', 'runtime-manifest.json', 'auth.json', 'credentials.json', '.env'}
PRIVATE_SUFFIXES = {'.sqlite', '.sqlite3', '.db', '.log', '.pem', '.key', '.p12', '.pfx'}
TOKEN = re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b')
USER_PATH = re.compile(r'(?i)(?:[a-z]:[\\/]+Users[\\/]+(?!example(?:[\\/]|$)|USERNAME(?:[\\/]|$)|user(?:[\\/]|$)|<)[^\\/\s"\']+|/home/(?!example/|user/)[a-z0-9_-]+/)')
IP = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')


def candidate_files(tracked=False):
    if tracked:
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
        return [ROOT/p.decode('utf-8') for p in result.stdout.split(b'\0') if p]
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not (set(p.relative_to(ROOT).parts) & IGNORED))


def scan(path):
    relative = path.relative_to(ROOT)
    findings = []
    if path.name in PRIVATE_NAMES or path.name.startswith('.env.') or path.suffix.lower() in PRIVATE_SUFFIXES:
        findings.append({'path': relative.as_posix(), 'kind': 'private runtime/config/binary file'})
    if 'data' in relative.parts or 'artifacts' in relative.parts:
        findings.append({'path': relative.as_posix(), 'kind': 'runtime data directory'})
    if path.suffix.lower() in {'.png', '.jpg', '.gif', '.ico', '.woff2'}:
        return findings
    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        return findings + [{'path': relative.as_posix(), 'kind': 'unreviewed binary file'}]
    synthetic = relative.parts[0] == 'tests'
    for number, line in enumerate(text.splitlines(), 1):
        kinds = []
        if USER_PATH.search(line):
            kinds.append('machine-specific user path')
        if not synthetic and TOKEN.search(line):
            kinds.append('credential-like token')
        if not synthetic and re.search(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----', line):
            kinds.append('private key block')
        for raw in IP.findall(line):
            try:
                address = ipaddress.ip_address(raw)
            except ValueError:
                continue
            if not address.is_loopback and (raw.startswith('10.') or raw.startswith('192.168.') or raw.startswith('172.') and 16 <= int(raw.split('.')[1]) <= 31):
                kinds.append('private network address')
        for kind in set(kinds):
            findings.append({'path': relative.as_posix(), 'line': number, 'kind': kind})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracked', action='store_true', help='Scan exactly the Git tracked files, including forbidden ones')
    args = parser.parse_args()
    files = candidate_files(args.tracked)
    findings = [finding for path in files for finding in scan(path)]
    print(json.dumps({'files_checked': len(files), 'findings': findings}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(findings))


if __name__ == '__main__':
    main()

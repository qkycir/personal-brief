#!/usr/bin/env python3
"""Check publication candidates for accidental private files and broken local links.

This is a lightweight release check, not a complete secret detector or history audit.
Only file locations and rule names are printed on failure, never matched values.
"""
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_NAMES = {'config.md', 'preferences.md', '个人信息.md', 'user-facts.md',
                 'mail-accounts.json', 'events.md', 'tasks.md', 'source-state.md',
                 'profile.md', 'focus.md', 'status.md', 'mail-processed.md'}
PRIVATE_DIRS = {'private', 'data', 'mail-cache', 'runs', 'run.lock'}
RULES = {
    'absolute personal home path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}'),
    'configured thread identifier': re.compile(r'(?i)thread[_ -]?id[^\n]{0,25}[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'),
}
EMAIL = re.compile(r'\b[A-Za-z0-9_.+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b')

def main():
    raw = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    paths = sorted(set(p for p in raw.decode().split('\0') if p))
    issues = []
    for rel in paths:
        path = ROOT / rel
        if path.is_symlink():
            issues.append([rel, 'symlink requires manual review']); continue
        if path.name in PRIVATE_NAMES or set(path.relative_to(ROOT).parts) & PRIVATE_DIRS or path.suffix in {'.db', '.sqlite', '.sqlite3', '.pem', '.key'}:
            issues.append([rel, 'private file in publication candidates'])
        try: body = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            if path.suffix not in {'.png', '.jpg', '.webp'}:
                issues.append([rel, 'unexpected binary file'])
            continue
        for label, pattern in RULES.items():
            for match in pattern.finditer(body):
                issues.append([rel, body.count('\n', 0, match.start()) + 1, label])
        for match in EMAIL.finditer(body):
            if match[1].lower() not in {'example.com', 'example.org', 'example.net'}:
                issues.append([rel, 'non-example email address'])
        if path.suffix == '.md':
            for target in re.findall(r'\]\(([^)\s]+)\)', body):
                if target.startswith(('https://', 'http://', '#', 'mailto:')): continue
                local = target.split('#')[0]
                if local and not (path.parent / local).exists():
                    issues.append([rel, 'broken local link: ' + local])
        if path.suffix == '.svg':
            try:
                tree = ET.fromstring(body)
                for node in tree.iter():
                    if node.tag.split('}')[-1] in {'script', 'foreignObject'}:
                        issues.append([rel, 'active SVG content'])
                    for key, value in node.attrib.items():
                        if key.split('}')[-1] == 'href' and not value.startswith('#'):
                            issues.append([rel, 'external SVG resource'])
            except ET.ParseError: issues.append([rel, 'invalid SVG'])
    commits = subprocess.check_output(['git','rev-list','--all','--count'],cwd=ROOT,text=True).strip()
    print(json.dumps({'candidate_files':len(paths),'issues':issues,'history_commits':int(commits),
                      'history_content_scanned':False,'complete_secret_audit':False},ensure_ascii=False,indent=2))
    return 1 if issues else 0

if __name__ == '__main__': raise SystemExit(main())

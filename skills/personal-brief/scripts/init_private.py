#!/usr/bin/env python3
"""Initialize private, disabled-by-default inputs outside the Skill/repository."""
import argparse
import os
from pathlib import Path

FILES = {
    'config.example.md': 'config.md',
    'preferences.example.md': 'preferences.md',
    'profile.example.md': '个人信息.md',
    'user-facts.example.md': 'user-facts.md',
    'mail-accounts.example.json': 'mail-accounts.json',
}

def initialize(destination, skill_dir=None):
    skill = Path(skill_dir or Path(__file__).resolve().parents[1]).resolve()
    root = Path(destination).expanduser().resolve()
    excluded = [skill] + [p for p in skill.parents if (p / '.git').exists()]
    if any(root == p or p in root.parents for p in excluded):
        raise ValueError('private data directory must be outside the Skill and Git repository')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    targets = [root / target for target in FILES.values()]
    if any(p.exists() or p.is_symlink() for p in targets):
        raise ValueError('input files already exist; refusing to overwrite')
    created = []
    try:
        for source, target in FILES.items():
            body = (skill / 'templates' / source).read_text(encoding='utf-8')
            body = body.replace('{{data_dir}}', str(root)).replace('{{skill_dir}}', str(skill))
            path = root / target
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                out.write(body)
    except Exception:
        for path in created:
            path.unlink()
        raise
    return created

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        created = initialize(args.data_dir)
    except (ValueError, OSError) as e:
        parser.exit(1, str(e) + '\n')
    print(f'Created {len(created)} private input files. All sources and scheduling are disabled.')

if __name__ == '__main__':
    main()

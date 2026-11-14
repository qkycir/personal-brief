import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).parents[1] / 'skills/personal-brief'
spec = importlib.util.spec_from_file_location('initializer', SKILL / 'scripts/init_private.py')
initializer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(initializer)

class InstallTests(unittest.TestCase):
    def test_skill_copy_is_self_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copied = root / 'installed-skill'
            shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('read_mail.py', 'brief_store.py', 'init_private.py'):
                subprocess.run([sys.executable, str(copied / 'scripts' / name), '--help'],
                               cwd=tmp, check=True, capture_output=True)
            private = root / 'private'
            initializer.initialize(private, copied)
            self.assertIn('enabled: false', (private / 'preferences.md').read_text())
            self.assertIn(str(copied), (private / 'config.md').read_text())
            self.assertEqual((private / 'mail-accounts.json').read_text().strip(), '{\n  "accounts": []\n}')
            subprocess.run([sys.executable, str(copied / 'scripts/brief_store.py'),
                            '--data-dir', str(private), 'init'], cwd=tmp, check=True, capture_output=True)

    def test_existing_profile_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / '个人信息.md'
            profile.write_text('user content')
            with self.assertRaises(ValueError): initializer.initialize(root)
            self.assertEqual(profile.read_text(), 'user content')
            self.assertFalse((root / 'config.md').exists())

    def test_private_data_inside_checkout_is_rejected(self):
        with self.assertRaises(ValueError):
            initializer.initialize(SKILL.parents[1] / 'private-test-not-created')

if __name__ == '__main__': unittest.main()

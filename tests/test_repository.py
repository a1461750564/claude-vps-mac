import json
import os
import re
import subprocess
import unittest

from helpers import ROOT

SCRIPTS = ['scripts/mac/claude', 'scripts/vps/claude-mac.py', 'scripts/vps/mac-project.py',
           'scripts/vps/mac-run.py', 'scripts/vps/route-bash-hook.py', 'scripts/vps/mac-git.py',
           'scripts/cvm', 'scripts/vps/mac-rg.py']
SECRETS = re.compile('|'.join([
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----', r'\bghp_[A-Za-z0-9]{30,}', r'\bgithub_pat_[A-Za-z0-9_]{30,}',
    r'\bsk-ant-[A-Za-z0-9_-]{20,}', r'\bxox[abp]-[A-Za-z0-9-]{10,}', r'vless://[0-9a-fA-F-]{8,}@',
    r'"accessToken"\s*:\s*"[^"_]',
]))


def tracked_files():
    output = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / name.decode() for name in output.split(b'\0') if name]


class Repository(unittest.TestCase):
    def test_scripts_compile(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                compile((ROOT / name).read_text(), name, 'exec')

    def test_scripts_are_executable(self):
        for name in SCRIPTS + ['scripts/vps/claude-mac-root.sh']:
            with self.subTest(script=name):
                self.assertTrue(os.access(ROOT / name, os.X_OK))

    def test_root_dispatcher_shell_syntax(self):
        subprocess.run(['bash', '-n', str(ROOT / 'scripts/vps/claude-mac-root.sh')], check=True)

    def test_examples_parse_and_keep_placeholders(self):
        for path in (ROOT / 'examples').glob('*.json'):
            with self.subTest(example=path.name):
                json.loads(path.read_text())
        launcher = json.loads((ROOT / 'examples/launcher.json').read_text())
        self.assertTrue(launcher['tailscale_host'].startswith('__'))

    def test_no_credentials_are_tracked(self):
        for path in tracked_files():
            try:
                text = path.read_text()
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertIsNone(SECRETS.search(text))


if __name__ == '__main__':
    unittest.main()

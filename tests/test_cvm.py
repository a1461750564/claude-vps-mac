import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT, load

cvm = load('scripts/cvm', 'cvm')


def entry(path, data=b'v1', mode=0o700):
    return {'path': str(path), 'owner': None, 'mode': mode, 'data': base64.b64encode(data).decode()}


class Apply(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(os.path.realpath(temporary.name))
        self.state = self.root / 'state'
        self.target = self.root / 'home/.local/libexec/claude-mac/git'

    def apply(self, files, dry_run=False, adopt=False):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cvm.apply({'state': str(self.state), 'commit': 'c1', 'dry_run': dry_run,
                              'adopt': adopt, 'files': files})
        return code, output.getvalue()

    def backups(self):
        return [path.read_bytes() for path in sorted((self.state / 'backups').rglob('*')) if path.is_file()]

    def test_fresh_install_creates_parents_and_records_a_manifest(self):
        code, output = self.apply([entry(self.target)])
        self.assertEqual(code, 0)
        self.assertIn('new', output)
        self.assertEqual(self.target.read_bytes(), b'v1')
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.root / 'home/.local/libexec').stat().st_mode), 0o700)
        manifest = json.loads((self.state / 'manifest.json').read_text())
        self.assertEqual(manifest['commit'], 'c1')
        self.assertEqual(manifest['files'][str(self.target)], hashlib.sha256(b'v1').hexdigest())
        self.assertEqual(self.backups(), [])

    def test_rerun_changes_nothing(self):
        self.apply([entry(self.target)])
        code, output = self.apply([entry(self.target)])
        self.assertEqual((code, output.split()[0]), (0, 'same'))
        self.assertEqual(self.backups(), [])

    def test_repository_update_backs_up_the_installed_version(self):
        self.apply([entry(self.target)])
        code, output = self.apply([entry(self.target, b'v2')])
        self.assertEqual((code, output.split()[0]), (0, 'update'))
        self.assertEqual((self.target.read_bytes(), self.backups()), (b'v2', [b'v1']))
        self.apply([entry(self.target, b'v3')])
        self.assertEqual((self.target.read_bytes(), self.backups()), (b'v3', [b'v1', b'v2']))

    def test_local_edits_are_kept_until_adopted(self):
        self.apply([entry(self.target)])
        self.target.write_bytes(b'edited on the server')
        code, output = self.apply([entry(self.target, b'v2')])
        self.assertEqual((code, output.split()[0]), (3, 'modified'))
        self.assertEqual(self.target.read_bytes(), b'edited on the server')
        self.assertEqual(self.apply([entry(self.target, b'v2')], adopt=True)[0], 0)
        self.assertEqual((self.target.read_bytes(), self.backups()), (b'v2', [b'edited on the server']))

    def test_files_cvm_never_installed_need_adopt(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'original deployment')
        self.assertEqual(self.apply([entry(self.target)])[0], 3)
        self.assertEqual(self.apply([entry(self.target)], dry_run=True, adopt=True)[0], 0)
        self.assertEqual(self.target.read_bytes(), b'original deployment')
        self.assertFalse(self.state.exists())
        self.assertEqual(self.apply([entry(self.target)], adopt=True)[0], 0)
        self.assertEqual((self.target.read_bytes(), self.backups()), (b'v1', [b'original deployment']))

    def test_a_mode_difference_alone_is_fixed_without_adopt(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'v1')
        self.target.chmod(0o755)
        code, output = self.apply([entry(self.target)])
        self.assertEqual((code, output.split()[0]), (0, 'update'))
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)

    def test_links(self):
        link = self.root / 'bin/claude-ssh'
        self.assertEqual(self.apply([{'path': str(link), 'link': 'claude'}])[0], 0)
        self.assertEqual(os.readlink(link), 'claude')
        self.assertEqual(self.apply([{'path': str(link), 'link': 'claude'}])[1].split()[0], 'same')
        link.unlink()
        link.write_text('a copy, not a link')
        # cvm installed the link, so a file in its place is a local change.
        self.assertEqual(self.apply([{'path': str(link), 'link': 'claude'}])[1].split()[0], 'modified')

    def test_dry_run_writes_nothing(self):
        code, output = self.apply([entry(self.target)], dry_run=True)
        self.assertEqual(code, 0)
        self.assertFalse(self.target.exists() or self.state.exists())

    def test_runs_as_python_c_without_its_own_file(self):
        argv = shlex.split(cvm.remote_command('apply'))
        self.assertEqual(argv[1:2] + argv[3:], ['-c', 'apply'])
        self.assertEqual(argv[2], (ROOT / 'scripts/cvm').read_text())
        payload = {'state': str(self.state), 'commit': 'c1', 'dry_run': False, 'adopt': False,
                   'files': [entry(self.target)]}
        result = subprocess.run([sys.executable] + argv[1:], input=json.dumps(payload), capture_output=True,
                                text=True, timeout=30, cwd=str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), b'v1')


class Payload(unittest.TestCase):
    def test_vps_payload_carries_repository_bytes_owners_and_modes(self):
        payload = cvm.payload('vps', True, False)
        self.assertEqual((payload['state'], payload['dry_run'], payload['adopt']), ('/var/lib/claude-vps-mac', True, False))
        for (source, dest, owner, mode), item in zip(cvm.VPS_FILES, payload['files']):
            with self.subTest(dest=dest):
                self.assertEqual((item['path'], item['owner'], item['mode']), (dest, owner, mode))
                self.assertEqual(base64.b64decode(item['data']), (ROOT / source).read_bytes())

    def test_mac_payload_expands_home_and_adds_the_links(self):
        with mock.patch.dict(os.environ, {'HOME': '/Users/example'}):
            payload = cvm.payload('mac', False, False)
        self.assertEqual([item['path'] for item in payload['files']],
                         ['/Users/example/.local/bin/claude', '/Users/example/.local/bin/claude-ssh', '/Users/example/.local/bin/claude-mosh'])
        self.assertEqual(payload['state'], '/Users/example/.local/state/claude-vps-mac')


def healthy(repository):
    routed = json.dumps({'hookSpecificOutput': {'updatedInput': {'command': "/home/claude/.local/bin/mac-run 'uname -s'"}}})
    return {
        'files': {path: {'sha': sha, 'owner': owner, 'mode': mode} for path, (sha, owner, mode) in repository.items()},
        'manifest': {'commit': 'v0.3.0'}, 'cli': [0, '2.1.296 (Claude Code)', ''],
        'mac': [0, 'host: m\nsystem: Darwin', ''], 'hook': [[0, routed, ''], [0, '', '']],
        'hook_registered': True, 'git': [0, 'git version 2.39.5', ''],
        'services': {'tailscaled': 'active', 'ssh': 'active'},
        'mosh': 'UNCONN 0 0 100.101.1.2:60001 0.0.0.0:*', 'mounts': 1,
        'memory_mib': {'MemAvailable': 1400, 'SwapFree': 2000},
    }


class Evaluate(unittest.TestCase):
    repository = {dest: ('sha-' + dest, owner, mode) for _, dest, owner, mode in cvm.VPS_FILES}

    def levels(self, report, last=None):
        return {name: level for level, name, _ in cvm.evaluate(report, self.repository, last)}

    def test_a_healthy_deployment_is_all_ok(self):
        levels = self.levels(healthy(self.repository), last='2.1.296 (Claude Code)')
        self.assertEqual(set(levels.values()), {'OK'}, levels)

    def test_problems_are_reported(self):
        report = healthy(self.repository)
        report['files']['/usr/local/bin/mac-project']['sha'] = 'old'
        report['files']['/home/claude/.local/bin/mac-run']['mode'] = 0o755
        del report['files']['/home/claude/.local/libexec/claude-mac/git']
        report['files']['/home/claude/.local/libexec/claude-mac/git'] = None
        report['mac'] = [255, '', 'ssh: connect timed out']
        report['hook'][0] = [0, '', '']
        report['mosh'] += '\nUNCONN 0 0 0.0.0.0:60002 0.0.0.0:*'
        report['manifest'] = None
        levels = self.levels(report, last='2.1.200 (Claude Code)')
        expected = {'/usr/local/bin/mac-project': 'FAIL', '/home/claude/.local/bin/mac-run': 'WARN',
                    '/home/claude/.local/libexec/claude-mac/git': 'FAIL', 'VPS → Mac': 'FAIL',
                    'Bash 路由 hook': 'FAIL', 'Mosh 端口': 'WARN', 'VPS 安装记录': 'WARN', 'CLI 版本变化': 'WARN'}
        self.assertEqual({name: levels[name] for name in expected}, expected)


class Main(unittest.TestCase):
    def test_unknown_usage_is_refused(self):
        for argv in ([], ['install'], ['install', 'both'], ['install', 'vps', '--force'], ['doctor', 'x']):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                cvm.main(argv)

    def test_install_refuses_uncommitted_sources(self):
        status = mock.Mock(stdout=' M scripts/vps/mac-git.py\n')
        with mock.patch.object(cvm, 'launcher_config', return_value=('a', '100.64.0.1', 'h')), \
                mock.patch.object(cvm.subprocess, 'run', return_value=status) as run:
            with self.assertRaises(SystemExit):
                cvm.install('vps', False, False)
        self.assertIn('scripts/cvm', run.call_args[0][0])


if __name__ == '__main__':
    unittest.main()

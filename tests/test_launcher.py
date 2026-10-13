import json
import os
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

from helpers import Exec, load

launcher = load('scripts/mac/claude', 'mac_launcher')
CONFIG = {'ssh_alias': 'CLAUDE-VPS', 'tailscale_host': '100.70.1.2', 'host_key_alias': 'vps.example.net'}
CWD = '/Volumes/示例盘/示例项目/demo app'


class Tty:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class WantsMosh(unittest.TestCase):
    def test_interactive_conversations_use_mosh(self):
        for args in ([], ['-c'], ['--model', 'opus'], ['修复登录问题'], ['fix the login bug'],
                     ['--permission-mode', 'manual']):
            with self.subTest(args=args):
                self.assertTrue(launcher.wants_mosh('claude', args, True, '/opt/mosh'))

    def test_everything_else_uses_ssh(self):
        cases = [('claude', ['mcp', 'list'], True, '/m'), ('claude', ['update'], True, '/m'),
                 ('claude', ['--help'], True, '/m'), ('claude', ['-v'], True, '/m'),
                 ('claude', ['-p', 'hi'], True, '/m'), ('claude', ['--print', 'hi'], True, '/m'),
                 ('claude-ssh', [], True, '/m'), ('claude', [], False, '/m'), ('claude', [], True, None)]
        for case in cases:
            with self.subTest(case=case):
                self.assertFalse(launcher.wants_mosh(*case))

    def test_port_pool_probe(self):
        for output, full in (('0\n', False), ('3', False), ('4', True), ('7', True), ('', True), ('x', True)):
            with self.subTest(output=output):
                self.assertEqual(launcher.mosh_ports_full(output), full)


class LoadConfig(unittest.TestCase):
    def load_with(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'launcher.json')
            with open(path, 'w') as handle:
                handle.write(data if isinstance(data, str) else json.dumps(data))
            with mock.patch.dict(os.environ, {'CLAUDE_MAC_CONFIG': path}):
                return launcher.load_config()

    def test_valid_configuration(self):
        self.assertEqual(self.load_with(CONFIG), ('CLAUDE-VPS', '100.70.1.2', 'vps.example.net'))

    def test_invalid_configurations_stop_before_connecting(self):
        bad = [dict(CONFIG, tailscale_host='__VPS_TAILSCALE_IPV4__'), dict(CONFIG, tailscale_host='8.8.8.8'),
               dict(CONFIG, ssh_alias='bad alias'), dict(CONFIG, ssh_alias='-oProxyCommand=x'),
               dict(CONFIG, host_key_alias='a b'), {'ssh_alias': 'x'}, 'not json']
        for data in bad:
            with self.subTest(data=data), self.assertRaises(SystemExit):
                self.load_with(data)

    def test_missing_file(self):
        with mock.patch.dict(os.environ, {'CLAUDE_MAC_CONFIG': '/nonexistent/launcher.json'}):
            with self.assertRaises(SystemExit):
                launcher.load_config()


class Main(unittest.TestCase):
    def launch(self, args, tty=True, probe=(0, '1\n'), mosh='/opt/homebrew/bin/mosh', name='claude'):
        ready = subprocess.CompletedProcess([], probe[0], stdout=probe[1], stderr='')
        with mock.patch('sys.platform', 'darwin'), mock.patch('sys.argv', ['/x/' + name, *args]), \
                mock.patch('sys.stdin', Tty(tty)), mock.patch('sys.stdout', Tty(tty)), \
                mock.patch('sys.stderr'), mock.patch.object(launcher, 'load_config',
                                                           return_value=('CLAUDE-VPS', '100.70.1.2', 'vps')), \
                mock.patch('shutil.which', return_value=mosh), mock.patch('os.getcwd', return_value=CWD), \
                mock.patch('subprocess.run', return_value=ready) as run, \
                mock.patch('os.execv', side_effect=Exec) as execv, \
                mock.patch('os.execve', side_effect=Exec) as execve:
            with self.assertRaises(Exec):
                launcher.main()
        return run, execv, execve

    def remote(self, *args):
        return ['/root/.local/bin/claude-mac', '--mac-project', CWD, '--', *args]

    def test_interactive_session_starts_mosh_on_the_tailnet(self):
        run, execv, execve = self.launch(['-c'])
        self.assertIn('ss -Hlun', run.call_args[0][0][-1])
        argv = execve.call_args[0][1]
        self.assertIn('--port=60001:60004', argv)
        self.assertIn('HostName=100.70.1.2', argv[1])
        self.assertEqual(argv[argv.index('--') + 1:], ['CLAUDE-VPS', *self.remote('-c')])
        execv.assert_not_called()

    def test_non_interactive_call_uses_ssh_and_round_trips_arguments(self):
        tricky = ['-p', "it's $HOME; `x` \"q\""]
        _, execv, execve = self.launch(tricky, tty=False)
        argv = execv.call_args[0][1]
        self.assertIn('-T', argv)
        self.assertIn('HostName=100.70.1.2', argv)
        self.assertEqual(shlex.split(argv[-1]), self.remote(*tricky))
        execve.assert_not_called()

    def test_tailscale_failure_falls_back_to_the_public_alias(self):
        _, execv, _ = self.launch([], probe=(255, ''))
        argv = execv.call_args[0][1]
        self.assertNotIn('HostName=100.70.1.2', argv)
        self.assertIn('-tt', argv)

    def test_full_port_pool_uses_ssh(self):
        _, execv, execve = self.launch([], probe=(0, '4\n'))
        self.assertIn('-tt', execv.call_args[0][1])
        execve.assert_not_called()

    def test_forced_ssh_name(self):
        run, execv, _ = self.launch([], name='claude-ssh')
        self.assertEqual(run.call_args[0][0][-1], 'true')
        self.assertIn('-tt', execv.call_args[0][1])

    def test_refuses_to_run_off_the_mac(self):
        with mock.patch('sys.platform', 'linux'), self.assertRaises(SystemExit):
            launcher.main()


if __name__ == '__main__':
    unittest.main()

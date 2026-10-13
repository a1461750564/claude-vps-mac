import os
import shlex
import subprocess
import unittest
from unittest import mock

from helpers import Exec, load

mac_run = load('scripts/vps/mac-run.py', 'mac_run')
PROJECT = '/Volumes/项目数据盘/项目/demo app'
MOUNT = '/home/claude/orca-control/projects/abc'


class Plan(unittest.TestCase):
    def test_project_root_and_exported_variables(self):
        target, command = mac_run.plan(PROJECT, MOUNT, MOUNT, 'pwd')
        self.assertEqual(target, PROJECT)
        first, rest = command.split('\n', 1)
        self.assertEqual(rest, 'pwd')
        self.assertEqual(shlex.split(first), ['export', 'MAC_PROJECT_DIR=' + PROJECT, 'MAC_PROJECT_MOUNT=' + PROJECT])

    def test_exported_variables_survive_a_real_shell(self):
        _, command = mac_run.plan(PROJECT, MOUNT, MOUNT, 'printf "%s|%s" "$MAC_PROJECT_DIR" "$MAC_PROJECT_MOUNT"')
        output = subprocess.run(['/bin/bash', '-c', command], capture_output=True, text=True, check=True).stdout
        self.assertEqual(output, PROJECT + '|' + PROJECT)

    def test_subdirectory_maps_to_the_same_mac_subdirectory(self):
        self.assertEqual(mac_run.plan(PROJECT, MOUNT, MOUNT + '/src/app', 'ls')[0], PROJECT + '/src/app')

    def test_mount_paths_inside_the_command_become_mac_paths(self):
        _, command = mac_run.plan(PROJECT, MOUNT, MOUNT, 'cat ' + MOUNT + '/a.txt')
        self.assertTrue(command.endswith('cat ' + PROJECT + '/a.txt'))

    def test_outside_the_mount_is_refused(self):
        for cwd in ('/tmp', MOUNT + '-sibling', '/home/claude'):
            with self.subTest(cwd=cwd), self.assertRaises(SystemExit):
                mac_run.plan(PROJECT, MOUNT, cwd, 'ls')


class Main(unittest.TestCase):
    def test_requires_a_mac_project_session(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch('sys.argv', ['mac-run', 'ls']):
            with self.assertRaises(SystemExit):
                mac_run.main()

    def test_hands_the_mapped_call_to_mac_project(self):
        env = {'MAC_PROJECT_DIR': PROJECT, 'MAC_PROJECT_MOUNT': MOUNT}
        with mock.patch.dict(os.environ, env), mock.patch('sys.argv', ['mac-run', 'ls -la']), \
                mock.patch('os.getcwd', return_value=MOUNT + '/src'), \
                mock.patch('os.execv', side_effect=Exec) as execv:
            with self.assertRaises(Exec):
                mac_run.main()
        path, argv = execv.call_args[0]
        self.assertEqual(path, '/usr/local/bin/mac-project')
        self.assertEqual(argv[1:3], ['exec', PROJECT + '/src'])
        self.assertTrue(argv[3].endswith('\nls -la'))


if __name__ == '__main__':
    unittest.main()

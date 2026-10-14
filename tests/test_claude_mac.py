import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from helpers import Exec, load

claude_mac = load('scripts/vps/claude-mac.py', 'claude_mac')


class TooBroad(unittest.TestCase):
    def test_roots_homes_and_whole_disks_are_refused(self):
        for path in ('/', '/Users', '/Users/example', '/Users/example/', '/Volumes', '/Volumes/ExampleDisk', '/tmp'):
            with self.subTest(path=path):
                self.assertTrue(claude_mac.too_broad(path))

    def test_project_directories_are_allowed(self):
        for path in ('/Users/example/code', '/Volumes/ExampleDisk/projects', '/Volumes/示例盘/示例项目/demo app'):
            with self.subTest(path=path):
                self.assertFalse(claude_mac.too_broad(path))


class StateDirectory(unittest.TestCase):
    def run_project_session(self, linked):
        project = '/Volumes/示例盘/示例项目/demo app'
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary, 'home')
            home.mkdir()
            control = home / 'claude-vps-mac'
            actual = Path(temporary, 'existing-state') if linked else control
            actual.mkdir()
            if linked:
                control.symlink_to(actual, target_is_directory=True)
            session = actual / 'projects' / hashlib.sha256(project.encode()).hexdigest()
            session.mkdir(parents=True)
            try:
                with mock.patch.object(claude_mac.Path, 'home', return_value=home), \
                        mock.patch.object(claude_mac.os, 'geteuid', return_value=1000), \
                        mock.patch('sys.argv', ['claude-mac', '--mac-project', project, '--', '-c']), \
                        mock.patch.object(claude_mac.subprocess, 'run',
                                          return_value=subprocess.CompletedProcess([], 0, 'Darwin', '')), \
                        mock.patch.object(claude_mac, 'release_idle_mounts') as release, \
                        mock.patch.object(claude_mac, 'mount_project',
                                          side_effect=lambda _, path: os.chdir(path)) as mount, \
                        mock.patch.object(claude_mac.os, 'execve', side_effect=Exec) as execute:
                    with self.assertRaises(Exec):
                        claude_mac.main()
                    expected = session.resolve()
                    self.assertEqual(Path.cwd(), expected)
                    release.assert_called_once_with(actual.resolve(), expected)
                    mount.assert_called_once_with(project, expected)
                    env = execute.call_args[0][2]
                    self.assertEqual(env['MAC_PROJECT_MOUNT'], str(expected))
                    self.assertEqual(env['MAC_PROJECT_DIR'], project)
                    self.assertEqual(execute.call_args[0][1][-1], '-c')
            finally:
                os.chdir(previous)

    def test_new_deployment_uses_the_project_state_directory(self):
        self.run_project_session(linked=False)

    def test_state_alias_preserves_actual_mount_and_session_paths(self):
        self.run_project_session(linked=True)


class CacheOutdated(unittest.TestCase):
    current = [option.encode() for option in claude_mac.CACHE_OPTIONS] + [b'reconnect', b'nodev']

    def test_current_policy_is_kept(self):
        self.assertFalse(claude_mac.cache_outdated(self.current))

    def test_old_or_content_caching_mounts_are_upgraded(self):
        self.assertTrue(claude_mac.cache_outdated(self.current + [b'auto_cache']))
        self.assertTrue(claude_mac.cache_outdated([o for o in self.current if o != b'direct_io']))
        self.assertTrue(claude_mac.cache_outdated([b'dir_cache=no', b'attr_timeout=0']))


class SessionEnv(unittest.TestCase):
    wrappers = '/home/claude/.local/libexec/claude-mac'
    base = {'PATH': '/home/claude/.local/bin:/usr/bin', 'HOME': '/home/claude'}

    def test_mac_project_sessions_get_project_variables_and_the_git_wrapper(self):
        env = claude_mac.session_env(self.base, self.wrappers, '/Volumes/ExampleDisk/p', '/m/abc')
        self.assertEqual((env['MAC_PROJECT_DIR'], env['MAC_PROJECT_MOUNT']), ('/Volumes/ExampleDisk/p', '/m/abc'))
        self.assertEqual(env['PATH'], self.wrappers + ':/home/claude/.local/bin:/usr/bin')
        self.assertEqual(env['HOME'], '/home/claude')
        self.assertEqual(env['USE_BUILTIN_RIPGREP'], '0')

    def test_other_sessions_drop_both_even_when_inherited(self):
        inherited = dict(self.base, MAC_PROJECT_DIR='/x', MAC_PROJECT_MOUNT='/y', USE_BUILTIN_RIPGREP='0',
                         PATH=self.wrappers + ':' + self.base['PATH'])
        env = claude_mac.session_env(inherited, self.wrappers)
        self.assertNotIn('MAC_PROJECT_DIR', env)
        self.assertNotIn('MAC_PROJECT_MOUNT', env)
        self.assertNotIn('USE_BUILTIN_RIPGREP', env)
        self.assertEqual(env['PATH'], self.base['PATH'])


if __name__ == '__main__':
    unittest.main()

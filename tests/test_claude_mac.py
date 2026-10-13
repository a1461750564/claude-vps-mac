import unittest

from helpers import load

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

    def test_other_sessions_drop_both_even_when_inherited(self):
        inherited = dict(self.base, MAC_PROJECT_DIR='/x', MAC_PROJECT_MOUNT='/y',
                         PATH=self.wrappers + ':' + self.base['PATH'])
        env = claude_mac.session_env(inherited, self.wrappers)
        self.assertNotIn('MAC_PROJECT_DIR', env)
        self.assertNotIn('MAC_PROJECT_MOUNT', env)
        self.assertEqual(env['PATH'], self.base['PATH'])


if __name__ == '__main__':
    unittest.main()

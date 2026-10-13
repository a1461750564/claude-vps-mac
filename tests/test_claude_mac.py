import unittest

from helpers import load

claude_mac = load('scripts/vps/claude-mac.py', 'claude_mac')


class TooBroad(unittest.TestCase):
    def test_roots_homes_and_whole_disks_are_refused(self):
        for path in ('/', '/Users', '/Users/someone', '/Users/someone/', '/Volumes', '/Volumes/Data', '/tmp'):
            with self.subTest(path=path):
                self.assertTrue(claude_mac.too_broad(path))

    def test_project_directories_are_allowed(self):
        for path in ('/Users/someone/code', '/Volumes/Data/projects', '/Volumes/项目数据盘/项目/demo app'):
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


if __name__ == '__main__':
    unittest.main()

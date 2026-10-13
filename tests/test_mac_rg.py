import base64
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import load

mac_rg = load('scripts/vps/mac-rg.py', 'mac_rg')
PROJECT = '/Volumes/数据盘/项目/demo app'
MOUNT = '/home/claude/orca-control/projects/abc'


class Routing(unittest.TestCase):
    def test_glob_and_grep_arguments_preserve_patterns_and_map_only_paths(self):
        for args in (['--files', '--hidden', '--glob', '**/*.py', MOUNT],
                     ['-n', '-H', '-e', MOUNT + '/literal;$(echo bad)', MOUNT + '/中文 空格.txt'],
                     ['--json', '--regexp=' + MOUNT, MOUNT],
                     ['--file', MOUNT + '/patterns', MOUNT]):
            with self.subTest(args=args):
                target, command, _ = mac_rg.plan(PROJECT, MOUNT, MOUNT, args, {})
                self.assertEqual(target, PROJECT)
                argv = shlex.split(command)
                self.assertEqual(argv[:2], ['exec', 'rg'])
                self.assertEqual(argv[-1], args[-1].replace(MOUNT, PROJECT))
                if '-e' in args:
                    self.assertEqual(argv[argv.index('-e') + 1], args[args.index('-e') + 1])
                if any(arg.startswith('--regexp=') for arg in args):
                    self.assertIn('--regexp=' + MOUNT, argv)

    def test_vps_paths_and_host_specific_calls_stay_on_the_vps(self):
        for args in (['--version'], ['--files', '/home/claude/.claude'],
                     ['needle', '../../outside'], ['--file', '/tmp/patterns', MOUNT],
                     ['--pre', '/vps/program', 'needle', MOUNT], ['--heading', 'needle', MOUNT],
                     ['--color', 'always', 'needle', MOUNT], ['--null-data', 'needle', MOUNT]):
            with self.subTest(args=args):
                self.assertIsNone(mac_rg.plan(PROJECT, MOUNT, MOUNT, args, {}))
        self.assertIsNone(mac_rg.plan(PROJECT, MOUNT, '/tmp', ['needle'], {}))
        self.assertIsNone(mac_rg.plan(PROJECT, MOUNT, MOUNT, ['needle'], {'RIPGREP_CONFIG_PATH': '/vps/config'}))

    def test_subdirectory_and_regexp_without_dash_e(self):
        target, command, mode = mac_rg.plan(PROJECT, MOUNT, MOUNT + '/src', [MOUNT, '.'], {})
        self.assertEqual(target, PROJECT + '/src')
        self.assertEqual(shlex.split(command), ['exec', 'rg', MOUNT, PROJECT + '/src'])


class Output(unittest.TestCase):
    def test_filename_prefixes_map_without_changing_match_text(self):
        line = (PROJECT + '/file.txt:12:content ' + PROJECT + '/literal\n').encode()
        expected = (MOUNT + '/file.txt:12:content ' + PROJECT + '/literal\n').encode()
        self.assertEqual(mac_rg.map_output(line, PROJECT, MOUNT, 'prefixed'), expected)
        self.assertEqual(mac_rg.map_output(line, PROJECT, MOUNT, 'text'), line)
        self.assertEqual(mac_rg.map_path((PROJECT + '-other/file').encode(), PROJECT, MOUNT),
                         (PROJECT + '-other/file').encode())

    def test_json_maps_path_fields_and_keeps_contents_and_offsets(self):
        content = PROJECT + '/literal\n'
        for field in ({'text': PROJECT + '/file.txt'},
                      {'bytes': base64.b64encode((PROJECT + '/file.txt').encode() + b'\xff').decode()}):
            event = {'type': 'match', 'data': {'path': field, 'lines': {'text': content},
                                             'absolute_offset': 10, 'submatches': [{'start': 0, 'end': 2}]}}
            changed = json.loads(mac_rg.map_output(json.dumps(event).encode(), PROJECT, MOUNT, 'json'))
            self.assertEqual(changed['data']['lines'], event['data']['lines'])
            self.assertEqual(changed['data']['submatches'], event['data']['submatches'])
            if 'text' in field:
                self.assertEqual(changed['data']['path']['text'], MOUNT + '/file.txt')
            else:
                self.assertEqual(base64.b64decode(changed['data']['path']['bytes']), (MOUNT + '/file.txt').encode() + b'\xff')


@unittest.skipUnless(shutil.which('rg'), 'uses the existing system rg')
class RealSearch(unittest.TestCase):
    def test_shell_arguments_output_and_exit_codes_match_real_rg(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / '中文 空格.txt'
            file.write_text('marker ' + directory + '/literal\n')
            for args in (['--files', '--null', MOUNT], ['-n', '-H', 'marker', MOUNT],
                         ['-n', '-H', 'not-present', MOUNT], ['--json', 'marker', MOUNT],
                         ['-n', '-H', '[invalid', MOUNT], ['--files', '-g', '*.txt', MOUNT]):
                with self.subTest(args=args):
                    target, command, mode = mac_rg.plan(directory, MOUNT, MOUNT, args, {})
                    result = subprocess.run(['/bin/bash', '-c', command], cwd=target, capture_output=True)
                    direct = subprocess.run(['rg', *[arg.replace(MOUNT, directory) for arg in args]],
                                            cwd=directory, capture_output=True)
                    self.assertEqual(result.returncode, direct.returncode)
                    if mode == 'json':
                        events = []
                        for output in (result.stdout, direct.stdout):
                            records = [json.loads(line) for line in output.splitlines()]
                            for record in records:
                                record.get('data', {}).get('stats', {}).pop('elapsed', None)
                                record.get('data', {}).pop('elapsed_total', None)
                            events.append(records)
                        self.assertEqual(events[0], events[1])
                        for line in result.stdout.splitlines():
                            changed = json.loads(mac_rg.map_output(line, directory, MOUNT, mode))
                            if changed['type'] == 'match':
                                self.assertEqual(changed['data']['lines']['text'], 'marker ' + directory + '/literal\n')
                                self.assertTrue(changed['data']['path']['text'].startswith(MOUNT + '/'))
                    else:
                        self.assertEqual(result.stdout, direct.stdout)
                        if mode == 'prefixed' and result.returncode == 0:
                            mapped = mac_rg.map_output(result.stdout, directory, MOUNT, mode)
                            self.assertIn(('marker ' + directory + '/literal').encode(), mapped)


class Failure(unittest.TestCase):
    def test_failed_mac_connection_does_not_rerun_the_search_on_the_vps(self):
        child = mock.Mock(stdout=iter([]), wait=mock.Mock(return_value=255))
        child.stdout = mock.Mock(__iter__=mock.Mock(return_value=iter([])))
        with mock.patch.dict(os.environ, {'MAC_PROJECT_DIR': PROJECT, 'MAC_PROJECT_MOUNT': MOUNT}), \
                mock.patch('sys.argv', ['rg', '--files']), mock.patch('os.getcwd', return_value=MOUNT), \
                mock.patch('os.isatty', return_value=False), mock.patch.object(mac_rg.subprocess, 'Popen', return_value=child), \
                mock.patch('os.execv') as execv, mock.patch('sys.stdout'):
            with self.assertRaises(SystemExit) as error:
                mac_rg.main()
        self.assertEqual(error.exception.code, 255)
        execv.assert_not_called()


if __name__ == '__main__':
    unittest.main()

import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from unittest import mock

from helpers import Exec, load

mac_git = load('scripts/vps/mac-git.py', 'mac_git')
PROJECT = '/Volumes/项目数据盘/项目/demo app'
MOUNT = '/home/claude/orca-control/projects/abc'
# Options the CLI puts before its own git calls (2.1.296, shortened).
CLI = ['-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=', '--no-optional-locks']


def plan(args, cwd=MOUNT, env=None, project=PROJECT):
    return mac_git.plan(project, MOUNT, cwd, args, env or {})


def remote(line):
    """Split a planned Mac command into its environment and git arguments."""
    words = shlex.split(line)
    assert words[:2] == ['exec', 'env'], words
    index = words.index('git')
    return dict(word.split('=', 1) for word in words[2:index]), words[index + 1:]


class Plan(unittest.TestCase):
    def test_cli_context_calls_run_on_the_mac(self):
        for args in (['status', '--short'], ['log', '--oneline', '-n', '5'], ['config', 'user.name'],
                     ['remote', 'get-url', 'origin']):
            with self.subTest(args=args):
                target, line, maps_output = plan(CLI + args)
                self.assertEqual(target, PROJECT)
                self.assertEqual(remote(line)[1], CLI + args)
                self.assertFalse(maps_output)

    def test_subdirectories_and_dash_c_follow_the_mount(self):
        self.assertEqual(plan(['status'], cwd=MOUNT + '/src')[0], PROJECT + '/src')
        for cwd in (MOUNT, '/home/claude'):
            with self.subTest(cwd=cwd):
                target, line, _ = plan(['-C', MOUNT + '/docs', 'status'], cwd=cwd)
                self.assertEqual((target, remote(line)[1]), (PROJECT + '/docs', ['-C', PROJECT + '/docs', 'status']))
        target, line, _ = plan(['-C', 'src', '-C', 'lib', 'status'])
        self.assertEqual((target, remote(line)[1]),
                         (PROJECT + '/src/lib', ['-C', PROJECT + '/src', '-C', PROJECT + '/src/lib', 'status']))
        self.assertEqual(plan(['-C', '..', 'status'], cwd=MOUNT + '/src')[0], PROJECT)
        self.assertEqual(plan(['-C', '../abc/src', 'status'])[0], PROJECT + '/src')
        self.assertIsNone(plan(['-C', '..', 'status']))

    def test_outside_the_mount_git_stays_on_the_vps(self):
        for cwd in ('/home/claude', MOUNT + '-sibling', '/'):
            with self.subTest(cwd=cwd):
                self.assertIsNone(plan(['status'], cwd=cwd))

    def test_vps_paths_keep_git_on_the_vps(self):
        for args in (['clone', 'https://example.invalid/x.git', '/home/claude/.claude/plugins/x'],
                     ['diff', '--no-index', '/tmp/a', MOUNT + '/b'],
                     ['-c', 'core.hooksPath=/home/claude/hooks', 'status'],
                     ['--git-dir=/tmp/repo.git', 'status'], ['--git-dir', '/tmp/repo.git', 'status']):
            with self.subTest(args=args):
                self.assertIsNone(plan(args))

    def test_mount_paths_and_dev_null_are_mapped_through(self):
        _, line, _ = plan(['diff', '--no-index', '/dev/null', MOUNT + '/new file'])
        self.assertEqual(remote(line)[1], ['diff', '--no-index', '/dev/null', PROJECT + '/new file'])

    def test_calls_without_a_repository_stay_local(self):
        for args in ([], ['--version'], ['version'], ['help', 'status'], ['--exec-path'], CLI):
            with self.subTest(args=args):
                self.assertIsNone(plan(args))

    def test_only_path_printing_commands_map_output(self):
        self.assertTrue(plan(CLI + ['rev-parse', '--show-toplevel'])[2])
        self.assertTrue(plan(['worktree', 'list', '--porcelain', '-z'])[2])
        self.assertFalse(plan(['show', 'HEAD:README.md'])[2])

    def test_git_environment_is_forwarded_selectively(self):
        env = {'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0', 'GIT_EDITOR': 'true',
               'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.attributesFile',
               'GIT_CONFIG_VALUE_0': MOUNT + '/.attributes', 'GIT_CONFIG_GLOBAL': '/dev/null',
               'GIT_ASKPASS': '/usr/lib/git-core/git-gui--askpass', 'GIT_SSH_COMMAND': 'ssh -i key',
               'GIT_EXEC_PATH': '/usr/lib/git-core', 'GIT_TRACE': '1', 'GIT_PAGER': '/usr/bin/less',
               'GIT_CEILING_DIRECTORIES': '/home', 'HOME': '/home/claude', 'PATH': '/usr/bin'}
        forwarded, _ = remote(plan(['status'], env=env)[1])
        self.assertEqual(forwarded, {
            'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0', 'GIT_EDITOR': 'true',
            'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.attributesFile',
            'GIT_CONFIG_VALUE_0': PROJECT + '/.attributes', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_CEILING_DIRECTORIES': '/Volumes/项目数据盘/项目'})

    def test_repository_location_variables_map_or_stay_local(self):
        forwarded, _ = remote(plan(['status'], env={'GIT_DIR': MOUNT + '/.git', 'GIT_INDEX_FILE': 'idx'})[1])
        self.assertEqual((forwarded['GIT_DIR'], forwarded['GIT_INDEX_FILE']), (PROJECT + '/.git', 'idx'))
        for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_GLOBAL'):
            with self.subTest(name=name):
                self.assertIsNone(plan(['status'], env={name: '/tmp/elsewhere'}))
        self.assertIsNone(plan(['status'], env={'GIT_ALTERNATE_OBJECT_DIRECTORIES': MOUNT + '/o:/tmp/o'}))


class Shell(unittest.TestCase):
    def test_arguments_reach_git_unchanged_through_bash(self):
        args = CLI + ['log', '--format=%H %s', '--', 'a b/文件.txt', "it's", '$HOME', '`x`', '*.py']
        _, line, _ = plan(args, env={'GIT_OPTIONAL_LOCKS': '0'})
        with tempfile.TemporaryDirectory() as tools:
            fake = Path(tools, 'git')
            fake.write_text('#!%s\nimport json, os, sys\nprint(json.dumps([sys.argv[1:], '
                            'os.environ.get("GIT_OPTIONAL_LOCKS"), os.environ.get("GIT_CEILING_DIRECTORIES")]))\n'
                            % sys.executable)
            fake.chmod(0o755)
            result = subprocess.run(['/bin/bash', '-c', line], capture_output=True, text=True, timeout=20,
                                    env=dict(os.environ, PATH=tools + os.pathsep + os.environ['PATH']))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [args, '0', '/Volumes/项目数据盘/项目'])

    def test_discovery_stops_at_the_project_like_the_mount(self):
        with tempfile.TemporaryDirectory() as temporary:
            outer = Path(os.path.realpath(temporary), 'outer')
            nested, repository = outer / 'nested', Path(os.path.realpath(temporary), 'repo')
            for path in (nested, repository):
                path.mkdir(parents=True)
            for path in (outer, repository):
                subprocess.run(['git', 'init', '-q', str(path)], check=True)
            for project, expected in ((nested, None), (repository, str(repository))):
                with self.subTest(project=project.name):
                    _, line, _ = plan(['rev-parse', '--show-toplevel'], project=str(project))
                    result = subprocess.run(['/bin/bash', '-c', line], cwd=project, capture_output=True,
                                            text=True, timeout=20)
                    if expected is None:
                        self.assertNotEqual(result.returncode, 0)
                    else:
                        self.assertEqual((result.returncode, result.stdout.strip()), (0, expected))


class MapOutput(unittest.TestCase):
    def test_mac_paths_become_mount_paths(self):
        output = (PROJECT + '\n' + PROJECT + '/.git\nunrelated /Volumes/x\n').encode()
        self.assertEqual(mac_git.map_output(output, PROJECT, MOUNT),
                         (MOUNT + '\n' + MOUNT + '/.git\nunrelated /Volumes/x\n').encode())

    def test_both_unicode_forms_of_the_project_are_mapped(self):
        project = '/Users/me/Café'
        for form in ('NFC', 'NFD'):
            with self.subTest(form=form):
                output = unicodedata.normalize(form, project).encode() + b'\n'
                self.assertEqual(mac_git.map_output(output, project, MOUNT), MOUNT.encode() + b'\n')


class Main(unittest.TestCase):
    session = {'MAC_PROJECT_DIR': PROJECT, 'MAC_PROJECT_MOUNT': MOUNT}

    def run_main(self, args, env, cwd=MOUNT, tty=False):
        with mock.patch.dict(os.environ, env, clear=True), mock.patch('sys.argv', ['git', *args]), \
                mock.patch('os.getcwd', return_value=cwd), mock.patch('os.isatty', return_value=tty), \
                mock.patch('os.dup2') as dup2, mock.patch('os.open', return_value=99), \
                mock.patch('os.execv', side_effect=Exec) as execv:
            with self.assertRaises(Exec):
                mac_git.main()
        return execv.call_args[0], dup2

    def test_outside_a_mac_project_session_the_vps_git_runs(self):
        (path, argv), _ = self.run_main(['status'], {})
        self.assertEqual((path, argv), ('/usr/bin/git', ['/usr/bin/git', 'status']))

    def test_repository_calls_are_handed_to_mac_project(self):
        (path, argv), dup2 = self.run_main(['status', '--short'], self.session, cwd=MOUNT + '/src')
        self.assertEqual(path, '/usr/local/bin/mac-project')
        self.assertEqual(argv[1:3], ['exec', PROJECT + '/src'])
        self.assertEqual(remote(argv[3])[1], ['status', '--short'])
        dup2.assert_not_called()

    def test_a_terminal_stdin_is_not_read_by_the_ssh_channel(self):
        _, dup2 = self.run_main(['status'], self.session, tty=True)
        dup2.assert_called_once_with(99, 0)

    def test_rev_parse_output_is_mapped_and_the_exit_code_kept(self):
        child = mock.Mock(returncode=0)
        child.communicate.return_value = ((PROJECT + '\n').encode(), None)
        stdout = io.TextIOWrapper(io.BytesIO())
        with mock.patch.dict(os.environ, self.session, clear=True), \
                mock.patch('sys.argv', ['git', 'rev-parse', '--show-toplevel']), \
                mock.patch('os.getcwd', return_value=MOUNT), mock.patch('os.isatty', return_value=False), \
                mock.patch('subprocess.Popen', return_value=child) as popen, \
                mock.patch('signal.signal'), mock.patch('sys.stdout', stdout):
            with self.assertRaises(SystemExit) as raised:
                mac_git.main()
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(popen.call_args[0][0][:3], ['/usr/local/bin/mac-project', 'exec', PROJECT])
        self.assertEqual(stdout.buffer.getvalue(), (MOUNT + '\n').encode())


if __name__ == '__main__':
    unittest.main()

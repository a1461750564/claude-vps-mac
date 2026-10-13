import json
import os
import shlex
import subprocess
import sys
import unittest

from helpers import ROOT, load

hook = load('scripts/vps/route-bash-hook.py', 'route_bash_hook')
ENV = {'MAC_PROJECT_DIR': '/Volumes/盘/项目 A', 'MAC_PROJECT_MOUNT': '/home/claude/orca-control/projects/abc'}


def decide(command, env=ENV, **fields):
    return hook.decide({'tool_input': dict(fields, command=command)}, env)


class Decide(unittest.TestCase):
    def assertRouted(self, command):
        updated = decide(command)
        self.assertEqual(shlex.split(updated['command']), [hook.MAC_RUN, command])

    def test_ordinary_commands_go_to_the_mac(self):
        for command in ('git status --short', 'cd docs && ls', 'echo "#vps" | cat',
                        "printf '%s\\n' \"it's\"", 'cat <<EOF\nx\nEOF', 'echo $HOME; exit 3'):
            with self.subTest(command=command):
                self.assertRouted(command)

    def test_other_tool_fields_are_kept(self):
        updated = decide('npm test', timeout=5000, run_in_background=True, description='t')
        self.assertEqual((updated['timeout'], updated['run_in_background'], updated['description']),
                         (5000, True, 't'))

    def test_explicit_vps_commands_stay(self):
        for command in ('uname -s #vps', 'uname -s   #vps  ', 'python3 - <<EOF #vps\nprint(1)\nEOF',
                        'a\nb\nuname -s #vps', 'mac-project exec "$MAC_PROJECT_DIR" true'):
            with self.subTest(command=command):
                self.assertIsNone(decide(command))

    def test_vps_mark_only_counts_at_first_or_last_line_end(self):
        self.assertRouted('a\necho x #vps\nb')
        self.assertRouted('echo #vpsx')

    def test_bare_cd_stays_so_the_cwd_persists(self):
        for command in ('cd', 'cd docs', 'cd ..', 'cd "two words"', "cd 'x y'"):
            with self.subTest(command=command):
                self.assertIsNone(decide(command))

    def test_cd_to_a_mac_path_maps_back_to_the_mount(self):
        updated = decide('cd "/Volumes/盘/项目 A/docs"')
        self.assertEqual(updated['command'], 'cd "/home/claude/orca-control/projects/abc/docs"')
        env = {'MAC_PROJECT_DIR': '/Volumes/盘/proj', 'MAC_PROJECT_MOUNT': '/m/abc'}
        self.assertEqual(decide('cd /Volumes/盘/proj/src', env=env)['command'], 'cd /m/abc/src')

    def test_unquoted_path_with_spaces_is_not_a_bare_cd(self):
        # Two words after cd are a shell error; it runs on the Mac and reports it.
        self.assertRouted('cd /Volumes/盘/项目 A/docs')

    def test_outside_a_mac_project_session_nothing_changes(self):
        self.assertIsNone(decide('ls', env={}))
        self.assertIsNone(decide('ls', env={'MAC_PROJECT_DIR': '/x'}))

    def test_non_string_commands_are_rejected(self):
        with self.assertRaises(TypeError):
            hook.decide({'tool_input': {'command': ['ls']}}, ENV)


class HookProcess(unittest.TestCase):
    def run_hook(self, payload, env=ENV):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/vps/route-bash-hook.py')],
                                input=payload, capture_output=True, text=True,
                                env=dict(os.environ, **env), timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_rewrite_is_returned_as_an_allowed_updated_input(self):
        output = json.loads(self.run_hook(json.dumps({'tool_input': {'command': 'ls', 'timeout': 9}})))
        specific = output['hookSpecificOutput']
        self.assertEqual((specific['hookEventName'], specific['permissionDecision']), ('PreToolUse', 'allow'))
        self.assertEqual(specific['updatedInput']['timeout'], 9)
        self.assertEqual(shlex.split(specific['updatedInput']['command'])[1], 'ls')

    def test_errors_deny_instead_of_running_on_the_vps(self):
        for payload in ('{"tool_input": {}}', 'not json', '{}'):
            with self.subTest(payload=payload):
                specific = json.loads(self.run_hook(payload))['hookSpecificOutput']
                self.assertEqual(specific['permissionDecision'], 'deny')

    def test_unchanged_calls_print_nothing(self):
        self.assertEqual(self.run_hook(json.dumps({'tool_input': {'command': 'uname #vps'}})), '')


if __name__ == '__main__':
    unittest.main()

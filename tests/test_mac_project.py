import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from helpers import Exec, load

mac_project = load('scripts/vps/mac-project.py', 'mac_project')
PROJECT = '/Volumes/项目数据盘/项目/demo app'


class Command(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state = Path(self.directory.name, 'mac-connection.json')
        self.state.write_text(json.dumps({'transport': 'tailscale'}))
        patcher = mock.patch.object(mac_project, 'STATE', self.state)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.directory.cleanup)

    def run_main(self, *args):
        with mock.patch('sys.argv', ['mac-project', *args]), mock.patch('os.execv', side_effect=Exec) as execv:
            with self.assertRaises(Exec):
                mac_project.main()
        return execv.call_args[0][1]

    def test_exec_round_trips_project_and_script_through_both_shells(self):
        script = "printf '%s' \"$HOME\"; echo 'a b' | cat; exit 4"
        argv = self.run_main('exec', PROJECT, script)
        self.assertEqual(argv[:2], ['/usr/bin/ssh', '-T'])
        self.assertEqual(argv[-2], 'mac-project')
        outer = shlex.split(argv[-1])
        self.assertEqual(outer[:3], ['exec', '/bin/zsh', '-lc'])
        self.assertEqual(shlex.split(outer[3]), ['exec', '/usr/bin/python3', '-c', mac_project.GUARD, PROJECT, script])

    def test_check_reports_the_host(self):
        self.assertIn('uname -s', self.run_main('check')[-1])

    def test_rejects_bad_usage(self):
        for args in (['exec', 'relative/path', 'ls'], ['exec', '/ok'], ['nope'], ['exec', '/a\nb', 'ls']):
            with self.subTest(args=args), mock.patch('sys.argv', ['mac-project', *args]):
                with self.assertRaises(SystemExit):
                    mac_project.main()

    def test_requires_registration(self):
        self.state.unlink()
        with mock.patch('sys.argv', ['mac-project', 'check']), self.assertRaises(SystemExit):
            mac_project.main()


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@unittest.skipUnless(sys.platform == 'darwin', 'the guard uses macOS kqueue process events')
class Guard(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def guard(self, script, **kwargs):
        return [sys.executable, '-c', mac_project.GUARD, self.directory.name, script]

    def wait_gone(self, pid):
        deadline = time.monotonic() + 6
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(alive(pid), 'process %d survived the guard' % pid)

    def test_exit_status_and_streams_pass_through(self):
        result = subprocess.run(self.guard('pwd; echo err >&2; exit 7'), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(os.path.realpath(result.stdout.strip()), os.path.realpath(self.directory.name))
        self.assertEqual(result.stderr, 'err\n')

    def test_stdin_passes_through(self):
        result = subprocess.run(self.guard('cat'), input='hello\n', capture_output=True, text=True, timeout=20)
        self.assertEqual(result.stdout, 'hello\n')

    def test_leftover_background_processes_are_cleaned_up(self):
        result = subprocess.run(self.guard('sleep 30 >/dev/null 2>&1 & echo $!'),
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        self.wait_gone(int(result.stdout))

    def test_closed_channel_ends_the_whole_group(self):
        process = subprocess.Popen(self.guard('sleep 30 & echo $!; wait'), stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
        pid = int(process.stdout.readline())
        process.stdout.close()  # What an interrupted SSH channel looks like to the guard.
        self.assertEqual(process.wait(timeout=10), 129)
        self.wait_gone(pid)

    def test_termination_ends_the_whole_group(self):
        process = subprocess.Popen(self.guard('sleep 30 & echo $!; wait'), stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
        pid = int(process.stdout.readline())
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=10), 128 + signal.SIGTERM)
        process.stdout.close()
        self.wait_gone(pid)

    def test_missing_directory_is_reported(self):
        result = subprocess.run([sys.executable, '-c', mac_project.GUARD, '/nonexistent/dir', 'true'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn('cannot enter', result.stderr)


if __name__ == '__main__':
    unittest.main()

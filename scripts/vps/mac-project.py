#!/usr/bin/python3
"""Run project commands on the registered Mac through a pinned SSH connection."""
import json
import os
import pathlib
import shlex
import sys

STATE = pathlib.Path.home() / 'orca-control/mac-connection.json'

# Runs on the Mac (system /usr/bin/python3). The login zsh only supplies the
# environment; the command itself runs in /bin/bash inside its own process group.
# If the SSH channel closes (Claude timeout, interrupt, task stop) the whole group
# is ended, and leftovers of a finished command are cleaned up as well.
GUARD = r'''
import os, select, signal, subprocess, sys, time
project, script = sys.argv[1], sys.argv[2]
try:
    os.chdir(project)
except OSError as error:
    sys.stderr.write('mac-project: cannot enter %s: %s\n' % (project, error.strerror))
    sys.exit(1)
child = subprocess.Popen(['/bin/bash', '-c', script], start_new_session=True)

def end_group():
    for sig, grace in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 1.0)):
        deadline = time.monotonic() + grace
        sent = False
        permission_error = None
        while time.monotonic() < deadline:
            child.poll()
            try:
                os.killpg(child.pid, 0 if sent else sig)
            except ProcessLookupError:
                return
            except PermissionError as error:
                # macOS can report EPERM for a zombie-only group. Reap and
                # retry within this deadline; a persistent denial still fails.
                permission_error = error
            else:
                sent = True
                permission_error = None
            time.sleep(0.05)
        if permission_error is not None:
            raise permission_error

def finish(code):
    end_group()
    os._exit(code)

for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGPIPE):
    signal.signal(number, lambda n, frame: finish(128 + n))
queue = select.kqueue()
for event in (select.kevent(child.pid, select.KQ_FILTER_PROC, select.KQ_EV_ADD, select.KQ_NOTE_EXIT),
              select.kevent(1, select.KQ_FILTER_WRITE, select.KQ_EV_ADD | select.KQ_EV_CLEAR)):
    try:
        queue.control([event], 0)
    except OSError:
        pass
while child.poll() is None:
    for event in queue.control(None, 4, 1.0):
        if event.filter == select.KQ_FILTER_WRITE and event.flags & select.KQ_EV_EOF:
            finish(129)
code = child.returncode
finish(code if code >= 0 else 128 - code)
'''


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('check', 'exec'):
        raise SystemExit('Usage: mac-project check | mac-project exec /absolute/project/path "command"')
    if not STATE.exists():
        raise SystemExit('Mac is not registered. Complete Tailscale and Mac Remote Login registration first.')
    json.loads(STATE.read_text())  # Refuse damaged registration state.
    if sys.argv[1] == 'check':
        if len(sys.argv) != 2:
            raise SystemExit('Usage: mac-project check')
        command = (
            'printf "host: "; hostname; printf "user: "; id -un; '
            'printf "system: "; uname -s; '
            'printf "home: %s\\n" "$HOME"; '
            'printf "git: "; command -v git || true; '
            'printf "node: "; command -v node || true; '
            'printf "python3: "; command -v python3 || true'
        )
    else:
        if len(sys.argv) != 4:
            raise SystemExit('Usage: mac-project exec /absolute/project/path "command" (stdin is forwarded too)')
        project, script = sys.argv[2:]
        if not project.startswith('/') or '\x00' in project or '\n' in project:
            raise SystemExit('Give the full absolute Mac project path; ~ is not expanded here.')
        command = 'exec ' + shlex.join(['/usr/bin/python3', '-c', GUARD, project, script])
    # Streams and exit status remain those of the Mac command.
    remote = 'exec /bin/zsh -lc ' + shlex.quote(command)
    os.execv('/usr/bin/ssh', ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes',
                            '-o', 'ConnectTimeout=10', 'mac-project', remote])


if __name__ == '__main__':
    main()

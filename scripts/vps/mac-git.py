#!/usr/bin/python3
"""git for Mac project sessions: repository commands inside the mount run on the Mac.

Installed as ~/.local/libexec/claude-mac/git for the claude user; claude-mac puts that
directory first on PATH only in Mac project sessions. The CLI's own git calls (session
context status/log, diffs, worktrees) then read the Mac repository directly instead of
crossing SSHFS file by file. Calls outside the mount, or naming VPS paths, use the VPS git.
"""
import os
import shlex
import signal
import subprocess
import sys
import unicodedata

REAL_GIT = '/usr/bin/git'
MAC_PROJECT = '/usr/local/bin/mac-project'
# Global options that take the next argument as their value.
VALUED = {'-C', '-c', '--git-dir', '--work-tree', '--namespace'}
# No repository needed; answering from the VPS git also keeps --exec-path truthful.
LOCAL_COMMANDS = {None, 'version', 'help'}
# Absolute paths in these subcommands' output are mapped back to the mount.
MAPS_OUTPUT = {'rev-parse', 'worktree'}
# Repository locations: mapped when inside the mount, otherwise the call stays on the VPS.
PATH_VARIABLES = {
    'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY',
    'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_CONFIG', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM',
    'GIT_GRAFT_FILE',
}
# VPS programs, credentials and diagnostics; the Mac's own git setup applies there.
VPS_ONLY = ('GIT_ASKPASS', 'GIT_SSH', 'GIT_EXEC_PATH', 'GIT_PROXY_COMMAND', 'GIT_SSL_',
            'GIT_TRACE', 'GIT_TEMPLATE_DIR', 'GIT_CEILING_DIRECTORIES')


def plan(project, mount, cwd, args, environ):
    """Return (Mac directory, shell command, maps output) or None to keep the call on the VPS."""
    def inside(path):
        rel = os.path.relpath(path, mount)
        return rel != '..' and not rel.startswith('../')

    def mapped(text):
        return text.replace(mount, project)

    for arg in args:
        # A VPS path anywhere (clone target, --no-index file, -c value) keeps git on the VPS.
        for value in (arg, arg.partition('=')[2]):
            if value.startswith('/') and value != '/dev/null' and not inside(value):
                return None
    where, index, command, args = cwd, 0, None, list(args)
    while index < len(args):
        option = args[index]
        if not option.startswith('-'):
            command = option
            break
        if option in VALUED:
            index += 1
            if option == '-C' and index < len(args) and args[index]:
                # Absolute and normalized: independent of the VPS cwd, and a path that
                # leaves the mount and re-enters it by name still maps textually.
                where = args[index] = os.path.normpath(os.path.join(where, args[index]))
        index += 1
    if command in LOCAL_COMMANDS or not inside(where):
        return None

    assignments = []
    for name, value in sorted(environ.items()):
        if not name.startswith('GIT_') or name.startswith(VPS_ONLY):
            continue
        if name in PATH_VARIABLES:
            entries = value.split(':') if name == 'GIT_ALTERNATE_OBJECT_DIRECTORIES' else [value]
            if any(entry.startswith('/') and entry != '/dev/null' and not inside(entry) for entry in entries):
                return None
        elif name in ('GIT_EDITOR', 'GIT_SEQUENCE_EDITOR', 'GIT_PAGER') and '/' in value:
            continue
        assignments.append(name + '=' + mapped(value))
    # Discovery stops at the project, as it does at the mount on the VPS: a project
    # inside a larger Mac repository is not silently widened to that repository.
    ceiling = os.path.dirname(project.rstrip('/')) or '/'
    assignments.append('GIT_CEILING_DIRECTORIES=' + ceiling)
    target = mapped(where)
    line = 'exec ' + shlex.join(['env', *assignments, 'git', *map(mapped, args)])
    return target, line, command in MAPS_OUTPUT


def map_output(data, project, mount):
    """Replace Mac project paths with mount paths, in the forms macOS git may print."""
    for form in {project, unicodedata.normalize('NFC', project), unicodedata.normalize('NFD', project)}:
        data = data.replace(form.encode(), mount.encode())
    return data


def main():
    args = sys.argv[1:]
    project = os.environ.get('MAC_PROJECT_DIR', '')
    mount = os.environ.get('MAC_PROJECT_MOUNT', '')
    routed = None
    if project.startswith('/') and mount.startswith('/'):
        try:
            routed = plan(project, mount, os.getcwd(), args, os.environ)
        except OSError:
            routed = None
    if routed is None:
        os.execv(REAL_GIT, [REAL_GIT, *args])
    target, line, maps_output = routed
    if os.isatty(0):
        # The SSH channel would otherwise read the user's terminal.
        os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    argv = [MAC_PROJECT, 'exec', target, line]
    if not maps_output:
        os.execv(MAC_PROJECT, argv)
    child = subprocess.Popen(argv, stdout=subprocess.PIPE)

    def stop(number, frame):
        child.terminate()
        os._exit(128 + number)

    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(number, stop)
    output = child.communicate()[0]
    sys.stdout.buffer.write(map_output(output, project, mount))
    sys.stdout.flush()
    sys.exit(child.returncode if child.returncode >= 0 else 128 - child.returncode)


if __name__ == '__main__':
    main()

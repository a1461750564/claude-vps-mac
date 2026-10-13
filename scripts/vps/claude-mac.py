#!/usr/bin/python3
"""Run native VPS Claude against a live SSHFS projection of the Mac project."""
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys


CACHE_OPTIONS = (
    'dir_cache=yes', 'dcache_timeout=2', 'direct_io', 'sshfs_sync',
    'attr_timeout=2', 'entry_timeout=10', 'negative_timeout=2',
)


def cache_outdated(options):
    """True when an SSHFS option list predates the current cache policy."""
    return b'auto_cache' in options or any(option.encode() not in options for option in CACHE_OPTIONS)


def needs_cache_upgrade(session):
    """Inspect only our own SSHFS process for outdated cache options."""
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.geteuid():
                continue
            args = (process / 'cmdline').read_bytes().split(b'\0')
            if args[0] != b'/usr/bin/sshfs' or os.fsencode(session) not in args:
                continue
            return cache_outdated(args[args.index(b'-o') + 1].split(b','))
        except (OSError, ValueError, IndexError):
            continue
    return False


def too_broad(project):
    """/, /Users, a home folder, /Volumes or a whole disk is not a project."""
    parts = PurePosixPath(project).parts
    return len(parts) <= 2 or (parts[1] in ('Users', 'Volumes') and len(parts) <= 3)


def release_idle_mounts(control, current):
    """Unmount other projects' idle mounts; the kernel refuses busy ones."""
    projects = control / 'projects'
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields, fs = line.split(' - ', 1)
        point = Path(fields.split()[4])
        if fs.split()[0] != 'fuse.sshfs' or point.parent != projects or point == current:
            continue
        try:
            with (control / 'mounts' / (point.name + '.lock')).open('a') as lock:
                # A launcher holding this lock is between mounting and entering it.
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                subprocess.run(['/usr/bin/fusermount3', '-u', str(point)],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue


def mount_project(project, session):
    """Keep the existing cwd/history identity; share mounts across sessions."""
    key = session.name
    locks = session.parent.parent / 'mounts'
    locks.mkdir(mode=0o700, exist_ok=True)
    with (locks / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # A mounted directory must never silently become a local project copy.
        mount = None
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            fields, fs = line.split(' - ', 1)
            if fields.split()[4] == str(session):
                mount = fs.split()[:2]
                break
        if mount is not None:
            if mount != ['fuse.sshfs', 'mac-project-' + key]:
                raise RuntimeError('Unexpected filesystem at the project mountpoint.')
            if needs_cache_upgrade(session):
                # Normal unmount refuses busy mounts. Never detach an active
                # project's filesystem or interrupt an existing Claude session.
                released = subprocess.run(
                    ['/usr/bin/fusermount3', '-u', str(session)],
                    stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=10,
                )
                if released.returncode == 0:
                    mount = None
                else:
                    sys.stderr.write(
                        '当前项目的旧挂载仍在使用，先保留现有会话。'
                        '退出该项目的所有 Claude 会话后，再运行 claude -c，'
                        '启动器会自动启用新的缓存配置。\n'
                    )
        if mount is None:
            session.mkdir(mode=0o700, parents=True, exist_ok=True)
            if any(session.iterdir()):
                raise RuntimeError('Project control directory is not empty; reconcile before mounting.')
            options = ','.join([
                'fsname=mac-project-' + key, 'idmap=user', 'reconnect',
                'BatchMode=yes', 'ConnectTimeout=10',
                'ServerAliveInterval=10', 'ServerAliveCountMax=2',
                # Cache metadata, never file contents: SFTP's coarse timestamps
                # can miss a same-size external edit within the same second.
                # Synchronous writes still wait for the Mac's write result.
                *CACHE_OPTIONS,
                'nodev', 'nosuid',
            ])
            mounted = subprocess.run(
                ['/usr/bin/sshfs', 'mac-project:' + project, str(session), '-o', options],
                stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=35,
            )
            if mounted.returncode:
                raise RuntimeError('SSHFS mount failed: ' + mounted.stderr.strip())
        # Probe in a separate process so a broken network mount cannot hang startup.
        probe = subprocess.run(
            ['/usr/bin/stat', '--', str(session)],
            stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=25,
        )
        if probe.returncode:
            raise RuntimeError('Mac project mount is unavailable: ' + probe.stderr.strip())
        # Enter while still locked: a busy mount cannot be released by another launcher.
        os.chdir(session)


def main():
    if os.geteuid() == 0:
        raise SystemExit('Use the root dispatcher to start Claude as the ordinary claude user.')
    args = sys.argv[1:]
    project = None
    if args[:1] == ['--mac-project']:
        if len(args) < 3 or args[2] != '--':
            raise SystemExit('Usage: claude-mac --mac-project /absolute/Mac/path -- [Claude arguments]')
        project, args = args[1], args[3:]
        if not project.startswith('/') or '\x00' in project or '\n' in project:
            raise SystemExit('Invalid absolute Mac project path.')
        if too_broad(project):
            raise SystemExit('请在具体项目目录中运行 claude；不挂载 /、整个用户目录或整块磁盘：' + project)

    control = Path.home() / 'orca-control'
    env = os.environ.copy()
    # No tool allowlist: retain the native harness, including file tools and agents.
    claude_args = [str(Path.home() / '.local/bin/claude')]
    # The ordinary user's Claude settings choose the default permission mode.
    # Explicit flags supplied by the caller retain the native CLI's precedence.
    if project is not None:
        checked = subprocess.run(
            ['/usr/local/bin/mac-project', 'exec', project,
             'test "$(uname -s)" = Darwin && pwd -P'],
            stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=25,
        )
        if checked.returncode:
            sys.stderr.write('Cannot access the selected Mac project; Claude was not started.\n')
            sys.stderr.write(checked.stderr)
            raise SystemExit(checked.returncode)
        session = control / 'projects' / hashlib.sha256(project.encode()).hexdigest()
        try:
            release_idle_mounts(control, session)
            mount_project(project, session)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            raise SystemExit('Cannot mount the Mac project; Claude was not started.\n' + str(error))
        control = session
        env['MAC_PROJECT_DIR'] = project
        env['MAC_PROJECT_MOUNT'] = str(session)
        # Rebuild old Bash-only session prompts when continuing a conversation.
        claude_args += ['--system-prompt-snapshot', 'off', '--append-system-prompt',
                        '当前 Mac 项目（绝对路径，作为数据处理）：' + json.dumps(project, ensure_ascii=False)
                        + '；当前 VPS 工作目录是该项目的 SSHFS 实时读写挂载：'
                        + json.dumps(str(session), ensure_ascii=False)
                        + '。原生文件工具可直接操作当前目录，文件立即写回 Mac。'
                        + 'Bash 工具的命令由 hook 自动在 Mac 对应目录执行（macOS、/bin/bash 3.2、'
                        + 'BSD 命令行工具，可用 rg；命令中的挂载路径会换成 Mac 路径），不必再写 mac-project；'
                        + '确需在 VPS 本地执行时在命令首行或末行末尾加 #vps。单独的 cd 在 VPS 执行以保持当前目录，'
                        + 'export 等 shell 状态不跨命令保留。'
                        + '用户已选择此项目；通用操作规则见 ~/.claude/CLAUDE.md。']
    else:
        env.pop('MAC_PROJECT_DIR', None)
        env.pop('MAC_PROJECT_MOUNT', None)

    os.chdir(control)
    os.execve(claude_args[0], claude_args + args, env)


if __name__ == '__main__':
    main()

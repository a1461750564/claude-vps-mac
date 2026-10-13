#!/usr/bin/python3
"""Run one Claude Bash command on the Mac, in the directory matching the VPS cwd.

Installed as ~/.local/bin/mac-run for the claude user; called by route-bash-hook.py.
"""
import os
import sys


def main():
    project = os.environ.get('MAC_PROJECT_DIR', '')
    mount = os.environ.get('MAC_PROJECT_MOUNT', '')
    if not project.startswith('/') or not mount.startswith('/') or len(sys.argv) != 2:
        raise SystemExit('mac-run: 当前不是 Mac 项目会话，命令未执行。')
    rel = os.path.relpath(os.getcwd(), mount)
    if rel == '..' or rel.startswith('../'):
        raise SystemExit('mac-run: 当前目录不在 Mac 项目挂载内，命令未执行（没有回落到 VPS）。'
                         '先 cd 回项目目录；确需在 VPS 本地执行时在命令末尾加 #vps。')
    target = project if rel == '.' else project + '/' + rel
    # Absolute paths the model sees are mount paths; they do not exist on the Mac.
    command = sys.argv[1].replace(mount, project)
    os.execv('/usr/local/bin/mac-project', ['/usr/local/bin/mac-project', 'exec', target, command])


if __name__ == '__main__':
    main()

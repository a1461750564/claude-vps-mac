#!/usr/bin/python3
"""PreToolUse(Bash) hook: in Mac project sessions, run Bash commands on the Mac.

Installed as ~/.claude/hooks/route-bash-to-mac.py for the claude user. Commands
stay on the VPS only when they already call mac-project, carry `#vps` at the end of
their first or last line, or are a bare `cd` (the mount mirrors the Mac tree, so
the shell cwd keeps persisting).
Any failure denies the call instead of silently running it on the VPS.
"""
import json
import os
import re
import shlex
import sys

MAC_RUN = os.path.expanduser('~/.local/bin/mac-run')
VPS_MARK = re.compile(r'(^|\s)#vps\s*$')
BARE_CD = re.compile(r'''cd(\s+("[^"]*"|'[^']*'|[^\s;&|<>`$()'"]+))?''')


def decide(event, environ):
    project = environ.get('MAC_PROJECT_DIR')
    mount = environ.get('MAC_PROJECT_MOUNT')
    if not project or not mount:
        return None  # Not a Mac project session.
    tool_input = event['tool_input']
    command = tool_input['command']
    if not isinstance(command, str):
        raise TypeError('Bash command is not a string')
    stripped = command.strip()
    lines = stripped.splitlines() or ['']
    # `#vps` ends the first line (e.g. after a heredoc opener) or the last line.
    if stripped.startswith('mac-project ') or any(VPS_MARK.search(line) for line in (lines[0], lines[-1])):
        return None
    if BARE_CD.fullmatch(stripped):
        if project in stripped:  # A Mac path given to cd maps back to the mount.
            return dict(tool_input, command=stripped.replace(project, mount))
        return None
    return dict(tool_input, command=shlex.quote(MAC_RUN) + ' ' + shlex.quote(command))


def main():
    try:
        updated = decide(json.load(sys.stdin), os.environ)
    except Exception as error:  # Fail closed: never fall back to the VPS silently.
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
            'permissionDecisionReason': 'Mac 路由 hook 出错，命令未执行：%s' % error}}, ensure_ascii=False))
        return
    if updated is not None:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'allow',
            'updatedInput': updated}}, ensure_ascii=False))


if __name__ == '__main__':
    main()

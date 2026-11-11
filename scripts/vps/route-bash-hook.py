#!/usr/bin/python3
"""PreToolUse(Bash) hook: in Mac project sessions, run Bash commands on the Mac.

Installed as ~/.claude/hooks/route-bash-to-mac.py for the claude user. Commands
stay on the VPS when they carry `#vps` at the end of their first or last line, are
a bare `cd` (the mount mirrors the Mac tree, so the shell cwd keeps persisting), or
run a program that exists only on the VPS: mac-project itself, ~/.claude files (skill
scripts), or files under the VPS home or Claude temp directory outside the mount.
The rest of such a command runs there too, except project toolchains (package
managers, builds, tests, project scripts): mixed with those it is refused, not guessed.
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
HEREDOC = re.compile(r'''(?<!<)<<(?!<)(-?)\s*(["']?)([A-Za-z_][A-Za-z0-9_]*)\2''')
QUOTED_OR_ESCAPED = re.compile(r'''\\[^\n]|'[^']*'|"(?:[^"\\]|\\.)*"''', re.DOTALL)
PUNCTUATION = '();&|<>'
LITERAL_PUNCTUATION = str.maketrans({char: '\0%d' % index for index, char in enumerate(PUNCTUATION)})
# After these words the next word is a command; after the closing ones it is not.
OPENS = {'then', 'do', 'else', 'elif', 'if', 'while', 'until', '!', 'time', '{'}
CLOSES = {'done', 'fi', 'esac', '}', 'for', 'case', 'select', 'function'}
INTERPRETERS = {'sh', 'bash', 'zsh', 'dash', 'python', 'python3', 'node', 'perl', 'ruby'}
# Project toolchains must run on the Mac; next to a VPS-only program they are refused.
TOOLCHAIN = {
    'npm', 'npx', 'pnpm', 'yarn', 'bun', 'deno', 'corepack', 'make', 'cmake', 'cargo', 'go', 'swift',
    'xcodebuild', 'xcrun', 'pod', 'pip', 'pip3', 'uv', 'poetry', 'pytest', 'tox', 'tsc', 'vite', 'vitest',
    'jest', 'playwright', 'electron-forge', 'envkit', 'brew', 'open', 'osascript', 'launchctl', 'sudo',
}
INLINE = {'-c', '-e', '-', '--eval'}


class Refused(Exception):
    """A command that cannot run correctly on either host as written."""


def protect_punctuation(command):
    # shlex strips quoting and would otherwise make a literal '|' look like a pipe.
    return QUOTED_OR_ESCAPED.sub(lambda match: match[0].translate(LITERAL_PUNCTUATION), command)


def restore_punctuation(word):
    return re.sub(r'\x00([0-6])', lambda match: PUNCTUATION[int(match[1])], word)


def without_heredoc_bodies(command):
    """Heredoc bodies are data: drop them so their lines are not read as commands."""
    kept, pending = [], []
    for line in command.split('\n'):
        if pending:
            strip_tabs, delimiter = pending[0]
            if (line.lstrip('\t') if strip_tabs else line) == delimiter:
                pending.pop(0)
            continue
        kept.append(line)
        pending += [(match.group(1) == '-', match.group(3))
                    for match in HEREDOC.finditer(protect_punctuation(line))]
    return '\n'.join(kept)


def tokens(command):
    """Shell words and operators, with ';' between lines. ValueError if unparsable."""
    result, chunk = [], ''
    for line in without_heredoc_bodies(command).split('\n'):
        chunk = chunk + '\n' + line if chunk else line
        lexer = shlex.shlex(protect_punctuation(chunk), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            words = list(lexer)
        except ValueError:
            continue  # A quote or escape continues on the next line.
        result += words + [';']
        chunk = ''
    if chunk:
        raise ValueError('unbalanced quotes')
    return result


def programs(command):
    """(command word, program file) for every simple command; the file differs for interpreters."""
    found, expecting, skip_target = [], True, False
    words = tokens(command)
    for index, word in enumerate(words):
        if skip_target:
            skip_target = False
            continue
        if word and set(word) <= set('();&|'):
            expecting = True
        elif word and set(word) <= set('<>&|0123456789') and ('<' in word or '>' in word):
            skip_target = True  # Redirection target, not a command.
        elif not expecting:
            continue
        elif word in OPENS:
            pass
        elif word in CLOSES:
            expecting = False
        elif re.match(r'[A-Za-z_][A-Za-z0-9_]*=', word):
            pass  # Assignment prefix.
        else:
            program = word
            if os.path.basename(word) in INTERPRETERS:
                program = '-'  # Inline code or stdin unless a script file follows.
                for argument in words[index + 1:]:
                    if set(argument) <= set('();&|<>') or argument in INLINE:
                        break
                    if not argument.startswith('-'):
                        program = argument
                        break
            found.append((restore_punctuation(word), restore_punctuation(program)))
            expecting = False
    return found


def vps_only(program, environ):
    """mac-project, or a file that exists only on the VPS (outside the project mount)."""
    if os.path.basename(program) == 'mac-project':
        return True
    home = environ.get('HOME') or os.path.expanduser('~')
    # `~` also exists on the Mac; only the CLI's own ~/.claude (skills, agents) is the VPS's.
    for prefix in ('~/.claude/', '$HOME/.claude/', '${HOME}/.claude/'):
        if program.startswith(prefix):
            program = home.rstrip('/') + '/.claude/' + program[len(prefix):]
    mount = environ['MAC_PROJECT_MOUNT'].rstrip('/')
    roots = (home.rstrip('/') + '/', '/tmp/claude-%d/' % os.getuid())
    if program == mount or program.startswith(mount + '/') or not program.startswith(roots):
        return False
    # The state directory may be reached through an alias (~/claude-vps-mac -> original);
    # a project file named that way is still the mount, not a VPS-only program.
    real = os.path.realpath(program)
    return not (real == mount or real.startswith(mount + '/'))


def project_program(word, program, environ):
    if os.path.basename(word) in TOOLCHAIN:
        return True
    if vps_only(program, environ):
        return False
    if program != word and program != '-':
        return True
    if not os.path.isabs(program):
        return '/' in program
    mount_prefix = environ['MAC_PROJECT_MOUNT'].rstrip('/') + '/'
    return (program.startswith(environ['MAC_PROJECT_DIR'].rstrip('/') + '/')
            or program.startswith(mount_prefix)
            or os.path.realpath(program).startswith(mount_prefix))


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
    if any(VPS_MARK.search(line) for line in (lines[0], lines[-1])):
        return None
    if BARE_CD.fullmatch(stripped):
        if project in stripped:  # A Mac path given to cd maps back to the mount.
            return dict(tool_input, command=stripped.replace(project, mount))
        return None
    try:
        found = programs(stripped)
    except ValueError:  # Unparsable here; the Mac shell reports its own syntax errors.
        found = [('mac-project', 'mac-project')] if stripped.startswith('mac-project ') else []
    vps = [word for word, program in found if vps_only(program, environ)]
    if vps:
        mac = sorted({word for word, program in found if project_program(word, program, environ)})
        if mac:
            raise Refused('命令同时含只在 VPS 存在的程序（%s）和应在 Mac 执行的项目命令（%s），未执行。'
                          '请拆成两条：VPS 部分末尾加 #vps，项目命令照常在 Mac 执行。'
                          % (', '.join(sorted(set(vps))), ', '.join(mac)))
        return None  # mac-project or a VPS-only program cannot run on the Mac.
    return dict(tool_input, command=shlex.quote(MAC_RUN) + ' ' + shlex.quote(command))


def deny(reason):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
        'permissionDecisionReason': reason}}, ensure_ascii=False))


def main():
    try:
        updated = decide(json.load(sys.stdin), os.environ)
    except Refused as error:
        deny(str(error))
        return
    except Exception as error:  # Fail closed: never fall back to the VPS silently.
        deny('Mac 路由 hook 出错，命令未执行：%s' % error)
        return
    if updated is not None:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'allow',
            'updatedInput': updated}}, ensure_ascii=False))


if __name__ == '__main__':
    main()

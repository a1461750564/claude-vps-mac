#!/usr/bin/python3
"""PATH rg for Claude's Glob/Grep: search the Mac, keep VPS paths and tool data intact."""
import base64
import json
import os
import shlex
import signal
import subprocess
import sys
import unicodedata

REAL_RG = '/usr/bin/rg'
MAC_PROJECT = '/usr/local/bin/mac-project'
VALUES = {
    '-A', '-B', '-C', '-d', '-e', '-f', '-g', '-j', '-m', '-M', '-r', '-t', '-T',
    '--after-context', '--before-context', '--context', '--max-depth', '--regexp',
    '--file', '--glob', '--iglob', '--threads', '--max-count', '--replace', '--type',
    '--type-not', '--encoding', '--engine', '--color', '--colors', '--context-separator',
    '--field-context-separator', '--field-match-separator', '--type-add', '--type-clear',
    '--sort', '--sortr', '--path-separator', '--max-filesize', '--max-columns', '--dfa-size-limit',
    '--regex-size-limit', '--ignore-file', '--pre', '--pre-glob', '--hostname-bin',
}
PATH_VALUES = {'-f', '--file', '--ignore-file'}


def plan(project, mount, cwd, args, environ):
    """Return (Mac cwd, command, output mode), or None for VPS-local calls."""
    def inside(path):
        relative = os.path.relpath(path, mount)
        return relative != '..' and not relative.startswith('../')

    def path(value):
        if value == '-':
            return value
        absolute = os.path.normpath(os.path.join(cwd, value))
        if not inside(absolute):
            raise ValueError('VPS path')
        relative = os.path.relpath(absolute, mount)
        return project if relative == '.' else project + '/' + relative

    if not inside(cwd) or any(arg in ('--version', '-V', '--help', '-h', '--heading', '--pretty', '--null-data', '--type-list') for arg in args):
        return None
    if any(arg in ('--color=always', '--color=ansi') or
           arg == '--color' and index + 1 < len(args) and args[index + 1] in ('always', 'ansi')
           for index, arg in enumerate(args)):
        return None
    if any(arg.split('=', 1)[0] in ('--pre', '--pre-glob', '--hostname-bin', '--path-separator',
                                  '--field-match-separator', '--field-context-separator') for arg in args):
        return None  # Host programs or custom output delimiters keep their VPS semantics.
    config = environ.get('RIPGREP_CONFIG_PATH')
    if config and '--no-config' not in args:
        return None
    mapped, paths = [], []
    pattern = any(arg in ('--files', '-e', '--regexp', '-f', '--file') or arg.startswith('--regexp=') or
                  arg.startswith('--file=') or
                  (arg.startswith(('-e', '-f')) and len(arg) > 2) for arg in args)
    index, positional = 0, False
    try:
        while index < len(args):
            arg = args[index]
            if arg == '--' and not positional:
                positional = True
                mapped.append(arg)
            elif arg.startswith('-') and arg != '-' and not positional:
                option, equals, value = arg.partition('=')
                if option in VALUES:
                    if equals:
                        mapped.append(option + '=' + (path(value) if option in PATH_VALUES else value))
                    else:
                        mapped.append(arg)
                        index += 1
                        if index >= len(args):
                            return None  # Let rg report invalid arguments unchanged.
                        mapped.append(path(args[index]) if option in PATH_VALUES else args[index])
                elif arg[:2] in PATH_VALUES and len(arg) > 2:
                    mapped.append(arg[:2] + path(arg[2:]))
                else:
                    mapped.append(arg)
            elif not pattern:
                mapped.append(arg)  # A regexp is data, even when it looks like an absolute path.
                pattern = True
            else:
                paths.append(os.path.normpath(os.path.join(cwd, arg)))
                mapped.append(path(arg))
            index += 1
    except ValueError:
        return None
    if '--json' in args:
        mode = 'json'
    elif any(arg in ('--files', '-l', '--files-with-matches', '--files-without-match') for arg in args):
        mode = 'paths-null' if '--null' in args or '-0' in args else 'paths'
    elif '--no-filename' in args or '-I' in args:
        mode = 'text'
    elif '--with-filename' in args or '-H' in args or '--vimgrep' in args or not paths or len(paths) > 1 or os.path.isdir(paths[0]):
        mode = 'prefixed-null' if '--null' in args or '-0' in args else 'prefixed'
    else:
        mode = 'text'
    target = path(cwd)
    return target, 'exec ' + shlex.join(['rg', *mapped]), mode


def map_path(data, project, mount):
    for form in {project, unicodedata.normalize('NFC', project), unicodedata.normalize('NFD', project)}:
        prefix = form.encode()
        if data == prefix or data.startswith(prefix + b'/'):
            return mount.encode() + data[len(prefix):]
    return data


def map_output(data, project, mount, mode):
    if mode == 'text':
        return data
    if mode == 'json':
        event = json.loads(data)
        field = event.get('data', {}).get('path')
        if field:
            if 'text' in field:
                field['text'] = map_path(field['text'].encode(), project, mount).decode()
            elif 'bytes' in field:
                field['bytes'] = base64.b64encode(map_path(base64.b64decode(field['bytes']), project, mount)).decode()
        return json.dumps(event, ensure_ascii=False).encode() + b'\n'
    return map_path(data, project, mount)


def main():
    args = sys.argv[1:]
    project, mount = os.environ.get('MAC_PROJECT_DIR', ''), os.environ.get('MAC_PROJECT_MOUNT', '')
    routed = plan(project, mount, os.getcwd(), args, os.environ) if project.startswith('/') and mount.startswith('/') else None
    if routed is None:
        os.execv(REAL_RG, [REAL_RG, *args])
    target, command, mode = routed
    if os.isatty(0):
        with open(os.devnull, 'rb') as empty:
            os.dup2(empty.fileno(), 0)
    child = subprocess.Popen([MAC_PROJECT, 'exec', target, command], stdout=subprocess.PIPE)

    def stop(number, frame):
        child.terminate()
        child.wait(timeout=10)
        os._exit(128 + number)

    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(number, stop)
    try:
        # Filename-NUL output is framed by NUL; other modes by newline. Preserve
        # match text, including occurrences of the Mac project path, byte for byte.
        if mode == 'paths-null':
            pending = b''
            while True:
                chunk = child.stdout.read1(65536)
                if not chunk:
                    break
                items = (pending + chunk).split(b'\0')
                pending = items.pop()
                for item in items:
                    sys.stdout.buffer.write(map_output(item, project, mount, mode) + b'\0')
            sys.stdout.buffer.write(map_output(pending, project, mount, mode))
        else:
            for line in child.stdout:
                sys.stdout.buffer.write(map_output(line, project, mount, mode))
        sys.stdout.flush()
    except BrokenPipeError:
        child.terminate()
        child.wait(timeout=10)
        os._exit(141)
    finally:
        child.stdout.close()
    code = child.wait()
    sys.exit(code if code >= 0 else 128 - code)


if __name__ == '__main__':
    main()

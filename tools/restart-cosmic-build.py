#!/usr/bin/env python3
"""Finish the current COSMIC package, then restart its controller with new jobs.

Usage: python3 tools/restart-cosmic-build.py --pid CONTROLLER_PID --jobs 6
The controller must be this checkout's build-cosmic.py. Only its Python process
is stopped; its package build continues. A checkpoint is adopted only after the
build exits successfully, sources remain unchanged, and repository metadata
matches. The original --install choice is preserved. Linux pidfds prevent
signals from reaching a reused process ID. Logs remain in hostdir/cosmic-build.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_cosmic', ROOT / 'tools/build-cosmic.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def interrupted(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--jobs', required=True, type=int)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    proc = Path('/proc') / str(args.pid)
    command = [word.decode() for word in (proc / 'cmdline').read_bytes().split(b'\0') if word]
    if (len(command) < 2 or not Path(command[0]).name.startswith('python')
            or Path(command[1]).name != 'build-cosmic.py'
            or Path(os.readlink(proc / 'cwd')) != ROOT):
        raise RuntimeError('PID is not this checkout\'s COSMIC build controller')
    descriptor = os.pidfd_open(args.pid)
    killed = False
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
        while (proc / 'stat').read_text().split(') ', 1)[1].split()[0] not in ('T', 't'):
            time.sleep(0.02)
        children = (proc / f'task/{args.pid}/children').read_text().split()
        active = []
        for child in children:
            words = [word.decode() for word in Path(f'/proc/{child}/cmdline').read_bytes().split(b'\0') if word]
            if 'build' in words and any(word == str(ROOT / 'voidlab') for word in words):
                name = words[words.index('build') + 1]
                if (ROOT / 'srcpkgs' / name / 'template').is_file():
                    active.append((child, name))
        if len(active) != 1:
            raise RuntimeError('expected exactly one active package build; controller was resumed')
        child, name = active[0]
        previous = ROOT / '.upstream/srcpkgs' / name
        current = ROOT / 'srcpkgs' / name
        if (not build.compatible_resume(previous, current)
                or (previous / 'template').read_bytes() != (current / 'template').read_bytes()):
            raise RuntimeError('active build sources differ from the canonical template')
        signature = build.fingerprint(name)
        print(f'Finishing {name} before restarting with {args.jobs} jobs.', flush=True)
        while True:
            fields = Path(f'/proc/{child}/stat').read_text().split(') ', 1)[1].split()
            if fields[0] == 'Z':
                if int(fields[49]) != 0:
                    raise RuntimeError(f'{name}: package build failed; controller was resumed')
                break
            time.sleep(1)
        if build.fingerprint(name) != signature:
            raise RuntimeError('sources changed during compilation; refusing to adopt checkpoint')
        expected = f'{name}-{build.package_version(name)}'
        if build.output('xbps-query', '-i', '--repository=' + str(ROOT / 'repo'), '-p', 'pkgver', name) != expected:
            raise RuntimeError('built repository version does not match the template')
        state = json.loads((build.STATE / 'state.json').read_text())
        state['built'][name] = signature
        state['jobs_restart'] = {'completed_package': name, 'jobs': args.jobs}
        build.save(state)
        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        killed = True
        print(f'Checkpoint verified for {expected}; restarting controller.', flush=True)
    finally:
        if not killed:
            try:
                signal.pidfd_send_signal(descriptor, signal.SIGCONT)
            except ProcessLookupError:
                pass
        os.close(descriptor)
    os.chdir(ROOT)
    restart = [sys.executable, str(ROOT / 'tools/build-cosmic.py'), '--jobs', str(args.jobs)]
    if '--install' in command:
        restart.append('--install')
    os.execv(sys.executable, restart)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, KeyboardInterrupt) as error:
        sys.exit(f'restart-cosmic-build: {error or "interrupted; controller resumed"}')

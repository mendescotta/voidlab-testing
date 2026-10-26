#!/usr/bin/env python3
"""Resume local COSMIC builds and optionally install updates to installed packages.

Usage: python3 tools/build-cosmic.py [--install] [--jobs 3] [--status]
Builds every active COSMIC template, pop-launcher, and the COSMIC portal.
Checkpoints include package sources and build-helper fingerprints, so a changed
template or patch rebuilds its package. Logs and the initial installed-package
list persist in hostdir/cosmic-build. Installation requires --install, verifies
exact versions, previews the transaction and upgrades the existing COSMIC
package set, or installs the full desktop when COSMIC is absent. Does not
publish packages or restart desktop services.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'hostdir/cosmic-build'
sys.dont_write_bytecode = True


def output(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def package_version(package):
    text = (ROOT / 'srcpkgs' / package / 'template').read_text()
    return '_'.join(re.search(rf'^{field}=([^\s]+)', text, re.M)[1] for field in ('version', 'revision'))


def fingerprint(package):
    digest = hashlib.sha256()
    paths = sorted((ROOT / 'srcpkgs' / package).rglob('*'))
    paths += [ROOT / 'voidlab']
    paths += sorted((ROOT / 'common').rglob('*'))
    digest.update(output('git', '-C', str(ROOT / '.upstream'), 'rev-parse', 'HEAD').encode())
    for path in paths:
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def save(state):
    temporary = STATE / 'state.tmp'
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(STATE / 'state.json')


def run_logged(args, path, env=None, cwd=ROOT):
    with path.open('w') as stream:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join(path.read_text(errors='replace').splitlines()[-35:]), flush=True)
        raise RuntimeError(f'command failed ({result.returncode}); log: {path}')


def compatible_resume(previous, current):
    """Allow identical sources or a single-line configure_args change only."""
    before = {p.relative_to(previous): p.read_bytes() for p in previous.rglob('*') if p.is_file()}
    after = {p.relative_to(current): p.read_bytes() for p in current.rglob('*') if p.is_file()}
    if before.keys() != after.keys():
        return False
    for path in before:
        if path == Path('template'):
            clean = lambda data: re.sub(rb'^configure_args="[^"\n]*"\n', b'', data, flags=re.M)
            if clean(before[path]) != clean(after[path]):
                return False
        elif before[path] != after[path]:
            return False
    return True


def resume_package(name, jobs, env):
    previous = ROOT / '.upstream/srcpkgs' / name
    current = ROOT / 'srcpkgs' / name
    if not compatible_resume(previous, current):
        raise RuntimeError(f'{name}: cached sources differ beyond configure_args; use a normal clean build')
    if subprocess.run(['pgrep', '-x', 'xbps-src'], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError('another xbps-src build is running; retry when it finishes')
    version = package_version(name).rsplit('_', 1)[0]
    if not (ROOT / 'masterdir/builddir' / f'{name}-{version}').is_dir():
        raise RuntimeError(f'{name}: no preserved build directory')
    shutil.copy2(current / 'template', previous / 'template')
    run_logged([str(ROOT / '.upstream/xbps-src'), '-j', str(jobs),
                '-H', str(ROOT / 'hostdir'), '-m', str(ROOT / 'masterdir'), 'pkg', name],
               STATE / (name + '-resume.log'), env, cwd=ROOT / '.upstream')
    expected = f'{name}-{package_version(name)}'
    archives = list((ROOT / 'hostdir/binpkgs').rglob(expected + '.*.xbps'))
    if not archives:
        raise RuntimeError(f'{name}: resumed build did not produce {expected}')
    archive = max(archives, key=lambda path: path.stat().st_mtime)
    destination = ROOT / 'repo' / archive.name
    shutil.copy2(archive, destination)
    subprocess.run(['xbps-rindex', '-f', '-a', str(destination)], cwd=ROOT, check=True)


def wait_for_build_slot():
    waiting = False
    while subprocess.run(['pgrep', '-x', 'xbps-src'], stdout=subprocess.DEVNULL).returncode == 0:
        if not waiting:
            print('Waiting for the other xbps-src build to finish...', flush=True)
            waiting = True
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--status', action='store_true', help='show checkpoint progress and the latest compiler log without building')
    parser.add_argument('--resume-package', help='reuse a preserved build directory when only configure_args changed')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.status:
        checkpoint = STATE / 'state.json'
        state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {'built': {}}
        print(f'Completed package checkpoints: {len(state["built"])}')
        print(' '.join(state['built']))
        logs = list((ROOT / 'hostdir').glob('voidlab-build-cosmic*.log'))
        logs += list((ROOT / 'hostdir').glob('voidlab-build-pop-launcher.log'))
        logs += list((ROOT / 'hostdir').glob('voidlab-build-xdg-desktop-portal-cosmic.log'))
        logs += list(STATE.glob('*-resume.log'))
        if logs:
            latest = max(logs, key=lambda path: path.stat().st_mtime)
            print(f'Latest compiler log: {latest}')
            print('\n'.join(latest.read_text(errors='replace').splitlines()[-4:]))
        return
    STATE.mkdir(parents=True, exist_ok=True)
    names = {p.parent.name for p in (ROOT / 'srcpkgs').glob('cosmic*/template')}
    names.update(('pop-launcher', 'xdg-desktop-portal-cosmic'))
    first = ['cosmic-icons', 'cosmic-sound-theme', 'cosmic-wallpapers', 'cosmic-randr',
             'pop-launcher', 'cosmic-comp', 'cosmic-settings-daemon', 'cosmic-session']
    last = ['cosmic-desktop-minimal', 'cosmic-desktop']
    packages = first + sorted(names - set(first) - set(last)) + last
    if args.resume_package and args.resume_package not in names:
        parser.error('--resume-package must name an active COSMIC package')
    state_file = STATE / 'state.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {'built': {}}
    if 'installed_before' not in state:
        installed = output('xbps-query', '-l')
        (STATE / 'installed-before.txt').write_text(installed + '\n')
        state['installed_before'] = [name for name in sorted(names)
                                     if subprocess.run(['xbps-query', '-p', 'pkgver', name],
                                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0]
        save(state)
    templates = [str(ROOT / 'srcpkgs' / name / 'template') for name in packages]
    run_logged(['xlint', *templates], STATE / 'lint.log')
    for template in templates:
        subprocess.run(['bash', '-n', template], check=True)
    env = os.environ.copy()
    env['VOIDLAB_MAKEJOBS'] = str(args.jobs)
    for name in packages:
        expected = f'{name}-{package_version(name)}'
        signature = fingerprint(name)
        built = subprocess.run(['xbps-query', '-i', '--repository=' + str(ROOT / 'repo'),
                                '-p', 'pkgver', name], text=True, capture_output=True)
        if state['built'].get(name) == signature and built.stdout.strip() == expected:
            print(f'Already built: {expected}', flush=True)
            continue
        print(f'Building {expected}; log: {STATE / (name + ".log")}', flush=True)
        wait_for_build_slot()
        if name == args.resume_package:
            resume_package(name, args.jobs, env)
        else:
            run_logged([str(ROOT / 'voidlab'), 'build', name], STATE / (name + '.log'), env)
        built = output('xbps-query', '-i', '--repository=' + str(ROOT / 'repo'), '-p', 'pkgver', name)
        if built != expected:
            raise RuntimeError(f'{name}: expected {expected}, repository contains {built}')
        state['built'][name] = signature
        save(state)
    run_logged([str(ROOT / 'voidlab'), 'test', *packages], STATE / 'package-checks.log')
    print(f'All {len(packages)} packages built and checked.', flush=True)
    if args.install:
        # Exact package versions prevent a configured remote repository winning.
        transaction = ['sudo', '-n', 'xbps-install', '--repository=' + str(ROOT / 'repo')]
        targets = state['installed_before'] or ['cosmic-desktop']
        install = [f'{name}-{package_version(name)}' for name in targets]
        preview = output(*transaction, '-n', *install)
        (STATE / 'install-preview.txt').write_text(preview + '\n')
        print(preview, flush=True)
        subprocess.run([*transaction, '-y', *install], cwd=ROOT, check=True)
        for name in targets:
            actual = output('xbps-query', '-p', 'pkgver', name)
            if actual != f'{name}-{package_version(name)}':
                raise RuntimeError(f'{name}: installed version mismatch: {actual}')
        state['installed_after'] = {name: output('xbps-query', '-p', 'pkgver', name)
                                    for name in packages
                                    if subprocess.run(['xbps-query', '-p', 'pkgver', name],
                                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0}
        for name, installed in state['installed_after'].items():
            if installed != f'{name}-{package_version(name)}':
                raise RuntimeError(f'{name}: installed dependency version mismatch: {installed}')
        save(state)
        print(f'Installed and verified {len(state["installed_after"])} COSMIC packages.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f'build-cosmic: {error}')

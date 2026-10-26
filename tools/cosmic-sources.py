#!/usr/bin/env python3
"""Verify COSMIC release archives and patches; optionally prepare a release bump.

Usage: python3 tools/cosmic-sources.py [--cache /path/to/cache]
       python3 tools/cosmic-sources.py --version 1.11.0 --update
       python3 tools/cosmic-sources.py --just /path/to/just

Selects pop-os COSMIC templates, pop-launcher and cosmic-tweaks. The independent
tweaks version is verified but not bumped with --version. Templates are read
as data, never executed. Downloads use curl; extraction requires Python 3.12+.
Checksums and patch applicability are checked before --update writes templates.
The cache keeps archives, source trees, and a JSON report for later review.
This checks source packaging; it does not replace xbps-src builds/runtime tests.
"""

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]


def assignment(text, name):
    match = re.search(rf'^{name}=(?:"([^"\n]*)"|([^\s\n]+))$', text, re.M)
    if not match:
        raise ValueError(f'expected a single-line {name} assignment')
    return match[1] if match[1] is not None else match[2]


def verify(template, cache, version, just=None):
    text = template.read_text()
    package = template.parent.name
    current = assignment(text, 'version')
    repo = assignment(text, 'homepage').removeprefix('https://github.com/')
    coordinated = repo.startswith('pop-os/')
    release = (version or current) if coordinated else current
    tag = ('epoch-' if coordinated else '') + release
    url = f'https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz'
    archive = cache / f'{package}-{release}.tar.gz'
    if not archive.exists():
        partial = archive.with_suffix('.part')
        subprocess.run(['curl', '-fL', '--retry', '2', '--connect-timeout', '15',
                        '--max-time', '300', '-sS', url, '-o', str(partial)], check=True)
        partial.replace(archive)
    with archive.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    if release == current and checksum != assignment(text, 'checksum'):
        raise ValueError(f'{package}: archive checksum does not match template')

    # Recreate only this tool's generated extraction directory, never a Cargo cache.
    extracted = cache / 'sources' / f'{package}-{release}'
    if extracted.exists():
        shutil.rmtree(extracted)
    extracted.mkdir(parents=True)
    with tarfile.open(archive) as source:
        source.extractall(extracted, filter='data')
    directories = list(extracted.iterdir())
    if len(directories) != 1 or not directories[0].is_dir():
        raise ValueError(f'{package}: expected one archive root directory')
    source = directories[0]
    patchdir = template.parent / 'patches'
    series = patchdir / 'series'
    patches = ([patchdir / line.strip() for line in series.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('#')]
               if series.exists() else sorted([*patchdir.glob('*.patch'), *patchdir.glob('*.diff')]))
    logs = []
    for patch in patches:
        # Refuse a patch that applies only with fuzz, reversed hunks, or offsets.
        result = subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1',
                                 '-i', str(patch)], cwd=source, capture_output=True, text=True)
        logs.append(result.stdout + result.stderr)
        if result.returncode or 'offset ' in result.stdout:
            raise ValueError(f'{package}/{patch.name}: patch needs refreshing\n{logs[-1]}')
    result = dict(package=package, version=release, url=url, checksum=checksum,
                  source=str(source), patches=[p.name for p in patches], patch_log=logs)
    licenses = Counter()
    for rust_source in source.rglob('*.rs'):
        licenses.update(re.findall(r'SPDX-License-Identifier:\s*([^\n]+)',
                                   rust_source.read_text(errors='replace')))
    result['source_license_identifiers'] = dict(sorted(licenses.items()))
    if just and ((source / 'justfile').exists() or (source / 'Justfile').exists()) and package not in ('cosmic-greeter', 'cosmic-tweaks'):
        args = [just, '--dry-run', f'rootdir={cache / "stage" / package}']
        if package == 'cosmic-applets':
            args.append('target=x86_64-unknown-linux-gnu/release')
        elif package == 'pop-launcher':
            args.append('target-dir=target/x86_64-unknown-linux-gnu/release')
        elif package != 'cosmic-icons':
            args.append('cargo-target-dir=target/x86_64-unknown-linux-gnu')
        install = subprocess.run([*args, 'install'], cwd=source, capture_output=True, text=True, check=True)
        result['install_dry_run'] = install.stdout + install.stderr
    print(f'{package}: {release}, checksum verified, {len(patches)} patches', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cache', type=Path, default=ROOT / 'hostdir/cosmic-source-review')
    parser.add_argument('--version', help='release version to check instead of each template version')
    parser.add_argument('--update', action='store_true', help='update versions/checksums after all checks pass')
    parser.add_argument('--just', help='also parse upstream install recipes with this just executable (dry run)')
    args = parser.parse_args()
    if args.version and not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        parser.error('--version must have the form 1.11.0')
    if args.update and not args.version:
        parser.error('--update requires --version')
    just = shutil.which(args.just) if args.just else None
    if args.just and not just:
        parser.error('--just executable not found')
    if just:
        just = str(Path(just).resolve())
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    templates = sorted((ROOT / 'srcpkgs').glob('cosmic*/template'))
    templates += [ROOT / f'srcpkgs/{p}/template' for p in ('pop-launcher', 'xdg-desktop-portal-cosmic')]
    templates = [t for t in templates if 'metapackage=' not in t.read_text()
                 and any(repo in t.read_text() for repo in ('https://github.com/pop-os/',
                                                          'https://github.com/cosmic-utils/cosmic-ext-tweaks'))]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda t: verify(t, cache, args.version, just), templates))
        (cache / 'report.json').write_text(json.dumps(results, indent=2) + '\n')
        if args.update:
            for result in results:
                path = ROOT / 'srcpkgs' / result['package'] / 'template'
                text = path.read_text()
                if assignment(text, 'version') != result['version']:
                    text = re.sub(r'^revision=.*$', 'revision=1', text, flags=re.M)
                text = re.sub(r'^version=.*$', 'version=' + result['version'], text, flags=re.M)
                text = re.sub(r'^checksum=.*$', 'checksum=' + result['checksum'], text, flags=re.M)
                path.write_text(text)
            for name in ('cosmic-desktop', 'cosmic-desktop-minimal'):
                path = ROOT / 'srcpkgs' / name / 'template'
                text = path.read_text()
                if assignment(text, 'version') != args.version:
                    text = re.sub(r'^revision=.*$', 'revision=1', text, flags=re.M)
                path.write_text(re.sub(r'^version=.*$', 'version=' + args.version, text, flags=re.M))
        print(f'Verified {len(results)} source packages; report: {cache / "report.json"}')
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'cosmic-sources: {error}\n')


if __name__ == '__main__':
    main()

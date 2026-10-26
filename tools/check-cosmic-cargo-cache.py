#!/usr/bin/env python3
"""Check tracked changes in cached Git dependencies pinned by COSMIC lockfiles.

Run cosmic-sources.py first, then:
  python3 tools/check-cosmic-cargo-cache.py --report /path/to/report.json
Missing checkouts are reported as not fetched, since conditional dependencies
need not be downloaded on this architecture. Dirty referenced checkouts fail the
audit. Dirty unused revisions are reported separately. No checkout is changed.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args):
    result = subprocess.run(['git', '--no-optional-locks', '-C', str(path), *args],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def tracked_changes(path):
    # Cargo places untracked .cargo-ok markers in submodules. Ignore those,
    # while still detecting changed tracked files and submodule commit drift.
    return git(path, 'status', '--porcelain', '--untracked-files=no', '--ignore-submodules=untracked')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', type=Path, default=ROOT / 'hostdir/cosmic-source-review/report.json')
    parser.add_argument('--cache', type=Path, default=ROOT / 'hostdir/cargo/git/checkouts')
    parser.add_argument('--output', type=Path, default=ROOT / 'hostdir/cosmic-build/cargo-cache-audit.json')
    args = parser.parse_args()
    pinned = {}
    for source in json.loads(args.report.read_text()):
        directory = Path(source['source'])
        if not directory.is_dir():
            raise ValueError(f'{directory}: source tree missing; rerun cosmic-sources.py')
        lock = directory / 'Cargo.lock'
        if not lock.is_file():
            continue
        for package in tomllib.loads(lock.read_text()).get('package', []):
            origin = package.get('source', '')
            if origin.startswith('git+') and '#' in origin:
                revision = origin.rsplit('#', 1)[1]
                pinned.setdefault(revision, set()).add(source['package'])
    checked, dirty, unused_dirty = set(), [], []
    for directory in sorted(args.cache.glob('*/*')):
        if not directory.is_dir():
            continue
        top = git(directory, 'rev-parse', '--show-toplevel')
        if not top or Path(top).resolve() != directory.resolve():
            continue
        revision = git(directory, 'rev-parse', 'HEAD')
        changes = tracked_changes(directory)
        if changes is None:
            raise ValueError(f'{directory}: cannot inspect checkout status')
        if revision in pinned:
            checked.add(revision)
        if changes:
            finding = dict(path=str(directory), revision=revision, changes=changes,
                           packages=sorted(pinned.get(revision, [])))
            (dirty if revision in pinned else unused_dirty).append(finding)
    result = dict(checked_revisions=len(checked), not_fetched=sorted(set(pinned) - checked),
                  dirty_referenced=dirty, dirty_unused=unused_dirty)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Checked {len(checked)} pinned cached revisions; {len(dirty)} dirty referenced checkouts.')
    print(f'{len(result["not_fetched"])} pinned revisions not fetched; {len(unused_dirty)} dirty unused checkouts.')
    print(f'Report: {args.output}')
    if dirty:
        for finding in dirty:
            print(f'{finding["path"]}: used by {", ".join(finding["packages"])}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f'check-cosmic-cargo-cache: {error}')

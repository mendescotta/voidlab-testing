#!/usr/bin/env python3
"""Run with python3 tests/test-bootstrap.py; exercise every pre-checkout bootstrap offline."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_repository_failures(self):
        count = 0
        for workflow in ('auto-update.yml', 'check.yml', 'overlay-report.yml'):
            text = (ROOT / '.github/workflows' / workflow).read_text()
            for block in text.split('          mkdir -p /etc/xbps.d')[1:]:
                # Stop at the next YAML step. Keep the actual shell, not a copy.
                lines = ['mkdir -p /etc/xbps.d']
                lines[0] += block.splitlines()[0]
                for line in block.splitlines()[1:]:
                    if line and not line.startswith('          '):
                        break
                    lines.append(line[10:])
                script = '\n'.join(lines)
                count += 1
                for failure in ('none', '-Syu xbps', '-yu', '-y git', 'both'):
                    with self.subTest(workflow=workflow, block=count, failure=failure), tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp)
                        (root / 'share').mkdir()
                        (root / 'share/00-repository-main.conf').write_text('repository=https://repo-default.voidlinux.org/current\n')
                        script_local = script.replace('/etc/xbps.d', str(root / 'etc')).replace('/usr/share/xbps.d', str(root / 'share'))
                        stub = '''
sleep() { :; }
xbps-install() {
  repo=$(cat "$TEST_ROOT/etc/00-repository-main.conf")
  printf '%s %s\n' "$repo" "$*" >> "$TEST_ROOT/log"
  [ "$FAILURE" != both ] || return 1
  case "$repo" in *repo-ci*) [ "$*" != "$FAILURE" ] || return 1 ;; esac
}
'''
                        result = subprocess.run(['bash', '-eu', '-c', stub + script_local], env={**os.environ, 'TEST_ROOT': tmp, 'FAILURE': failure}, capture_output=True, text=True, timeout=5)
                        self.assertEqual(result.returncode, 1 if failure == 'both' else 0, result.stderr)
                        log = (root / 'log').read_text()
                        self.assertEqual('repo-default' in log, failure != 'none')
                        if failure not in ('none', 'both'):
                            self.assertIn('repo-default.voidlinux.org/current -y git', log)
        self.assertEqual(count, 4)


if __name__ == '__main__':
    unittest.main()

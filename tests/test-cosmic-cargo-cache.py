#!/usr/bin/env python3
"""Exercise real Git submodules so Cargo metadata cannot hide source changes."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('cache_audit', Path(__file__).resolve().parents[1] / 'tools/check-cosmic-cargo-cache.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CargoSubmoduleChanges(unittest.TestCase):
    def git(self, path, *args):
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        '-c', 'commit.gpgSign=false', '-c', 'core.hooksPath=/dev/null',
                        '-c', 'protocol.file.allow=always', '-C', str(path), *args],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        child = root / 'child-source'
        child.mkdir()
        self.git(child, 'init', '-q')
        (child / 'source.rs').write_text('original\n')
        self.git(child, 'add', 'source.rs')
        self.git(child, 'commit', '-qm', 'initial')
        self.parent = root / 'parent'
        self.parent.mkdir()
        self.git(self.parent, 'init', '-q')
        self.git(self.parent, 'submodule', 'add', '-q', str(child), 'dependency')
        self.git(self.parent, 'commit', '-qm', 'initial')

    def test_cargo_marker_is_ignored(self):
        (self.parent / 'dependency/.cargo-ok').touch()
        self.assertEqual(audit.tracked_changes(self.parent), '')

    def test_modified_dependency_source_is_detected(self):
        (self.parent / 'dependency/source.rs').write_text('modified\n')
        self.assertIn('dependency', audit.tracked_changes(self.parent))

    def test_changed_dependency_revision_is_detected(self):
        child = self.parent / 'dependency'
        (child / 'source.rs').write_text('new revision\n')
        self.git(child, 'commit', '-qam', 'next')
        self.assertIn('dependency', audit.tracked_changes(self.parent))


if __name__ == '__main__':
    unittest.main()

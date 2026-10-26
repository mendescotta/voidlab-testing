#!/usr/bin/env python3
"""A resumed build must never reuse sources after a patch or archive change."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('build_cosmic', Path(__file__).resolve().parents[1] / 'tools/build-cosmic.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class ResumeCompatibility(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.old = Path(temporary.name) / 'old'
        self.new = Path(temporary.name) / 'new'
        for directory in (self.old, self.new):
            (directory / 'patches').mkdir(parents=True)
            (directory / 'template').write_text('version=1.11.0\nchecksum=abc\nconfigure_args="--workspace"\n')
            (directory / 'patches/fix.patch').write_text('original patch\n')

    def test_target_selection_change_can_reuse_compiler_output(self):
        path = self.new / 'template'
        path.write_text(path.read_text().replace('--workspace', '--package cosmic-applets'))
        self.assertTrue(build.compatible_resume(self.old, self.new))

    def test_source_checksum_change_requires_clean_build(self):
        path = self.new / 'template'
        path.write_text(path.read_text().replace('checksum=abc', 'checksum=def'))
        self.assertFalse(build.compatible_resume(self.old, self.new))

    def test_changed_patch_requires_clean_build(self):
        (self.new / 'patches/fix.patch').write_text('new patch\n')
        self.assertFalse(build.compatible_resume(self.old, self.new))

    def test_deleted_patch_requires_clean_build(self):
        (self.new / 'patches/fix.patch').unlink()
        self.assertFalse(build.compatible_resume(self.old, self.new))


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Offline checks for checksum enforcement and strict patch validation."""

import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('cosmic_sources', Path(__file__).resolve().parents[1] / 'tools/cosmic-sources.py')
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


class SourceVerification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.package = self.root / 'cosmic-example'
        self.package.mkdir()
        self.template = self.package / 'template'
        self.archive = self.cache / 'cosmic-example-1.11.0.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as archive:
            data = b'first\nold\nlast\n'
            entry = tarfile.TarInfo('example-epoch-1.11.0/file')
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        checksum = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.template.write_text(f'version=1.11.0\nhomepage="https://github.com/pop-os/example"\nchecksum={checksum}\n')

    def verify(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return sources.verify(self.template, self.cache, None)

    def test_checksum_mismatch_does_not_extract(self):
        self.archive.write_bytes(b'invalid archive')
        with self.assertRaisesRegex(ValueError, 'checksum does not match'):
            self.verify()
        self.assertFalse((self.cache / 'sources').exists())

    def test_patch_is_applied_in_extracted_tree(self):
        patchdir = self.package / 'patches'
        patchdir.mkdir()
        (patchdir / 'fix.patch').write_text('--- a/file\n+++ b/file\n@@ -1,3 +1,3 @@\n first\n-old\n+new\n last\n')
        result = self.verify()
        self.assertEqual((Path(result['source']) / 'file').read_text(), 'first\nnew\nlast\n')
        self.assertEqual(result['patches'], ['fix.patch'])

    def test_offset_patch_is_rejected(self):
        patchdir = self.package / 'patches'
        patchdir.mkdir()
        (patchdir / 'fix.patch').write_text('--- a/file\n+++ b/file\n@@ -5,3 +5,3 @@\n first\n-old\n+new\n last\n')
        with self.assertRaisesRegex(ValueError, 'patch needs refreshing'):
            self.verify()

    def test_independent_package_keeps_its_version(self):
        self.template.write_text(self.template.read_text().replace('pop-os/example', 'cosmic-utils/cosmic-ext-tweaks'))
        with contextlib.redirect_stdout(io.StringIO()):
            result = sources.verify(self.template, self.cache, '1.12.0')
        self.assertEqual(result['version'], '1.11.0')
        self.assertIn('/tags/1.11.0.tar.gz', result['url'])


if __name__ == '__main__':
    unittest.main()

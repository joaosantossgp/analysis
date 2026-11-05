import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.governance import update_agent_skills as updater


class SkillUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = b'---\nname: example\ndescription: Example\n---\nOld\n'
        self.new = self.old.replace(b'Old', b'New')
        (self.root / 'example').mkdir()
        (self.root / 'example/SKILL.md').write_bytes(self.old)
        self.manifest = {'skills': [{'name': 'example', 'repository': 'owner/repo',
            'commit': 'a' * 40, 'source_path': 'skills/example',
            'sha256': {'SKILL.md': hashlib.sha256(self.old).hexdigest()}}]}
        (self.root / 'installation-manifest.json').write_text(json.dumps(self.manifest))

    def test_verify_rejects_local_changes(self):
        (self.root / 'example/SKILL.md').write_bytes(b'local edit')
        with self.assertRaises(ValueError):
            updater.verify(self.root, self.manifest)

    def test_update_verifies_download_and_updates_manifest(self):
        with patch.object(updater, 'fetch_upstream', return_value=('b' * 40, {'SKILL.md': self.new})):
            updater.update(self.root)
        self.assertEqual((self.root / 'example/SKILL.md').read_bytes(), self.new)
        manifest = json.loads((self.root / 'installation-manifest.json').read_text())
        self.assertEqual(manifest['skills'][0]['commit'], 'b' * 40)
        updater.verify(self.root, manifest)

    def test_network_failure_leaves_installation_unchanged(self):
        before = (self.root / 'installation-manifest.json').read_bytes()
        with patch.object(updater, 'fetch_upstream', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                updater.update(self.root)
        self.assertEqual((self.root / 'example/SKILL.md').read_bytes(), self.old)
        self.assertEqual((self.root / 'installation-manifest.json').read_bytes(), before)

    def test_unsafe_download_path_leaves_installation_unchanged(self):
        with patch.object(updater, 'fetch_upstream', return_value=('b' * 40, {'../escape': b'bad'})):
            with self.assertRaises(ValueError):
                updater.update(self.root)
        self.assertEqual((self.root / 'example/SKILL.md').read_bytes(), self.old)

    def test_unchanged_update_is_noop(self):
        before = (self.root / 'installation-manifest.json').read_bytes()
        with patch.object(updater, 'fetch_upstream', return_value=('a' * 40, {'SKILL.md': self.old})):
            updater.update(self.root)
        self.assertEqual((self.root / 'installation-manifest.json').read_bytes(), before)

    def test_directory_to_file_conflict_preserves_all_packages(self):
        second = dict(self.manifest['skills'][0], name='other')
        folder = self.root / 'other'
        (folder / 'references').mkdir(parents=True)
        (folder / 'SKILL.md').write_bytes(self.old)
        (folder / 'references/a.md').write_bytes(b'reference')
        second['sha256'] = {
            'SKILL.md': hashlib.sha256(self.old).hexdigest(),
            'references/a.md': hashlib.sha256(b'reference').hexdigest(),
        }
        self.manifest['skills'].append(second)
        (self.root / 'installation-manifest.json').write_text(json.dumps(self.manifest))
        before = {p.relative_to(self.root): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        replies = [
            ('b' * 40, {'SKILL.md': self.new}),
            ('b' * 40, {'SKILL.md': self.old.replace(b'example', b'other'),
                        'references': b'flat reference'}),
        ]
        with patch.object(updater, 'fetch_upstream', side_effect=replies):
            with self.assertRaisesRegex(ValueError, 'directory'):
                updater.update(self.root)
        after = {p.relative_to(self.root): p.read_bytes()
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        updater.verify(self.root, self.manifest)

    def test_corrupt_upstream_blob_is_rejected(self):
        tree = {'tree': [{'path': 'skills/example/SKILL.md', 'type': 'blob',
                         'mode': '100644', 'sha': '0' * 40}]}
        replies = [json.dumps({'sha': 'b' * 40}).encode(), json.dumps(tree).encode(), self.new]
        with patch.object(updater, 'download', side_effect=replies):
            with self.assertRaisesRegex(ValueError, 'blob mismatch'):
                updater.fetch_upstream(self.manifest['skills'][0])

    def test_extra_local_file_is_rejected(self):
        (self.root / 'example/unexpected.md').write_text('local')
        with self.assertRaises(ValueError):
            updater.verify(self.root, self.manifest)

    def test_failed_second_package_does_not_install_first(self):
        second = dict(self.manifest['skills'][0], name='other')
        (self.root / 'other').mkdir()
        (self.root / 'other/SKILL.md').write_bytes(self.old)
        self.manifest['skills'].append(second)
        (self.root / 'installation-manifest.json').write_text(json.dumps(self.manifest))
        with patch.object(updater, 'fetch_upstream', side_effect=[('b' * 40, {'SKILL.md': self.new}), OSError('offline')]):
            with self.assertRaises(OSError):
                updater.update(self.root)
        self.assertEqual((self.root / 'example/SKILL.md').read_bytes(), self.old)


if __name__ == '__main__':
    unittest.main()

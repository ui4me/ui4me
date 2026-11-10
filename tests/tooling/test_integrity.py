import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.ui4me_dev.common import DevError, safe_extract, sha256, source_id, write_json, zip_tree
from tools.ui4me_dev.evidence import observation_rows
from tools.ui4me_dev.publishing import qualified_evidence_files


class SourceIdentityTests(unittest.TestCase):
    def test_line_endings_do_not_change_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'code.py'
            file.write_bytes(b'a\r\nb\r\n')
            first = source_id(root)
            file.write_bytes(b'a\nb\n')
            self.assertEqual(first, source_id(root))

    def test_content_change_changes_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'file.md').write_text('before')
            first = source_id(root)
            (root / 'file.md').write_text('after')
            self.assertNotEqual(first, source_id(root))

    def test_generated_files_do_not_change_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.rs').write_text('fn main() {}')
            first = source_id(root)
            (root / 'build').mkdir()
            (root / 'build/log.txt').write_text('generated')
            self.assertEqual(first, source_id(root))

    def test_renaming_changes_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'a.rs'
            file.write_text('same')
            first = source_id(root)
            file.rename(root / 'b.rs')
            self.assertNotEqual(first, source_id(root))


class ArchiveTests(unittest.TestCase):
    def test_packaging_pre_zip_epoch_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            file = source / 'license.txt'
            file.write_text('license')
            os.utime(file, (1, 1))
            archive = root / 'package.zip'
            zip_tree(source, archive)
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.read('license.txt'), b'license')

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('../outside.txt', 'bad')
            with self.assertRaises(DevError):
                safe_extract(archive, root / 'output')
            self.assertFalse((root / 'outside.txt').exists())

    def test_windows_absolute_path_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('C:/outside.txt', 'bad')
            with self.assertRaises(DevError):
                safe_extract(archive, root / 'output')

    def test_valid_archive_extracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'good.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('Ui4me/file.txt', 'ok')
            safe_extract(archive, root / 'output')
            self.assertEqual((root / 'output/Ui4me/file.txt').read_text(), 'ok')


class PublishedEvidenceTests(unittest.TestCase):
    def test_only_reviewed_proof_is_selected_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'build/reports/run'
            run.mkdir(parents=True)
            proof = run / 'proof.log'
            proof.write_text('proof')
            (run / 'unrelated.log').write_text('not selected')
            receipt = run / 'run.json'
            write_json(receipt, {'proof_files': [{'path': 'proof.log', 'sha256': sha256(proof)}], 'cases': []})
            qualification = {'evidence': [{'path': 'build/reports/run/run.json', 'sha256': sha256(receipt)}]}
            self.assertEqual({path.name for path in qualified_evidence_files(qualification, root)}, {'run.json', 'proof.log'})
            proof.write_text('tampered')
            with self.assertRaises(DevError):
                qualified_evidence_files(qualification, root)


class LatestEvidenceTests(unittest.TestCase):
    def records(self):
        base = {'schema': 1, 'kind': 'test', 'platform': 'linux-x64', 'binding': 'python', 'suite': 'installed', 'source_id': 'source', 'manifest_sha256': 'manifest'}
        first = dict(base, status='passed', cases=[{'id': 'F01', 'status': 'passed'}])
        second = dict(base, status='failed', cases=[{'id': 'F01', 'status': 'failed'}])
        return [(Path('first/run.json'), first), (Path('second/run.json'), second)]

    @patch('tools.ui4me_dev.evidence.catalog', return_value=[{'id':'F01','suite':'installed','title':'install'}])
    def test_latest_failure_overrides_old_pass(self, _):
        rows = observation_rows(self.records(), 'source', 'manifest')
        row = next(x for x in rows if x['platform'] == 'linux-x64' and x['binding'] == 'python')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['last_success'][0], Path('first/run.json'))

    @patch('tools.ui4me_dev.evidence.catalog', return_value=[{'id':'F01','suite':'installed','title':'install'}])
    def test_other_source_is_not_coverage(self, _):
        self.assertTrue(all(x['status'] == 'not_run' for x in observation_rows(self.records(), 'different')))

    @patch('tools.ui4me_dev.evidence.catalog', return_value=[{'id':'F01','suite':'installed','title':'install'}])
    def test_other_artifact_is_not_coverage(self, _):
        self.assertTrue(all(x['status'] == 'not_run' for x in observation_rows(self.records(), 'source', 'other-manifest')))

    @patch('tools.ui4me_dev.evidence.catalog', return_value=[{'id':'F01','suite':'installed','title':'install'}])
    def test_unfinished_attempt_blocks_old_success(self, _):
        values = self.records()
        values[-1][1]['status'] = 'running'
        values[-1][1]['cases'] = []
        row = next(x for x in observation_rows(values, 'source') if x['platform'] == 'linux-x64' and x['binding'] == 'python')
        self.assertEqual(row['status'], 'interrupted')

    @patch('tools.ui4me_dev.evidence.catalog', return_value=[{'id':'F01','suite':'installed','title':'install'}])
    def test_duplicate_scenario_rejected(self, _):
        values = self.records()
        values[0][1]['cases'] *= 2
        with self.assertRaises(DevError):
            observation_rows(values, 'source')

    @patch('tools.ui4me_dev.evidence.catalog', return_value=[{'id':'F01','suite':'installed','title':'install'}])
    def test_failed_run_cannot_confer_a_pass(self, _):
        values = self.records()
        values[-1][1]['cases'][0]['status'] = 'passed'
        row = next(x for x in observation_rows(values, 'source') if x['platform'] == 'linux-x64' and x['binding'] == 'python')
        self.assertEqual(row['status'], 'failed')

    @patch('tools.ui4me_dev.evidence.catalog', return_value=[{'id':'F01','suite':'installed','title':'install'}])
    def test_unit_suite_cannot_qualify_an_acceptance_scenario(self, _):
        values = self.records()[:1]
        values[0][1]['suite'] = 'unit'
        row = next(x for x in observation_rows(values, 'source') if x['platform'] == 'linux-x64' and x['binding'] == 'python')
        self.assertEqual(row['status'], 'not_run')


if __name__ == '__main__':
    unittest.main()

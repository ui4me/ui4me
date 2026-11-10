import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.ui4me_dev.reporting import matrix
from tools.ui4me_dev import evidence


class EvidenceControls(unittest.TestCase):
    def entry(self, status, case_status="passed", manifest="candidate"):
        return (Path("run.json"), {"kind": "test", "platform": "linux-x64", "binding": "python", "status": status, "suite": "installed", "manifest_sha256": manifest, "cases": [{"id": "F01", "status": case_status}]})

    def test_missing_results_are_not_passed(self):
        self.assertEqual(matrix([])[("linux-x64", "python", "F01")], [])

    def test_failed_run_cannot_confer_a_pass(self):
        self.assertEqual(matrix([self.entry("failed")])[("linux-x64", "python", "F01")][0][0], "failed")

    def test_only_exact_manifest_counts(self):
        self.assertFalse(matrix([self.entry("passed")], manifest_hash="different")[("linux-x64", "python", "F01")])

    def test_unit_suite_cannot_qualify_an_acceptance_scenario(self):
        entry = self.entry("passed")
        entry[1]["suite"] = "unit"
        self.assertFalse(matrix([entry])[("linux-x64", "python", "F01")])

    def test_latest_failure_is_retained_after_success(self):
        history = matrix([self.entry("passed"), self.entry("failed", "failed")])[("linux-x64", "python", "F01")]
        self.assertEqual([item[0] for item in history], ["passed", "failed"])

    def test_report_labels_renderer_snapshot_as_not_desktop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run" / "run.json"
            receipt = {"renderer_snapshot": {"path": "renderer.png", "native_capture": False}}
            case = {"id": "F02", "status": "not_run"}
            row = {"latest": (run, receipt, case), "last_success": None,
                   "platform": "linux-x64", "binding": "python", "status": "not_run",
                   "scenario": {"id": "F02", "title": "Native startup", "acceptance": "Visible window"}}
            with patch.object(evidence, "output_path", side_effect=lambda p: p), \
                 patch.object(evidence, "source_id", return_value="test"), \
                 patch.object(evidence, "receipts", return_value=[]), \
                 patch.object(evidence, "observation_rows", return_value=[row]):
                evidence.report(root / "overview")
            for name in ("overview.md", "index.html"):
                self.assertIn("renderer snapshot (not desktop)", (root / "overview" / name).read_text())


if __name__ == "__main__":
    unittest.main()

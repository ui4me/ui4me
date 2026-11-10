import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.ui4me_dev import evidence


class EvidenceControls(unittest.TestCase):
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

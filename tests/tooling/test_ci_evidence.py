"""CI must not manufacture success from absent, stale or incomplete reports."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from tools.ui4me_dev.common import sha256, write_json

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_ci_evidence", ROOT / ".github/scripts/check-ci-evidence.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class CiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = {"source_id": "source", "git_revision": "revision", "artifacts": []}
        for platform in ci.PLATFORMS:
            for kind in ("native-sdk", "python-wheel"):
                self.manifest["artifacts"].append({"kind": kind, "platform": platform, "path": kind + "-" + platform})
        self.manifest["artifacts"].append({"kind": "powershell-package", "path": "Ui4me.nupkg"})
        self.values = []
        for platform in ci.PLATFORMS:
            for binding in ("core", "python", "powershell", "tools"):
                self.add_receipt(platform, binding, "unit")
            for binding in ("core", "python", "powershell"):
                for python in ci.PYTHONS if binding == "python" else ("3.12",):
                    self.add_receipt(platform, binding, "installed", python)

    def add_receipt(self, platform, binding, suite, python="3.12"):
        folder = self.root / str(len(self.values))
        folder.mkdir()
        proof = folder / "suite.log"
        proof.write_text("suite completed", encoding="utf-8")
        data = {"source_id": "source", "git_revision": "revision", "phase": "candidate", "platform": platform,
                "binding": binding, "suite": suite, "status": "passed", "harness": {"python": python + ".1"},
                "proof_files": [{"path": proof.name, "sha256": sha256(proof)}]}
        if suite == "unit":
            data.update(test_count=1, cases=[{"id": "unit", "status": "passed"}])
        else:
            cases = {"C01"} if binding == "core" else ci.INSTALLED
            kind = {"core": "native-sdk", "python": "python-wheel", "powershell": "powershell-package"}[binding]
            artifact = ci.find_artifact(self.manifest, kind, None if binding == "powershell" else platform)
            data.update(manifest_sha256="manifest", consumed_artifact=dict(artifact),
                        cases=[{"id": key, "status": "passed"} for key in sorted(cases)],
                        installation_checks={"missing_payload_rejected": True, "exact_candidate_reinstalled": True})
            consumer = folder / "consumer.json"
            write_json(consumer, {"cases": data["cases"]})
            data["consumer_sha256"] = sha256(consumer)
        self.values.append((folder / "run.json", data))

    def errors(self):
        return ci.check_receipts(self.values, self.manifest, "manifest")

    def test_complete_headless_matrix_passes_without_native_claim(self):
        self.assertEqual(self.errors(), [])
        self.assertTrue(all(data["suite"] != "native" for _, data in self.values))

    def test_missing_interpreter_consumer_fails(self):
        self.values = [(p, d) for p, d in self.values if not (d["binding"] == "python" and d["suite"] == "installed" and d["harness"]["python"].startswith("3.11."))]
        self.assertTrue(any("Missing installed consumer: win-x64/python/Python 3.11" in error for error in self.errors()))

    def test_stale_source_cannot_fill_required_suite(self):
        self.values[0][1]["source_id"] = "old source"
        self.assertTrue(any("Missing unit suite: linux-x64/core" in error for error in self.errors()))

    def test_zero_tests_are_not_a_pass(self):
        self.values[0][1]["test_count"] = 0
        self.assertTrue(any("Required unit suite did not pass" in error for error in self.errors()))

    def test_latest_failure_cannot_hide_behind_old_success(self):
        self.add_receipt("linux-x64", "python", "installed", "3.12")
        self.values[-1][1]["status"] = "failed"
        self.assertTrue(any("Required installed consumer did not pass: linux-x64/python/Python 3.12" in error for error in self.errors()))

    def test_different_candidate_and_missing_case_rejected(self):
        data = next(d for _, d in self.values if d["binding"] == "powershell" and d["suite"] == "installed")
        data["manifest_sha256"] = "different manifest"
        data["cases"].pop()
        errors = self.errors()
        self.assertTrue(any("used different artifacts" in error for error in errors))
        self.assertTrue(any("Required installed consumer did not pass" in error for error in errors))

    def test_changed_proof_fails(self):
        path, _ = self.values[0]
        (path.parent / "suite.log").write_text("replaced", encoding="utf-8")
        self.assertTrue(any("Missing or changed proof" in error for error in self.errors()))

    def test_loader_and_reinstall_checks_are_required(self):
        data = next(d for _, d in self.values if d["binding"] == "python" and d["suite"] == "installed")
        data["installation_checks"] = {}
        self.assertTrue(any("Missing negative-loader or exact-reinstall" in error for error in self.errors()))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from tools.gate import verdict
from tools.ui4me_dev.common import ROOT, read_json
from tools.ui4me_dev.testing import INSTALLED, NATIVE


def passing(results: Path, platform: str) -> None:
    steps = verdict.LINUX if platform == "linux" else verdict.WINDOWS
    lines = []
    for step, files in steps.items():
        if step not in verdict.NO_EXIT_RECORD.get(platform, set()):
            lines.append(f"{step} exit 0")
        for rel in files:
            path = results / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if rel.endswith(".log"):
                path.write_text("ok x\n\n3 passed, 0 failed\n", encoding="utf-8")
            else:
                path.write_text(json.dumps({"status": "passed", "cases": [{"id": "A", "status": "passed"}]}), encoding="utf-8")
    (results / "summary.txt").write_text("\n".join(lines + ["done"]) + "\n", encoding="utf-8")


class GateVerdictTests(unittest.TestCase):
    def check(self, platform, damage=None):
        with tempfile.TemporaryDirectory() as temporary:
            results = Path(temporary)
            passing(results, platform)
            if damage:
                damage(results)
            code = verdict.main([str(results), "--platform", platform])
            return code, read_json(results / "verdict.json")

    def test_complete_results_pass(self):
        for platform in ("linux", "windows"):
            self.assertEqual(self.check(platform)[0], 0)

    def test_missing_result_fails(self):
        code, data = self.check("linux", lambda r: (r / "lua/lua.json").unlink())
        self.assertEqual(code, 1)
        self.assertIn("result missing", json.dumps(data))

    def test_skipped_or_blocked_case_fails(self):
        def blocked(r):
            (r / "print/print.json").write_text(json.dumps({"status": "passed", "cases": [{"id": "P1", "status": "blocked"}]}))
        self.assertEqual(self.check("windows", blocked)[0], 1)

    def test_step_that_did_not_run_fails(self):
        def drop(r):
            text = (r / "summary.txt").read_text().replace("nvda exit 0\n", "")
            (r / "summary.txt").write_text(text)
        self.assertEqual(self.check("windows", drop)[0], 1)

    def test_nonzero_exit_fails_even_with_passing_json(self):
        def fail_exit(r):
            text = (r / "summary.txt").read_text().replace("orca exit 0", "orca exit 1")
            (r / "summary.txt").write_text(text)
        self.assertEqual(self.check("linux", fail_exit)[0], 1)

    def test_unfinished_runner_and_empty_cases_fail(self):
        self.assertEqual(self.check("linux", lambda r: (r / "summary.txt").write_text("chat-python exit 0\n"))[0], 1)
        self.assertEqual(self.check("linux", lambda r: (r / "a11y/a11y.json").write_text('{"status": "passed", "cases": []}'))[0], 1)

    def test_lua_unit_failures_fail(self):
        self.assertEqual(self.check("windows", lambda r: (r / "lua/command.log").write_text("18 passed, 1 failed\n"))[0], 1)


class ScenarioCatalogueTests(unittest.TestCase):
    def test_catalogue_matches_the_installed_and_native_cases(self):
        scenarios = read_json(ROOT / "quality/scenarios.json")["scenarios"]
        self.assertEqual({s["id"] for s in scenarios if s["suite"] == "installed"}, INSTALLED)
        self.assertEqual({s["id"] for s in scenarios if s["suite"] == "native"}, NATIVE)
        self.assertEqual(len(scenarios), len(INSTALLED) + len(NATIVE))
        self.assertTrue(all(s["title"] and s["acceptance"] for s in scenarios))


if __name__ == "__main__":
    unittest.main()

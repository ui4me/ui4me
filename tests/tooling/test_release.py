"""Offline release-control regressions; fixtures are never release evidence."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import patch

from tools.ui4me_dev import common, evidence, publishing
from tools.ui4me_dev.common import DevError, sha256, source_id, write_json


SCRIPT = common.ROOT / ".github/scripts/trusted-run.py"
SPEC = importlib.util.spec_from_file_location("trusted_run", SCRIPT)
trusted_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trusted_run)


class SourceIsolationTests(unittest.TestCase):
    def test_pypa_generated_action_changes_identity_but_fresh_checkout_verifies(self):
        # The pinned publisher creates this exact path in its checkout. Keep it
        # visible to source identity; a fresh verifier receives only dist/build.
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            publisher = work / "publisher"
            verifier = work / "verifier"
            for root in (publisher, verifier):
                root.mkdir()
                (root / "VERSION").write_text("0.1.0\n")
                (root / "source.py").write_text("print('same committed source')\n")
            candidate = publisher / "dist/release"
            candidate.mkdir(parents=True)
            wheel = candidate / "fixture.whl"
            wheel.write_bytes(b"offline test fixture, not an installable release")
            manifest = {
                "schema": 1, "product": "ui4me", "version": "0.1.0",
                "source_id": source_id(publisher),
                "artifacts": [{"kind": "python-wheel", "path": wheel.name,
                               "sha256": sha256(wheel), "size": wheel.stat().st_size}],
            }
            write_json(candidate / "manifest.json", manifest)
            with patch.object(common, "source_id", side_effect=lambda: source_id(publisher)), \
                 patch.object(common, "version", return_value="0.1.0"):
                common.load_manifest(candidate / "manifest.json")
                generated = publisher / ".github/.tmp/.generated-actions/run-pypi-publish-in-docker-container/action.yml"
                generated.parent.mkdir(parents=True)
                generated.write_text("runs: {using: docker, image: fixture}\n")
                with self.assertRaisesRegex(DevError, "Manifest source differs"):
                    common.load_manifest(candidate / "manifest.json")
            shutil.copytree(candidate, verifier / "dist/release")
            with patch.object(common, "source_id", side_effect=lambda: source_id(verifier)), \
                 patch.object(common, "version", return_value="0.1.0"):
                self.assertEqual(common.load_manifest(verifier / "dist/release/manifest.json"), manifest)
            self.assertFalse((verifier / ".github/.tmp").exists())


class QualificationPortabilityTests(unittest.TestCase):
    def test_ci_only_keeps_native_acceptance_distinct(self):
        manifest = {"source_id": "fixture-source", "git_revision": "fixture-revision",
                    "platform": "combined", "profile": "release", "artifacts": []}
        with patch.object(evidence, "load_manifest", return_value=manifest), \
             patch.object(evidence, "require_locks"), \
             patch.object(evidence, "revision", return_value="fixture-revision"), \
             patch.object(evidence, "receipts", return_value=[]), \
             patch.object(evidence, "sha256", return_value="fixture-hash"), \
             patch.object(evidence.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")):
            result = evidence.qualify(common.ROOT / "dist/release/manifest.json", "ci",
                                      "https://github.com/ui4me/ui4me/actions/runs/1", save=False, ci_only=True)
        self.assertEqual(result["status"], "qualified")
        self.assertEqual(result["native_desktop_acceptance"], "not_run")

    def test_ci_only_blocks_failed_matrix(self):
        manifest = {"source_id": "fixture-source", "git_revision": "fixture-revision",
                    "platform": "combined", "profile": "release", "artifacts": []}
        def command(args, **kwargs):
            return SimpleNamespace(returncode=1 if str(args[-1]).endswith("check-ci-evidence.py") else 0,
                                   stdout="", stderr="matrix failed")
        with patch.object(evidence, "load_manifest", return_value=manifest), \
             patch.object(evidence, "require_locks"), \
             patch.object(evidence, "revision", return_value="fixture-revision"), \
             patch.object(evidence, "receipts", return_value=[]), \
             patch.object(evidence, "sha256", return_value="fixture-hash"), \
             patch.object(evidence.subprocess, "run", side_effect=command):
            result = evidence.qualify(common.ROOT / "dist/release/manifest.json", "ci",
                                      "https://github.com/ui4me/ui4me/actions/runs/1", save=False, ci_only=True)
        self.assertEqual(result["status"], "blocked")

    def test_saved_references_are_identical_on_linux_and_windows(self):
        # Exercise all three qualification reference paths: acceptance, unit
        # and installed C SDK. Incomplete fixtures stay blocked and are not
        # written; this checks serialization, not genuine native acceptance.
        wheel = {"kind": "python-wheel", "platform": "linux-x64", "path": "fixture.whl"}
        sdk = {"kind": "native-sdk", "platform": "linux-x64", "path": "fixture.zip"}
        manifest = {"source_id": "fixture-source", "git_revision": "fixture-revision",
                    "platform": "combined", "profile": "release", "artifacts": [wheel, sdk]}
        base = {"source_id": "fixture-source", "platform": "linux-x64", "status": "passed"}
        unit = dict(base, binding="tools", suite="unit", test_count=1,
                    cases=[{"id": "fixture", "status": "passed"}], proof_files=[])
        installed = dict(base, binding="core", suite="installed", manifest_sha256="fixture-hash",
                         consumed_artifact=sdk, cases=[{"id": "C01", "status": "passed"}], proof_files=[])
        acceptance = dict(base, consumed_artifact=wheel)
        results = []
        for root in (PurePosixPath("/checkout"), PureWindowsPath("C:/checkout")):
            paths = {name: root / "build/reports" / name / "run.json"
                     for name in ("acceptance", "unit", "sdk")}
            row = {"platform": "linux-x64", "binding": "python", "scenario": {"id": "F01"},
                   "status": "passed", "latest": (paths["acceptance"], acceptance, {"id": "F01"})}
            with self.subTest(platform=type(root).__name__), \
                 patch.object(evidence, "ROOT", root), \
                 patch.object(evidence, "load_manifest", return_value=manifest), \
                 patch.object(evidence, "require_locks"), \
                 patch.object(evidence, "revision", return_value="fixture-revision"), \
                 patch.object(evidence.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="")), \
                 patch.object(evidence, "receipts", return_value=[(paths["unit"], unit), (paths["sdk"], installed)]), \
                 patch.object(evidence, "observation_rows", return_value=[row]), \
                 patch.object(evidence, "evidence_errors", return_value=[]), \
                 patch.object(evidence, "sha256", return_value="fixture-hash"):
                result = evidence.qualify(Path("fixture-manifest.json"), "offline-test",
                                          "https://github.com/ui4me/ui4me", save=False)
                self.assertEqual(result["status"], "blocked")
                results.append(result["evidence"])
        expected = [{"path": f"build/reports/{name}/run.json", "sha256": "fixture-hash"}
                    for name in ("acceptance", "sdk", "unit")]
        self.assertEqual(results[0], expected)
        self.assertEqual(results[1], expected)


class PublicationControlsTests(unittest.TestCase):
    def test_gallery_lookup_uses_an_exact_version_path(self):
        self.assertEqual(publishing.gallery_package_url("0.2.0"),
                         "https://cdn.powershellgallery.com/packages/ui4me.0.2.0.nupkg")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.folder = self.root / "dist/release"
        self.folder.mkdir(parents=True)
        self.manifest_path = self.folder / "manifest.json"
        self.wheels = []
        artifacts = []
        for platform in ("linux-x64", "win-x64"):
            path = self.folder / (platform + ".whl")
            path.write_bytes(("test bytes " + platform).encode())
            self.wheels.append(path)
            artifacts.append({"kind": "python-wheel", "path": path.name,
                              "platform": platform, "sha256": sha256(path),
                              "size": path.stat().st_size})
        self.manifest = {"schema": 1, "product": "ui4me", "version": "0.1.0",
                         "source_id": "fixture", "artifacts": artifacts}
        write_json(self.manifest_path, self.manifest)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(publishing, "ROOT", self.root))
        self.stack.enter_context(patch.object(publishing, "load_manifest", return_value=self.manifest))
        self.stdout = self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def index(self, wheels):
        records = [{"filename": path.name, "url": "https://files.pythonhosted.org/" + path.name}
                   for path in wheels]
        return io.StringIO(json.dumps({"urls": records}))

    def download_identical(self, url, destination):
        shutil.copyfile(self.folder / url.rsplit("/", 1)[-1], destination)

    def test_review_only_does_not_call_network_or_execute_an_upload(self):
        for registry in ("pypi", "testpypi"):
            with self.subTest(registry=registry), \
                 patch.object(publishing, "require_qualified", return_value={}) as qualification, \
                 patch.object(publishing, "run") as execute, \
                 patch.object(publishing.urllib.request, "urlopen") as network:
                publishing.publish(self.manifest_path, registry, execute=False)
                qualification.assert_called_once_with(self.manifest_path)
                execute.assert_not_called()
                network.assert_not_called()
        self.assertNotIn("--execute", self.stdout.getvalue())

    def test_missing_qualification_blocks_even_review_only(self):
        with patch.object(publishing, "run") as execute, \
             patch.object(publishing.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(DevError, "No qualification record"):
                publishing.publish(self.manifest_path, "pypi", execute=False)
            execute.assert_not_called()
            network.assert_not_called()

    def test_new_version_plans_only_the_qualified_wheels(self):
        not_found = urllib.error.HTTPError("https://pypi.org", 404, "absent", {}, None)
        with patch.object(publishing, "require_qualified", return_value={}), \
             patch.object(publishing.urllib.request, "urlopen", side_effect=not_found), \
             patch.object(publishing, "download") as download:
            self.assertEqual(publishing.python_upload_plan(self.manifest_path, "pypi", self.root / "existing"), self.wheels)
            download.assert_not_called()

    def test_index_errors_do_not_get_treated_as_a_new_version(self):
        for code in (401, 403, 429, 500):
            error = urllib.error.HTTPError("https://pypi.org", code, "failed", {}, None)
            with self.subTest(code=code), \
                 patch.object(publishing, "require_qualified", return_value={}), \
                 patch.object(publishing.urllib.request, "urlopen", side_effect=error):
                with self.assertRaises(urllib.error.HTTPError):
                    publishing.python_upload_plan(self.manifest_path, "pypi", self.root / "existing")

    def test_identical_existing_wheels_are_downloaded_and_no_upload_occurs(self):
        with patch.object(publishing, "require_qualified", return_value={}), \
             patch.object(publishing.urllib.request, "urlopen", return_value=self.index(self.wheels)), \
             patch.object(publishing, "download", side_effect=self.download_identical) as download, \
             patch.object(publishing, "run") as execute:
            publishing.publish(self.manifest_path, "pypi", execute=True)
            self.assertEqual(download.call_count, 2)
            execute.assert_not_called()
        receipt = common.read_json(self.root / "build/publish/pypi/publish.json")
        self.assertEqual(receipt["status"], "already_published_identical")

    def test_partial_publication_resumes_only_missing_wheels(self):
        with patch.object(publishing, "require_qualified", return_value={}), \
             patch.object(publishing.urllib.request, "urlopen", return_value=self.index(self.wheels[:1])), \
             patch.object(publishing, "download", side_effect=self.download_identical):
            self.assertEqual(publishing.python_upload_plan(self.manifest_path, "testpypi", self.root / "existing"), self.wheels[1:])

    def test_existing_version_with_changed_bytes_refuses_upload(self):
        with patch.object(publishing, "require_qualified", return_value={}), \
             patch.object(publishing.urllib.request, "urlopen", return_value=self.index(self.wheels)), \
             patch.object(publishing, "download", side_effect=lambda url, path: path.write_bytes(b"different")), \
             patch.object(publishing, "run") as execute:
            with self.assertRaisesRegex(DevError, "already contains different bytes"):
                publishing.publish(self.manifest_path, "pypi", execute=True)
            execute.assert_not_called()

    def test_duplicate_registry_filename_is_rejected(self):
        with patch.object(publishing, "require_qualified", return_value={}), \
             patch.object(publishing.urllib.request, "urlopen", return_value=self.index(self.wheels * 2)):
            with self.assertRaisesRegex(DevError, "Ambiguous published wheel filename"):
                publishing.python_upload_plan(self.manifest_path, "pypi", self.root / "existing")

    def test_qualification_is_rechecked_before_planning_any_upload(self):
        with patch.object(publishing, "require_qualified", side_effect=DevError("stale evidence")), \
             patch.object(publishing.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(DevError, "stale evidence"):
                publishing.python_upload_plan(self.manifest_path, "pypi", self.root / "existing")
            network.assert_not_called()


class ArtifactOriginTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "output.txt"
        self.run = {"repository": {"full_name": "ui4me/ui4me"},
                    "head_repository": {"full_name": "ui4me/ui4me"},
                    "head_branch": "main", "head_sha": "a" * 40,
                    "path": ".github/workflows/ci.yml", "event": "push",
                    "status": "completed", "conclusion": "success"}
        self.artifacts = [{"name": "ci-bundle", "id": 42, "expired": False}]

    def invoke(self, run_id="123"):
        def response(request, **kwargs):
            if "/artifacts?" in request.full_url:
                value = {"artifacts": self.artifacts}
            elif "/actions/runs/" in request.full_url:
                value = self.run
            else:
                value = {"default_branch": "main"}
            return io.StringIO(json.dumps(value))

        env = {"GITHUB_REPOSITORY": "ui4me/ui4me", "GITHUB_SHA": "a" * 40,
               "GH_TOKEN": "offline-fixture-token", "GITHUB_OUTPUT": str(self.output)}
        argv = [str(SCRIPT), "--run-id", run_id, "--workflow", "ci.yml", "--artifact", "ci-bundle"]
        with patch.dict(os.environ, env), patch("sys.argv", argv), \
             patch.object(trusted_run.urllib.request, "urlopen", side_effect=response), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            trusted_run.main()
            self.assertNotIn(env["GH_TOKEN"], output.getvalue())

    def test_exact_successful_default_branch_producer_is_accepted(self):
        self.invoke()
        self.assertEqual(self.output.read_text(), "artifact_id=42\n")

    def test_wrong_source_fork_event_workflow_or_result_is_rejected(self):
        values = {
            "head_repository": {"full_name": "someone/fork"},
            "repository": {"full_name": "someone/fork"},
            "head_branch": "feature", "head_sha": "b" * 40,
            "path": ".github/workflows/other.yml", "event": "pull_request",
            "status": "in_progress", "conclusion": "failure",
        }
        for key, value in values.items():
            with self.subTest(key=key), patch.dict(self.run, {key: value}):
                with self.assertRaisesRegex(SystemExit, "Artifact producer refused"):
                    self.invoke()
                self.assertFalse(self.output.exists())

    def test_missing_expired_or_duplicate_artifact_is_rejected(self):
        for values in ([], [dict(self.artifacts[0], expired=True)], self.artifacts * 2):
            with self.subTest(artifacts=values):
                self.artifacts = values
                with self.assertRaisesRegex(SystemExit, "exactly one nonexpired artifact"):
                    self.invoke()
                self.assertFalse(self.output.exists())

    def test_non_numeric_run_id_is_rejected(self):
        for value in ("0", "-1", "123/../456", "1; echo bad"):
            with self.subTest(value=value), self.assertRaisesRegex(SystemExit, "positive decimal integer"):
                self.invoke(run_id=value)


if __name__ == "__main__":
    unittest.main()

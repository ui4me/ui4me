"""Package the exact bridge/native pair recorded by the build, including deps."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.ui4me_dev import packages
from tools.ui4me_dev.common import DevError, sha256, write_json


class BuildOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(packages, "ROOT", self.root).start()
        patch.object(packages, "host", return_value="linux-x64").start()
        patch.object(packages, "native_name", return_value="libui4me_core.so").start()
        patch.object(packages, "source_id", return_value="source").start()
        self.folder = self.root / "build/linux-x64/dev"
        self.native = packages.native_output("dev")
        self.managed = self.folder / "managed/Ui4me.Managed.dll"
        self.deps = self.folder / "managed/Ui4me.Managed.deps.json"
        for path in (self.native, self.managed, self.deps):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())
        write_json(self.folder / "build.json", {
            "status": "passed", "source_id": "source", "binding": "all",
            "native_sha256": sha256(self.native),
            "outputs": [packages.output_identity(path, "test") for path in (self.native, self.managed, self.deps)],
        })

    def test_complete_output_set_is_accepted(self):
        self.assertEqual(packages.checked_build("dev", "powershell"), self.folder)

    def test_modified_managed_bridge_invalidates_receipt(self):
        self.managed.write_bytes(b"different bridge")
        with self.assertRaisesRegex(DevError, "Build output changed"):
            packages.checked_build("dev", "powershell")

    def test_removed_dependency_file_invalidates_receipt(self):
        self.deps.unlink()
        with self.assertRaisesRegex(DevError, "every delivered output"):
            packages.checked_build("dev", "powershell")

    def test_new_unrecorded_dependency_file_invalidates_receipt(self):
        (self.deps.parent / "unexpected.deps.json").write_text("{}")
        with self.assertRaisesRegex(DevError, "every delivered output"):
            packages.checked_build("dev", "powershell")

    def test_target_directory_override_cannot_select_old_root_payload(self):
        old = self.root / "target/debug/libui4me_core.so"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"stale")
        with patch.dict("os.environ", {"CARGO_TARGET_DIR": "/somewhere/else"}):
            self.assertEqual(packages.checked_build("dev", "python"), self.folder)
            self.assertNotEqual(packages.native_output("dev"), old)


if __name__ == "__main__":
    unittest.main()

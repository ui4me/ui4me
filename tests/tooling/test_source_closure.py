"""Standalone source staging must preserve sibling crates and build assets."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tools.ui4me_dev.common import ROOT

spec = importlib.util.spec_from_file_location("source_support", ROOT / "bindings/python/_build_support.py")
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


class SourceClosureTests(unittest.TestCase):
    def tree(self, root: Path):
        for name, content in {
            "Cargo.toml": '[workspace]\nmembers=["crates/core", "crates/render"]\n[workspace.dependencies]\nrender={path="crates/render"}\n',
            "Cargo.lock": "version = 4\n", "rust-toolchain.toml": '[toolchain]\nchannel="1.99.1"\n', "LICENSE": "MIT\n",
            "crates/core/Cargo.toml": '[package]\nname="core"\nversion="0.2.0"\n[dependencies]\nrender={workspace=true}\n',
            "crates/core/src/lib.rs": "// core\n",
            "crates/render/Cargo.toml": '[package]\nname="render"\nversion="0.2.0"\n',
            "crates/render/assets/font/OFL.txt": "Font license\n",
            "crates/render/assets/font/test.ttf": "Fixture bytes\n",
        }.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def test_sibling_crates_and_nested_assets_survive_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.tree(root / "source")
            support.stage_native_source(root / "source", root / "archive")
            self.assertEqual((root / "archive/crates/render/assets/font/test.ttf").read_bytes(), b"Fixture bytes\n")
            self.assertEqual(len(support.native_source_roots(root / "archive")), 2)

    def test_local_dependency_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.tree(root / "source")
            manifest = root / "source/crates/core/Cargo.toml"
            manifest.write_text(manifest.read_text() + 'outside={path="../../../outside"}\n')
            with self.assertRaisesRegex(ValueError, "escapes"):
                support.stage_native_source(root / "source", root / "archive")

    def test_nested_font_notice_is_collected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.tree(root / "source")
            support.collect_notices({"packages": [{"name": "render", "version": "0.2.0", "source": None,
                                     "manifest_path": str(root / "source/crates/render/Cargo.toml")}]}, root / "notices")
            target = root / "notices/licenses/render-0.2.0/assets/font/OFL.txt"
            self.assertEqual(target.read_text(), "Font license\n")
            recorded = json.loads((root / "notices/third-party.json").read_text())["notice_files"]
            self.assertEqual(len(recorded), 1)


if __name__ == "__main__":
    unittest.main()

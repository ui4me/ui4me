from pathlib import Path
import shutil
import tempfile
import unittest

from tools.ui4me_dev.common import ROOT, DevError
from tools.ui4me_dev.versioning import generated, replacements, synchronize


class VersioningTests(unittest.TestCase):
    def test_drift_is_rejected_and_explicit_update_repairs_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ["VERSION", *replacements("0.2.0"), *generated("0.2.0")]:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            synchronize("0.2.0", root=root)
            target = root / "bindings/powershell/Ui4me.Managed/BuildVersion.cs"
            target.write_text(target.read_text().replace("0.2.0", "0.1.0"))
            with self.assertRaisesRegex(DevError, "Version metadata differs"):
                synchronize(root=root)
            synchronize("0.2.1", root=root)
            synchronize(root=root)
            self.assertIn("0.2.1", target.read_text())

    def test_prerelease_requires_deliberate_mapping(self):
        with self.assertRaisesRegex(DevError, "Prerelease mapping"):
            synchronize("0.2.0rc1")


if __name__ == "__main__":
    unittest.main()

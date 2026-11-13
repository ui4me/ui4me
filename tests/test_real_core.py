"""Optional installed Core integration; skipped until qualified Core wheel exists."""
from __future__ import annotations
import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec('ui4me_core') is not None, 'ui4me-core wheel not installed')
class InstalledCoreTests(unittest.TestCase):
    def test_exact_identity(self):
        from ui4me import Application, Document, Window, LiveBitmap, host_binary
        from ui4me_core import Application as CA, Document as CD, Window as CW, LiveBitmap as CL, host_binary as CH
        self.assertIs(Application, CA)
        self.assertIs(Document, CD)
        self.assertIs(Window, CW)
        self.assertIs(LiveBitmap, CL)
        self.assertIs(host_binary, CH)


if __name__ == '__main__':
    unittest.main()

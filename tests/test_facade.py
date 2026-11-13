"""Identity tests: UI4ME must not create its own runtime or copy Core code."""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


class FacadeTests(unittest.TestCase):
    def setUp(self):
        fake = types.ModuleType('ui4me_core')
        for symbol in ('Application', 'Window', 'Document', 'StaleDocumentError',
                       'RpcClient', 'RpcError', 'ProtocolError', 'DisconnectedError',
                       'LiveBitmap', 'host_binary'):
            setattr(fake, symbol, type(symbol, (), {}) if symbol != 'host_binary' else lambda: '/test/host')
        self.fake = fake
        self.inject = patch.dict(sys.modules, {'ui4me_core': fake})
        self.inject.start()
        import ui4me
        self.facade = importlib.reload(ui4me)

    def tearDown(self):
        self.inject.stop()

    def test_identity_and_public_exports(self):
        for name in self.facade.__all__:
            self.assertIs(getattr(self.facade, name), getattr(self.fake, name))
            self.assertIn(name, dir(self.facade))

    def test_unknown_attributes_are_rejected(self):
        with self.assertRaises(AttributeError):
            _ = self.facade.DefinitelyNotCore

    def test_version_is_independent_from_core(self):
        self.assertEqual(self.facade.__version__, '0.1.0')

    def test_no_embedded_runtime_or_internal_core_copy(self):
        path = Path(self.facade.__file__).parent
        self.assertEqual(sorted(x.name for x in path.iterdir() if x.is_file()), ['__init__.py'])

    def test_missing_core_has_actionable_error(self):
        # Force the loader to behave as it would before Core is available.
        original = self.facade.import_module
        with patch.object(self.facade, 'import_module', side_effect=ModuleNotFoundError("No module named 'ui4me_core'", name='ui4me_core')):
            with self.assertRaisesRegex(ModuleNotFoundError, 'Install the Core wheel'):
                _ = self.facade.Application


if __name__ == '__main__':
    unittest.main()

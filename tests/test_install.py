from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import fetch_gatt
import install
from render_ha import render


class InstallTests(unittest.TestCase):
    def test_staging_builds_a_self_contained_tree_without_service_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(install.subprocess, 'run') as run:
            root = Path(directory)
            files = install.install_files(root)
            self.assertEqual(len(files), 10)
            self.assertEqual((root / 'opt/projector-bridge/projector_bridge.py').read_bytes(),
                             (install.ROOT / 'runtime/projector_bridge.py').read_bytes())
            fetch_gatt.verify((root / 'opt/projector-bridge/core/ble_dbus.py').read_bytes())
            unit = (root / 'etc/systemd/system/projector-ble.service').read_text()
            self.assertIn('EnvironmentFile=/etc/projector-bridge/bridge.env', unit)
            self.assertEqual((root / 'etc/projector-bridge/bridge.env').stat().st_mode & 0o777, 0o600)
            self.assertFalse((root / 'var/lib/bluetooth').exists())
            self.assertFalse((root / 'var/lib/projector-ble').exists())
            run.assert_not_called()

    def test_existing_installation_or_state_aborts_before_any_write(self):
        reserved = ('opt/projector-bridge', 'etc/projector-bridge',
                    'etc/systemd/system/projector-ble.service',
                    'etc/systemd/system/projector-ble.service.d', 'var/lib/projector-ble')
        for name in reserved:
            with self.subTest(existing=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                marker = root / name
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text('keep this existing state')
                with self.assertRaises(FileExistsError):
                    install.install_files(root)
                self.assertEqual(marker.read_text(), 'keep this existing state')
                self.assertEqual([p for p in root.rglob('*') if p.is_file()], [marker])

    def test_tampered_dependency_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            fetch_gatt.verify(b'import os # tampered dependency')

    def test_renderer_selects_entity_without_changing_source_or_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            render('remote.test_projector', root)
            scripts = (root / 'scripts.yaml').read_text()
            self.assertIn("is_state('remote.test_projector', 'on')", scripts)
            self.assertNotIn('remote.projector', scripts)
            self.assertIn('remote.projector', (install.ROOT / 'home-assistant/scripts.yaml').read_text())
            helper = json.loads((root / 'voice-helper.json').read_text())
            self.assertEqual(helper['value_template'], "{{ is_state('remote.test_projector', 'on') }}")
            self.assertEqual(helper['turn_on'][0]['target']['entity_id'], 'script.projector_turn_on')
            self.assertEqual(helper['turn_off'][0]['target']['entity_id'], 'script.projector_turn_off')
            with self.assertRaises(FileExistsError):
                render('remote.other', root)
            self.assertEqual((root / 'scripts.yaml').read_text(), scripts)

    def test_renderer_rejects_non_entity_template_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            for invalid in ('light.projector', "remote.x' }}", 'remote.X', 'remote.a\nscript:'):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    render(invalid, Path(directory))


if __name__ == '__main__':
    unittest.main()

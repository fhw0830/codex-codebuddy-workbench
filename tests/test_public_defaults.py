"""Public installs must not inherit another user's directories or models."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.service import Service
from backend.runtime_paths import runtime_cache


class PublicDefaults(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)/'private-data'
        self.service = Service(ROOT, data=self.data, connect=False)
        self.conversation = self.service.store.conversations()[0]['id']

    def tearDown(self):
        self.service.close()
        self.service.store.db.close()
        self.temp.cleanup()

    def test_default_directories_stay_in_own_data(self):
        self.assertEqual(self.service.archive, self.data/'archive')
        self.assertEqual(Path(self.service.preferences(self.conversation)['workdir']), self.data/'agent-workspace')
        self.assertEqual(self.service.documents(), [])

    def test_new_install_starts_in_discussion(self):
        self.assertEqual(self.service.preferences(self.conversation)['access_mode'], 'discussion')

    def test_model_defaults_come_from_connected_catalogs(self):
        prefs = self.service.preferences(self.conversation)
        self.assertEqual(prefs['codex_model'], '')
        self.assertEqual(prefs['codebuddy_model'], '')
        self.service.health['codex']['models'] = [{'id': 'available-codex'}]
        self.service.health['codebuddy']['models'] = [{'id': 'available-buddy'}]
        prefs = self.service.preferences(self.conversation)
        self.assertEqual(prefs['codex_model'], 'available-codex')
        self.assertEqual(prefs['codebuddy_model'], 'available-buddy')

    def test_selected_model_is_not_silently_replaced(self):
        self.service.health['codebuddy']['models'] = [{'id': 'selected'}, {'id': 'other'}]
        self.service.set_preferences(self.conversation, {'codebuddy_model': 'selected'})
        self.service.health['codebuddy']['models'].reverse()
        self.assertEqual(self.service.preferences(self.conversation)['codebuddy_model'], 'selected')

    def test_cache_uses_user_local_app_data(self):
        with patch('backend.runtime_paths.os.name', 'nt'), patch.dict('os.environ', {'LOCALAPPDATA': str(Path(self.temp.name)/'cache')}):
            self.assertEqual(runtime_cache(), Path(self.temp.name)/'cache/CodeDuo/runtime')


if __name__ == '__main__':
    unittest.main()

"""Offline checks only; no production licenses or database are touched."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
config = types.ModuleType('config')
for key, value in dict(APP_NAME='Test', PROJECT_NAME='test', CORS_ORIGINS=[], ADMIN_TOKEN='test', SUPABASE_URL='', SUPABASE_SERVICE_KEY='', STATE_SYNC_MIN_SECONDS=10).items():
    setattr(config, key, value)
sys.modules['config'] = config
spec = importlib.util.spec_from_file_location('test_server', ROOT / 'server/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class SecurityTests(unittest.TestCase):
    def setUp(self):
        server.RUNTIME_STATE['zuncia']['licenses'] = [dict(id='test',key='test-key',active=True,online=True,session_token='test-token',client_id='test-client',script_id='test-script',last_seen_at=server.utc_now())]
        server.save_state = lambda **kwargs: None
        server.ensure_shapes()

    def test_legacy_geometry_cannot_lock(self):
        before = copy.deepcopy(server.RUNTIME_STATE)
        for source in ['bot_keydown', 'loader_devtools_open', 'loader_devtools_watch', 'client', 'loader_keydown']:
            result = server.api_tamper_report_for_app(server.TamperPayload(token='test-token',source=source), 'zuncia')
            self.assertTrue(result['ignored'])
        self.assertEqual(server.RUNTIME_STATE, before)

    def test_explicit_keyboard_report_locks_identified_license(self):
        result = server.api_tamper_report_for_app(server.TamperPayload(token='test-token',source='loader_keydown_v2'), 'zuncia')
        self.assertTrue(result['success'])
        lic=server.RUNTIME_STATE['zuncia']['licenses'][0]
        self.assertTrue(lic['tamper_detected'])
        self.assertFalse(lic['active'])

    def test_anonymous_report_does_not_guess_online_license(self):
        result=server.api_tamper_report_for_app(server.TamperPayload(source='loader_keydown_v2'), 'zuncia')
        self.assertFalse(result['success'])
        self.assertTrue(server.RUNTIME_STATE['zuncia']['licenses'][0]['active'])

if __name__ == '__main__':
    unittest.main()

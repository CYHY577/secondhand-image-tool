import importlib.util
import io
import json
import os
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('cloud_app', 'scf-web/app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class CloudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {'APP_ACCESS_PASSWORD': 'test-only-password', 'DASHSCOPE_API_KEY': 'test-only-key'}, clear=True)
        cls.env.start()
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.env.stop()

    def request(self, method, path, body=None, auth=False, headers=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_address[1])
        headers = headers or {}
        if auth:
            headers['Cookie'] = 'wt_session=' + app.new_session()
        conn.request(method, path, body, headers)
        result = conn.getresponse()
        output = result.status, dict(result.getheaders()), result.read()
        conn.close()
        return output

    def test_login_and_access(self):
        self.assertEqual(self.request('GET', '/')[0], 303)
        self.assertEqual(self.request('GET', '/api/health')[0], 401)
        self.assertEqual(self.request('POST', '/login', 'password=bad')[0], 401)
        status, headers, _ = self.request('POST', '/login', 'password=test-only-password')
        self.assertEqual(status, 303)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('Secure', headers['Set-Cookie'])
        status, _, page = self.request('GET', '/', auth=True)
        self.assertEqual(status, 200)
        self.assertNotIn(b'test-only-key', page)
        self.assertEqual(self.request('GET', '/app.py', auth=True)[0], 404)

    def test_forged_expired_sessions(self):
        self.assertFalse(app.valid_session('9999999999.forged'))
        self.assertFalse(app.valid_session('1.' + app.signature('1')))
        self.assertTrue(app.valid_session(app.new_session()))

    def test_invalid_and_cross_origin_requests(self):
        self.assertEqual(self.request('POST', '/login', 'password=test-only-password', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/dashscope/other', '{}', auth=True)[0], 403)
        self.assertEqual(self.request('POST', '/api/dashscope'+app.GENERATION, '[]', auth=True)[0], 400)

    def test_async_forwarding_and_upstream_errors(self):
        with patch.object(app, 'build_opener') as factory:
            response = MagicMock(status=200)
            response.read.return_value = b'{"output":{"task_id":"abc-123"}}'
            factory.return_value.open.return_value.__enter__.return_value = response
            status, _, _ = self.request('POST', '/api/dashscope'+app.GENERATION, '{"input":{},"parameters":{"n":99}}', auth=True)
            self.assertEqual(status, 200)
            req = factory.return_value.open.call_args.args[0]
            self.assertTrue(req.full_url.endswith(app.ASYNC_GENERATION))
            self.assertEqual(req.get_header('Authorization'), 'Bearer test-only-key')
            self.assertEqual(req.get_header('X-dashscope-async'), 'enable')
            self.assertEqual(json.loads(req.data)['parameters']['n'], 1)
            self.assertEqual(self.request('GET', '/api/dashscope/api/v1/tasks/abc-123', auth=True)[0], 200)
            factory.return_value.open.side_effect = HTTPError('https://example.com', 401, '', {}, io.BytesIO(b'{"message":"invalid key"}'))
            status, _, body = self.request('GET', '/api/dashscope/api/v1/tasks/abc-123', auth=True)
            self.assertEqual(status, 401)
            self.assertIn(b'invalid key', body)


if __name__ == '__main__':
    unittest.main()

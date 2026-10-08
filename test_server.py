import io
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from server import Handler, ThreadingHTTPServer, GENERATION


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_address[1])
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_pages_health_and_private_files(self):
        for path in ['/', '/admin.html', '/api/health']:
            self.assertEqual(self.request('GET', path)[0], 200)
        self.assertEqual(self.request('GET', '/server.py')[0], 404)

    def test_origin_path_and_key_restrictions(self):
        self.assertEqual(self.request('GET', '/', headers={'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/dashscope' + GENERATION)[0], 401)
        self.assertEqual(self.request('POST', '/api/dashscope/anything')[0], 403)

    @patch('server.build_opener')
    def test_generation_and_poll_forwarding(self, opener):
        response = MagicMock(status=200, headers={'Content-Type': 'application/json'})
        response.read.return_value = b'{"output":{"task_id":"abc-123"}}'
        opener.return_value.open.return_value.__enter__.return_value = response
        self.assertEqual(self.request('POST', '/api/dashscope' + GENERATION, '{}',
                                     {'Authorization': 'Bearer test-placeholder'})[0], 200)
        req = opener.return_value.open.call_args.args[0]
        self.assertEqual(req.full_url, 'https://dashscope.aliyuncs.com' + GENERATION)
        self.assertEqual(req.data, b'{}')
        self.assertEqual(req.get_header('Authorization'), 'Bearer test-placeholder')
        self.assertEqual(self.request('GET', '/api/dashscope/api/v1/tasks/abc-123',
                                     headers={'Authorization': 'Bearer test-placeholder'})[0], 200)
        self.assertEqual(opener.return_value.open.call_args.args[0].method, 'GET')

    @patch('server.build_opener')
    def test_upstream_errors_preserved(self, opener):
        opener.return_value.open.side_effect = HTTPError('https://example.com', 401, 'Denied',
                                                       {}, io.BytesIO(b'{"message":"invalid key"}'))
        status, body = self.request('POST', '/api/dashscope' + GENERATION, '{}',
                                    {'Authorization': 'Bearer test-placeholder'})
        self.assertEqual(status, 401)
        self.assertIn(b'invalid key', body)
        opener.return_value.open.side_effect = URLError('offline')
        self.assertEqual(self.request('POST', '/api/dashscope' + GENERATION, '{}',
                                     {'Authorization': 'Bearer test-placeholder'})[0], 502)


if __name__ == '__main__':
    unittest.main()

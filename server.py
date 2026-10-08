"""Local web app and same-origin DashScope proxy. Python 3, no pip packages."""
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
UPSTREAM = 'https://dashscope.aliyuncs.com'
GENERATION = '/api/v1/services/aigc/multimodal-generation/generation'
MAX_BODY = 30 * 1024 * 1024  # Allow base64 expansion of the UI's 20 MB image limit.


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Do not log credentials, prompts, or image data.

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        port = self.server.server_address[1]
        hosts = {f'localhost:{port}', f'127.0.0.1:{port}'}
        host = self.headers.get('Host', '')
        if host not in hosts:
            return self.reply(403, {'message': 'Invalid local host'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + host:
            return self.reply(403, {'message': 'Open the page through the local server'})
        path = urlsplit(self.path).path
        if path == '/api/health' and self.command == 'GET':
            return self.reply(200, {'service': 'secondhand-local-proxy'})
        if path.startswith('/api/dashscope/'):
            target = path[len('/api/dashscope'):]
            valid = (self.command == 'POST' and target == GENERATION) or (
                self.command == 'GET' and target.startswith('/api/v1/tasks/')
                and target[len('/api/v1/tasks/'):].replace('-', '').isalnum())
            if not valid:
                return self.reply(403, {'message': 'Unsupported API path or method'})
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Bearer ') or not auth[7:].strip():
                return self.reply(401, {'message': '请先配置 API Key'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.reply(400, {'message': 'Invalid body length'})
            if length < 0 or length > MAX_BODY:
                return self.reply(413, {'message': '图片请求过大，请压缩图片后重试'})
            body = self.rfile.read(length) if self.command == 'POST' else None
            req = Request(UPSTREAM + target, data=body, method=self.command,
                          headers={'Authorization': auth, 'Content-Type': 'application/json'})
            try:
                with build_opener(NoRedirect).open(req, timeout=180) as response:
                    return self.reply(response.status, response.read(),
                                      response.headers.get('Content-Type', 'application/json'))
            except HTTPError as exc:
                return self.reply(exc.code, exc.read(),
                                  exc.headers.get('Content-Type', 'application/json'))
            except (URLError, TimeoutError, OSError):
                return self.reply(502, {'message': '本地服务无法连接 DashScope，请检查网络、VPN 或证书设置后重试'})
        pages = {'/': 'index.html', '/index.html': 'index.html', '/admin.html': 'admin.html'}
        if self.command == 'GET' and path in pages:
            return self.reply(200, (ROOT / pages[path]).read_bytes(), 'text/html; charset=utf-8')
        self.reply(404, {'message': 'Not found'})


if __name__ == '__main__':
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8080), Handler)
    except OSError:
        raise SystemExit('8080 端口已被占用，请先关闭旧服务，再重新启动。')
    print('请在浏览器打开 http://localhost:8080 （保持此终端开启，Ctrl+C 停止）', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

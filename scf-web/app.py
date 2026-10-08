"""Tencent SCF Web function: private site and server-side DashScope adapter."""
import hashlib
import hmac
import json
import os
import re
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
MAX_BODY = 4 * 1024 * 1024
GENERATION = '/api/v1/services/aigc/multimodal-generation/generation'
ASYNC_GENERATION = '/api/v1/services/aigc/image-generation/generation'
LOGIN = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>二手商品图工具 · 登录</title><style>body{font:16px system-ui;background:#f5f7fb;color:#172337;display:grid;place-items:center;min-height:95vh}form{background:white;padding:36px;border-radius:20px;width:min(340px,80vw);box-shadow:0 8px 40px #16223912}input,button{box-sizing:border-box;width:100%;padding:14px;margin:10px 0;border-radius:9px;border:1px solid #ccd3df;font:inherit}button{background:#0d9488;color:white;border:0}p{color:#64748b;line-height:1.7}</style><form method="post" action="/login"><h2>二手商品图工具</h2><p>输入网站访问密码即可使用。图片服务已由后台配置。</p><label for="password">访问密码</label><input id="password" name="password" type="password" required autocomplete="current-password"><button>进入工具</button></form></html>'''


def signature(value):
    return hmac.new(os.environ.get('APP_ACCESS_PASSWORD', '').encode(), value.encode(), hashlib.sha256).hexdigest()


def new_session():
    expiry = str(int(time.time()) + 86400)
    return expiry + '.' + signature(expiry)


def valid_session(value):
    try:
        expiry, digest = value.split('.', 1)
        return int(expiry) > time.time() and hmac.compare_digest(signature(expiry), digest)
    except (ValueError, TypeError):
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data, content_type='application/json; charset=utf-8', headers=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        for key, value in {'Content-Type': content_type, 'Content-Length': str(len(data)),
                           'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                           'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin', **(headers or {})}.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length < 0 or length > MAX_BODY:
            raise ValueError('请求过大，请压缩图片后重试')
        return self.rfile.read(length)

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        path = urlsplit(self.path).path
        if path == '/healthz' and self.command == 'GET':
            return self.reply(200, {'status': 'ok'})
        password = os.environ.get('APP_ACCESS_PASSWORD', '')
        if not os.environ.get('DASHSCOPE_API_KEY'):
            return self.reply(503, {'message': '服务端尚未完成配置'})
        origin = self.headers.get('Origin')
        if origin and (urlsplit(origin).netloc != self.headers.get('Host') or urlsplit(origin).scheme not in ('https', 'http')):
            return self.reply(403, {'message': '请从本站打开工具'})
        if password and path == '/login':
            if self.command == 'GET':
                return self.reply(200, LOGIN.encode(), 'text/html; charset=utf-8')
            try:
                supplied = parse_qs(self.read_body().decode()).get('password', [''])[0]
            except (ValueError, UnicodeError):
                return self.reply(400, {'message': '登录请求无效'})
            if not hmac.compare_digest(supplied.encode(), password.encode()):
                return self.reply(401, LOGIN.replace('输入网站访问密码即可使用。', '密码不正确，请重试。').encode(), 'text/html; charset=utf-8')
            secure = '' if os.environ.get('LOCAL_TEST') == '1' else '; Secure'
            return self.reply(303, b'', headers={'Location': '/', 'Set-Cookie': f'wt_session={new_session()}; Path=/; Max-Age=86400; HttpOnly; SameSite=Strict{secure}'})
        if password:
            try:
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                logged_in = 'wt_session' in cookie and valid_session(cookie['wt_session'].value)
            except Exception:
                logged_in = False
            if not logged_in:
                if path.startswith('/api/'):
                    return self.reply(401, {'message': '登录已过期，请刷新页面重新登录'})
                return self.reply(303, b'', headers={'Location': '/login'})
        if path == '/api/health':
            return self.reply(200, {'service': 'secondhand-cloud', 'configured': True})
        if path.startswith('/api/dashscope/'):
            target = path[len('/api/dashscope'):]
            create = self.command == 'POST' and target == GENERATION
            poll = self.command == 'GET' and re.fullmatch(r'/api/v1/tasks/[a-zA-Z0-9-]+', target)
            if not create and not poll:
                return self.reply(403, {'message': '不支持的接口'})
            try:
                body = self.read_body() if create else None
                if create:
                    payload = json.loads(body)
                    payload['model'] = 'wan2.7-image'
                    payload['parameters'] = {'size': '1K', 'n': 1}
                    body = json.dumps(payload).encode()
            except (ValueError, TypeError, UnicodeError):
                return self.reply(400, {'message': '图片请求格式无效或超过 4MB'})
            host = os.environ.get('DASHSCOPE_API_HOST', 'https://dashscope.aliyuncs.com').rstrip('/')
            parsed = urlsplit(host)
            allowed = parsed.hostname in ('dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com') or re.fullmatch(r'[a-zA-Z0-9-]+\.(cn-beijing|ap-southeast-1)\.maas\.aliyuncs\.com', parsed.hostname or '')
            if parsed.scheme != 'https' or not allowed or parsed.username or parsed.password or parsed.port or parsed.path or parsed.query or parsed.fragment:
                return self.reply(503, {'message': '服务端 API Host 配置无效'})
            headers = {'Authorization': 'Bearer ' + os.environ['DASHSCOPE_API_KEY'], 'Content-Type': 'application/json'}
            if create:
                headers['X-DashScope-Async'] = 'enable'
            request = Request(host + (ASYNC_GENERATION if create else target), data=body, method=self.command, headers=headers)
            try:
                with build_opener(NoRedirect).open(request, timeout=50) as response:
                    return self.reply(response.status, response.read())
            except HTTPError as exc:
                return self.reply(exc.code, exc.read())
            except (URLError, TimeoutError, OSError):
                return self.reply(502, {'message': '无法连接图片服务，请稍后重试'})
        pages = {'/': 'index.html', '/index.html': 'index.html', '/admin.html': 'admin.html'}
        if self.command == 'GET' and path in pages:
            return self.reply(200, (ROOT / pages[path]).read_bytes(), 'text/html; charset=utf-8')
        self.reply(404, {'message': 'Not found'})


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '9000'))), Handler).serve_forever()

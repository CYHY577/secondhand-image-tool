"""Build cloud-only frontend without modifying the local version or embedding keys."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
target = root / 'scf-web'
source = (root / 'index.html').read_text(encoding='utf-8')
start = source.index('let localProxyAvailable;')
end = source.index('async function callWanAPI', start)
source = source[:start] + '''async function applyProxy(url) {
  return '/api/dashscope' + new URL(url).pathname;
}

''' + source[end:]
source = source.replace("const apiKey = localStorage.getItem(LS.API_KEY) || '';", "const apiKey = 'server-managed';")
source = source.replace("'Authorization': `Bearer ${apiKey}`, ", '')
source = source.replace("{ headers: { 'Authorization': `Bearer ${apiKey}` } }", "{ credentials: 'same-origin' }")
source = source.replace("$('api-notice').classList.toggle('visible', !localStorage.getItem(LS.API_KEY));", "$('api-notice').classList.remove('visible');")
source = source.replace("for (let i = 0; i < 80; i++)", "for (let i = 0; i < 160; i++)")
source = source.replace("if (status === 'FAILED')", "if (status === 'FAILED' || status === 'CANCELED' || status === 'UNKNOWN')")
source = source.replace("API Key", "服务连接")
source = source.replace("</body>", '''<script>
function openSettings() { alert('图片服务已在云端配置，无需填写 Key 或代理。'); }
window.addEventListener('load', () => {
  document.getElementById('cfg-key').disabled = true;
});
</script></body>''')
(target / 'index.html').write_text(source, encoding='utf-8')
admin = (root / 'admin.html').read_text(encoding='utf-8')
admin = admin.replace('</body>', '''<script>
window.addEventListener('load', () => {
  const key = document.getElementById('cfg-key');
  key.value = ''; key.disabled = true; key.placeholder = '已在腾讯云服务端配置';
});
</script></body>''')
(target / 'admin.html').write_text(admin, encoding='utf-8')
with zipfile.ZipFile(root / '腾讯云Web部署包.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in ('app.py', 'scf_bootstrap', 'index.html', 'admin.html'):
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (0o100755 if name == 'scf_bootstrap' else 0o100644) << 16
        archive.writestr(info, (target / name).read_bytes())
print('Built 腾讯云Web部署包.zip (no credentials included)')

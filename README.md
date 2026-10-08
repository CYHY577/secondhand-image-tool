# Secondhand Image Tool · 二手商品图生成工具

A prototype that turns secondhand product photos and listing information into downloadable promotional images. Built with vanilla JavaScript, HTML/CSS and a Python HTTP service, with Alibaba Cloud DashScope integration.

面向留学生二手转卖场景：输入商品名称、价格和卖点，上传照片，选择展示模板，生成并下载商品展示图。

## Features / 功能

- 商品照片上传、模板选择、文案排版与 PNG 导出。
- DashScope 图片生成请求与异步任务状态查询。
- 同源 Python 代理，避免浏览器直接跨域请求图片服务。
- 管理与调试页面，查看最近一次生成记录及 API 错误。
- 腾讯云 SCF Web 函数部署代码；云端 API Key 通过环境变量配置。

## Run locally / 本地运行

Requires Python 3.10+; no third-party Python packages required.

```bash
git clone https://github.com/CYHY577/secondhand-image-tool.git
cd secondhand-image-tool
python3 server.py
```

Open **http://localhost:8080/**. On Windows, use `python server.py` if appropriate for your installation. Keep the terminal running. Opening `index.html` directly is not sufficient for the same-origin API proxy.

Configure your own DashScope API key in the local UI to use AI generation. The local version stores settings in the browser. Do not commit keys or include them in screenshots. Image generation requires access to the selected model and may incur provider charges.

## Architecture / 实现

```text
Browser: index.html / admin.html
             |
             | same-origin /api/dashscope/*
             v
Python HTTP server -> DashScope API -> task polling -> result image
             |
             +-> HTML/CSS composition -> html2canvas PNG export
```

The local server binds to `127.0.0.1:8080`. The SCF entry point binds to `0.0.0.0:9000`. html2canvas is loaded from a CDN and is required for image export.

## Tencent Cloud deployment / 云部署

```bash
python3 build-scf.py
```

Upload the generated `腾讯云Web部署包.zip` to a Python SCF Web function. Listen on port `9000`, use `scf_bootstrap` to start the HTTP server, and allow enough execution time for upstream calls (the prepared configuration uses 60 seconds).

Environment variables:

| Variable | Purpose |
| --- | --- |
| `DASHSCOPE_API_KEY` | Required; your own provider key, configured on the server |
| `DASHSCOPE_API_HOST` | API host matching your key's region / workspace |
| `APP_ACCESS_PASSWORD` | Optional; when absent, the website and generation API are public |
| `PORT` | Optional; defaults to `9000` |

The server does not automatically read `.env` files. Set variables in your shell or cloud console. A public deployment without a password lets visitors invoke the configured paid model; add usage limits before sharing widely. GitHub Pages alone cannot run this Python backend.

## Validation / 测试

```bash
python3 -m unittest test_server test_scf_web
node test-client.cjs
```

The tests exercise local proxy behavior, session handling and mocked upstream requests. They do not verify real model access, account billing or public cloud availability.

## Project status / 项目状态

This is a portfolio prototype. A Tencent Cloud deployment was created, but successful public access and end-to-end paid image generation have not been verified. No live-demo availability is claimed here. Model names, endpoint formats and region/workspace compatibility must be checked against the provider documentation for your own account before deployment.

Some preview flows use CSS composition without AI generation. These previews must not be interpreted as proof of a successful model call.

## Files

| Path | Purpose |
| --- | --- |
| `index.html` | Product image creation interface |
| `admin.html` | Configuration and generation diagnostics |
| `server.py` | Local same-origin HTTP service |
| `scf-web/app.py` | Cloud server, optional login and API adapter |
| `build-scf.py` | Generate cloud frontend and deployment archive |
| `test_*.py`, `test-client.cjs` | Backend and frontend checks |

Private documents, credentials, account-specific deployment records and generated archives are excluded from this source release.

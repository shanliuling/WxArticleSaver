<p align="right">
  <a href="./README.md">中文</a> | <a href="./README_EN.md">English</a>
</p>

<h1 align="center">WxArticleSaver</h1>

<p align="center">
  本地运行的微信公众号文章导出 / 归档工具。<br>
  打开你可以正常阅读的公众号文章，点击「导出本文」，即可保存正文、图片以及可直接获取的视频资源。
</p>

<p align="center">
  <strong>Windows 10 / 11</strong> · <strong>macOS Apple Silicon（实验性）</strong> · <strong>AGPL-3.0</strong><br>
  <a href="https://github.com/shanliuling/WxArticleSaver/releases/latest"><img src="https://img.shields.io/github/v/release/shanliuling/WxArticleSaver?style=flat-square" alt="GitHub Release" /></a>
  <a href="https://github.com/shanliuling/WxArticleSaver/releases"><img src="https://img.shields.io/github/downloads/shanliuling/WxArticleSaver/total?style=flat-square" alt="GitHub Downloads" /></a>
  <a href="https://github.com/shanliuling/WxArticleSaver/releases/latest"><img src="https://img.shields.io/badge/Windows-Portable-success?style=flat-square" alt="Windows Portable" /></a>
  <img src="https://img.shields.io/badge/macOS-Experimental-orange?style=flat-square" alt="macOS Experimental" />
  <a href="https://linux.do/"><img src="https://img.shields.io/badge/LINUX%20DO-社区友链-555?style=flat" alt="LINUX DO 社区友链" /></a>
</p>

<p align="center">
  <img src="./docs/images/hero-export-demo.jpg"
       alt="WxArticleSaver 微信文章导出 Markdown 效果"
       width="100%" />
</p>

## ✨ 功能

- 📄 一键导出 **Markdown / HTML / TXT**
- 🖼️ 自动下载并保存文章图片
- 🎬 支持保存文章内**可直接获取的视频资源**；无法直接下载时保留原始链接
- 🧾 同时保存原始响应、文章元信息等归档数据
- 🔒 文章内容默认只保存在本机
- 🚫 不需要登录第三方账号，也不依赖云端服务
- 🪟 Windows 提供免 Python 的便携版
- 🍎 macOS 已支持 Apple Silicon，并提供 `.app / .dmg` 构建能力（实验性）

<p align="center">
  <img src="./docs/images/workflow-demo.jpg"
       alt="WxArticleSaver 微信文章导出使用流程"
       width="100%" />
</p>

## 🖥️ 平台支持

| 平台 | 状态 | 使用方式 |
| --- | --- | --- |
| Windows 10 / 11 | ✅ 推荐 | Release 便携版 / 源码运行 |
| macOS Apple Silicon | 🧪 实验性 | DMG / App / 源码运行 |
| macOS Intel | ❌ 暂未提供 DMG | 暂未正式支持 |
| Linux | ❌ | 暂未支持 |

## 🚀 快速开始

### Windows：免安装便携版（推荐）

1. 前往 **[Releases 最新发布页](https://github.com/shanliuling/WxArticleSaver/releases/latest)**。
2. 下载最新的 `WxArticleSaver-*-Windows-x64.zip`。
3. 解压到任意文件夹。
4. 双击运行 `WxArticleSaver.exe`。
5. 完全退出并重新打开微信。
6. 打开公众号文章，点击右下角 **「导出本文」**。

导出的文章默认位于 `WxArticleSaver.exe` 同级的 `exports`：

```text
WxArticleSaver/
├─ WxArticleSaver.exe
├─ runtime/
└─ exports/
   └─ 文章标题/
      ├─ article.md
      ├─ article.html
      ├─ article.txt
      ├─ raw_wechat_response.html
      ├─ meta.json
      ├─ images/
      └─ videos/
```

如果文章打开后没有出现按钮，先按 **Ctrl+R** 或右键刷新文章页面。

---

### macOS：Apple Silicon（实验性）

当前 macOS 实现支持 Apple Silicon（arm64），可构建 `.app` 和 `.dmg`。

源码运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./run_macos.command --service "Wi-Fi"
```

构建 DMG：

```bash
python scripts/build-macos.py
```

构建结果：

```text
dist/WxArticleSaver-macos-arm64.dmg
```

首次运行需要：

1. 将程序生成的 CA 导入当前用户的 `Login Keychain`。
2. 手动设置为 `Always Trust`。
3. 完全退出并重新打开微信 Mac。
4. 打开公众号文章；如果没有出现「导出本文」，按 `⌘R`。
5. 停止程序时回到终端按 `Ctrl+C`，等待代理恢复完成。

macOS 打包版默认导出到：

```text
~/Library/Application Support/WxArticleSaver/exports/
```

详细说明：

- [macOS 用户指南](./docs/macos-user-guide.md)
- [macOS 技术说明与故障排查](./docs/macos.md)

## 📦 导出内容

每篇文章会单独创建一个目录：

```text
exports/
└─ 文章标题/
   ├─ article.md
   ├─ article.html
   ├─ article.txt
   ├─ raw_wechat_response.html
   ├─ meta.json
   ├─ images/
   └─ videos/
```

其中：

- `article.md`：适合 Obsidian、Typora、知识库等场景
- `article.html`：尽量保留原始排版结构
- `article.txt`：纯文本版本
- `images/`：文章图片
- `videos/`：可以直接获取的视频文件
- `raw_wechat_response.html`：原始文章响应，方便后续重新处理
- `meta.json`：文章相关元信息

## 🎬 视频说明

公众号文章的视频资源通常不会直接写在初始 HTML 中。

如果你希望同时保存视频，建议：

1. 打开文章；
2. 先播放视频几秒；
3. 再点击「导出本文」。

对于可直接访问的视频文件或未加密 HLS，WxArticleSaver 会尝试保存到本地；如果资源无法直接获取、经过加密或存在 DRM，则**不会绕过保护措施**，只保留可用链接或占位信息。

## 🔄 为什么有时需要刷新？

微信桌面端可能直接从 WebView 缓存恢复已经打开过的文章，此时不会重新请求文章主 HTML，WxArticleSaver 就没有机会注入「导出本文」按钮。

- Windows：程序会在能够确认前台窗口为微信时，尽力自动执行一次 `Ctrl+R`。
- macOS：当前版本不会申请 Accessibility 权限，因此需要用户手动按 `⌘R`。

## 🔐 安全说明

WxArticleSaver 使用本地 `mitmproxy` 读取并修改微信文章的 HTTPS 响应，因此需要信任一个**由当前电脑本地生成的 CA 证书**。

工具只通过 PAC 将微信公众号文章及相关媒体域名发送到本地代理，其他网络请求正常情况下保持直连。

### Windows

首次运行会在当前 Windows 用户范围内配置所需证书和代理；程序正常退出时会尝试恢复原代理状态。

如果退出后网络异常，可运行：

```text
restore_proxy.bat
```

清理证书：

```text
remove_certificate.bat
```

### macOS

macOS 首版不会静默修改 Keychain。首次使用需要用户自行确认并信任 CA。

异常退出后可运行：

```text
restore_proxy_macos.command
```

清理证书：

```text
remove_certificate_macos.command
```

> 不要信任来源不明的 CA，也不要把本工具生成的 CA 私钥分享给其他人。

## 🛠️ Windows 源码运行

环境要求：

- Windows 10 / 11
- Python 3.11 / 3.12

下载源码后运行：

```text
install_and_run.bat
```

首次运行会自动安装所需 Python 依赖。

## ⚠️ 使用说明与免责声明

本项目用于对用户**合法有权访问的内容**进行个人离线归档、学习与研究。

请勿将本项目用于绕过付费、访问权限、DRM 或其他技术保护措施，也请勿用于未经授权的批量采集、版权内容再分发或其他侵害第三方权益的用途。使用者应自行遵守所在地适用法律法规及相关平台规则。

本项目按现状提供，不对因使用本项目产生的账号、数据、网络配置或其他损失作任何保证。若你不了解 HTTPS 本地代理和根证书的含义，请先阅读上方「安全说明」。

## 🤝 Contributing

欢迎提交 Issue 和 Pull Request。

如果你在不同版本的微信、Windows 或 macOS 上遇到兼容问题，欢迎附上系统版本、微信版本以及运行日志，方便定位。

## 📄 License

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 开源。

如果你修改本项目并以符合 AGPL 第 13 条的方式通过网络向用户提供其功能，应按 AGPL 的要求向这些用户提供相应源代码。完整条款见 [`LICENSE`](./LICENSE)。

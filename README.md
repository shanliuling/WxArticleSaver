<p align="right">
  <a href="./README.md">中文</a> | <a href="./README_EN.md">English</a>
</p>

<h1 align="center">WxArticleSaver</h1>

<p align="center">
  微信公众号文章本地导出工具。<br>
  打开文章，点击「导出本文」，即可保存正文、图片和视频资源。
</p>

<p align="center">
  <a href="https://github.com/shanliuling/WxArticleSaver/releases/latest"><img src="https://img.shields.io/github/v/release/shanliuling/WxArticleSaver?style=flat-square" alt="GitHub Release" /></a>
  <a href="https://github.com/shanliuling/WxArticleSaver/releases"><img src="https://img.shields.io/github/downloads/shanliuling/WxArticleSaver/total?style=flat-square" alt="GitHub Downloads" /></a>
  <img src="https://img.shields.io/badge/Windows-10%20%2F%2011-blue?style=flat-square" alt="Windows" />
  <img src="https://img.shields.io/badge/macOS-Apple%20Silicon-black?style=flat-square" alt="macOS Apple Silicon" />
  <img src="https://img.shields.io/badge/license-AGPL--3.0-orange?style=flat-square" alt="License" />
</p>

<p align="center">
  <img src="./docs/images/hero-export-demo.jpg" alt="WxArticleSaver 导出效果" width="100%" />
</p>

## 功能

- 📄 导出 Markdown / HTML / TXT
- 🖼️ 自动保存文章图片
- 🎬 支持文章内视频资源
- 🧾 保存文章元信息和原始页面数据
- 🔒 全程本地运行，不需要第三方账号或云服务
- 🪟 Windows 提供免 Python 便携版
- 🍎 macOS 提供 Apple Silicon DMG 安装包

<p align="center">
  <img src="./docs/images/workflow-demo.jpg" alt="WxArticleSaver 使用流程" width="100%" />
</p>

## 下载

前往 **[Releases](https://github.com/shanliuling/WxArticleSaver/releases/latest)** 下载最新版本。

| 平台 | 下载文件 | 使用方式 |
| --- | --- | --- |
| Windows 10 / 11 | `WxArticleSaver-v*-Windows-x64.zip` | 解压后双击 `WxArticleSaver.exe` |
| macOS Apple Silicon | `WxArticleSaver-v*-macOS-arm64.dmg` | 打开 DMG，将 App 拖入 Applications |

> macOS 当前支持 M1 / M2 / M3 / M4 等 Apple Silicon 机型。

## 使用

### Windows

1. 下载并解压 Windows ZIP。
2. 双击 `WxArticleSaver.exe`。
3. 完全退出并重新打开微信。
4. 打开公众号文章。
5. 点击右下角 **「导出本文」**。

如果按钮没有出现，按 `Ctrl+R` 或右键刷新文章页面。

导出目录：

```text
WxArticleSaver/
└─ exports/
   └─ 文章标题/
```

### macOS

1. 下载 `WxArticleSaver-v*-macOS-arm64.dmg`。
2. 打开 DMG，将 `WxArticleSaver.app` 拖入 Applications。
3. 第一次打开时，如果 macOS 提示无法验证开发者，请在 Finder 中右键 App → **打开**。
4. 按程序提示将生成的 CA 导入 Login Keychain，并设置为 `Always Trust`。
5. 完全退出并重新打开微信 Mac。
6. 打开公众号文章，点击 **「导出本文」**。

如果按钮没有出现，按 `⌘R` 刷新。

导出目录：

```text
~/Library/Application Support/WxArticleSaver/exports/
```

详细说明见 [macOS 用户指南](./docs/macos-user-guide.md)。

## 导出内容

```text
文章标题/
├─ article.md
├─ article.html
├─ article.txt
├─ raw_wechat_response.html
├─ meta.json
├─ images/
└─ videos/
```

如果文章包含视频，建议先播放几秒，再点击「导出本文」。

## 为什么有时需要刷新？

微信桌面端可能直接从 WebView 缓存恢复文章，此时不会重新请求文章页面，工具就无法注入「导出本文」按钮。

- Windows：程序会尽力自动刷新一次。
- macOS：当前需要手动按 `⌘R`。

## 安全说明

WxArticleSaver 使用本地 `mitmproxy` 处理微信公众号文章页面，因此首次使用需要信任当前电脑本地生成的 CA 证书。

工具通过 PAC 仅代理微信公众号文章和相关媒体请求，其他网络请求保持直连。

异常退出后：

- Windows：运行 `restore_proxy.bat`
- macOS：运行 `restore_proxy_macos.command`

## 源码运行

### Windows

需要 Python 3.11 / 3.12，运行：

```text
install_and_run.bat
```

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./run_macos.command --service "Wi-Fi"
```

## 使用说明

本项目用于对用户有权访问的内容进行个人离线归档、学习与研究。使用者应自行遵守所在地法律法规及相关平台规则。

## Contributing

欢迎提交 Issue 和 Pull Request。

## License

GNU Affero General Public License v3.0（AGPL-3.0）。完整条款见 [`LICENSE`](./LICENSE)。

<p align="right">
  <a href="./README.md">中文</a> | <a href="./README_EN.md">English</a>
</p>

<h1 align="center">WxArticleSaver</h1>

<p align="center">
  A local-first WeChat Official Account article archiving tool.<br>
  Open an article you can normally access, click "Export Article" in the bottom-right corner, and save the article text, images, and directly accessible media resources to your computer.
</p>

<p align="center">
  <strong>Windows 10 / 11</strong> · <strong>GNU AGPL-3.0</strong>
</p>

<p align="center">
  <img src="./docs/images/hero-export-demo.jpg"
       alt="WxArticleSaver WeChat article to Markdown export preview"
       width="100%" />
</p>

## Features

- 📄 One-click export to Markdown / HTML / TXT
- 🖼️ Automatically save article images
- 🎬 Support directly accessible media resources in articles
- 🔒 All article content is stored locally by default
- 🚫 No third-party account or cloud service required
- 🤖 Local MCP tool for agents to read WeChat article URLs directly

<p align="center">
  <img src="./docs/images/workflow-demo.jpg"
       alt="WxArticleSaver article export workflow"
       width="100%" />
</p>

## Quick Start

### Method 1: Portable Release (Recommended · No Python Required)

1. Go to **[Latest Releases](https://github.com/shanliuling/WxArticleSaver/releases/latest)** and download the latest `WxArticleSaver-*-Windows-x64.zip`.
2. Extract to any folder and double-click **`WxArticleSaver.exe`**.

---

### Method 2: Run from Source (For Developers)

#### 1. Requirements
- Windows 10 / 11
- Python 3.11 or 3.12

#### 2. Start
After downloading the source code, double-click:

```text
install_and_run.bat
```

On first run, WxArticleSaver automatically installs required dependencies and temporarily trusts a locally generated CA certificate for the **current Windows user**.

---

### macOS Experimental Support (Run from Source)

The macOS implementation is currently a source-run PoC and does not provide a signed or notarized `.app`. It uses a macOS network-service PAC file to route only the WeChat article/media allowlist through local `mitmproxy`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./run_macos.command --service "Wi-Fi"
```

On first launch, import the generated CA into the current user's `Login` Keychain and set it to `Always Trust`. Then fully quit and reopen WeChat for Mac; if the button does not appear, press `⌘R`. Press `Ctrl+C` in the launcher terminal to stop. If the process is interrupted, run `restore_proxy_macos.command`.

See [`docs/macos.md`](./docs/macos.md) for setup, security notes, troubleshooting, and limitations.

## Read articles from an agent

The local MCP server exposes `read_article(url)`. Given an `https://mp.weixin.qq.com/s/...` link, an agent receives the title, author, and Markdown body. It fetches publicly accessible pages directly, does not require opening WeChat or trusting this project's CA, and does not write to the export directory.

The page must be publicly accessible from the current network. Login-gated, restricted, or blocked pages return an error; the tool does not bypass those restrictions. Article text is untrusted content and must not be treated as instructions. The MCP server has a separate dependency list and does not start the desktop proxy.

The MCP server is currently source-only; it is not included in the Windows ZIP or macOS DMG. Clone this repository, then run from its root:

```bash
python3.12 -m venv .venv-agent
.venv-agent/bin/python -m pip install -r requirements-agent.txt
codex mcp add wx-article-saver -- "$PWD/.venv-agent/bin/python" "$PWD/mcp_server.py"
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv-agent
.\.venv-agent\Scripts\python.exe -m pip install -r requirements-agent.txt
codex mcp add wx-article-saver -- "$PWD\.venv-agent\Scripts\python.exe" "$PWD\mcp_server.py"
```

Codex starts this stdio server when needed; do not run `mcp_server.py` in a separate terminal. Remove the connection with:

```bash
codex mcp remove wx-article-saver
```

Start a new Codex session to use `read_article`.

---

### 3. Export an Article (Common Steps)

1. Start WxArticleSaver, then fully quit WeChat and reopen it.
2. Open an Official Account article that you can normally access.
3. Click **"Export Article"** in the bottom-right corner.
4. If the button does not appear, press **Ctrl+R** or use **Right-click → Refresh** on the article page.
5. If the article contains video, play it for a few seconds before exporting.

Exported files are saved to:

```text
exports/
└─ Article Title/
   ├─ article.md
   ├─ article.html
   ├─ article.txt
   ├─ raw_wechat_response.html
   ├─ meta.json
   ├─ images/
   └─ videos/
```

## Why Is a Refresh Sometimes Needed?

WeChat for Windows may restore an already opened article directly from its WebView page cache. In that case, the article's main HTML is not requested again, so WxArticleSaver has no chance to inject the export button.

When it can confirm that WeChat is the foreground window, the program will **try to send Ctrl+R automatically once**. If that does not happen, refresh the page manually.

## Video Notes

Video URLs are often not present in the initial article HTML. It is recommended to play the video for a few seconds first, so the page requests the media resource before exporting.

## Security Design

WxArticleSaver uses a local `mitmproxy` instance to read and modify WeChat article HTTPS responses. On first run, it therefore needs to temporarily trust a **CA generated locally on your own machine** in the current user's certificate store.

## FAQ

### The "Export Article" button does not appear

Press **Ctrl+R** on the current article page, or use **Right-click → Refresh**. This is usually caused by WeChat's WebView page cache.

### Network settings are not restored after exit

Run:

```text
restore_proxy.bat
```

### How do I remove the root certificate installed by WxArticleSaver?

Run:

```text
remove_certificate.bat
```

## Usage Notice & Disclaimer

This project is intended for personal offline archiving, study, and research of content that the user is **legally authorized to access**.

Do not use this project to bypass paywalls, access controls, DRM, or other technical protection measures. Do not use it for unauthorized bulk collection, redistribution of copyrighted content, or other activities that infringe third-party rights. Users are responsible for complying with applicable laws, regulations, and platform rules in their jurisdiction.

This project is provided as-is, without warranties regarding account safety, data integrity, network configuration, or other potential losses. If you do not understand the implications of local HTTPS proxies and root certificates, please read the Security Design section before running the tool.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

If you modify this project and provide its functionality over a network in a way covered by Section 13 of the AGPL, you must provide the corresponding source code to those users as required by the license. See [`LICENSE`](./LICENSE) for the full terms.

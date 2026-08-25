# WxArticleSaver

[中文](./README.md)

> A local-first WeChat Official Account article archiving tool. Open an article that you can **normally access**, click **"Export Article"** in the bottom-right corner, and save the article text, images, and directly accessible media resources to your computer.

**Current platform: Windows 10 / Windows 11**  
**License: GNU AGPL-3.0**

## Features

- 📄 One-click export to Markdown / HTML / TXT
- 🖼️ Automatically save article images
- 🎬 Support directly accessible media resources in articles
- 🔒 All article content is stored locally by default
- 🚫 No third-party account or cloud service required

## Quick Start

### 1. Requirements

- Windows 10 / 11
- Python 3.11 or 3.12

### 2. Start

After downloading the source code, double-click:

```text
install_and_run.bat
```

On first run, WxArticleSaver installs the required Python dependencies and temporarily trusts a locally generated proxy certificate for the **current Windows user**.

### 3. Export an Article

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

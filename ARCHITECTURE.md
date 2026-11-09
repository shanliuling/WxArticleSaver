# Architecture

WxArticleSaver has two local entry points that share article parsing and formatting:

- The desktop flow runs a `mitmproxy` addon. It observes article pages opened in WeChat, injects an export button, and writes Markdown, HTML, text, metadata, and eligible media to the configured export directory.
- `mcp_server.py` exposes the `read_article(url)` tool over MCP stdio. It fetches an accessible `mp.weixin.qq.com/s...` page directly, validates redirects and response size, extracts the article body with the existing parser helpers, and returns structured metadata plus Markdown. It does not save files or reuse WeChat session credentials. Its environment omits mitmproxy; the shared parsing module treats that desktop-only dependency as optional.

Data flow for MCP:

`agent URL → URL/redirect validation → bounded HTTPS request → existing article selectors → Markdown + metadata → MCP stdio response`

The MCP server uses the official Python MCP SDK. The desktop launchers and their proxy/keychain lifecycle remain separate from the MCP server.

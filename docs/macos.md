# macOS 支持

> 直接使用 DMG 的用户请先阅读：[macOS 操作说明](./macos-user-guide.md)。

macOS 版本支持源码运行，也支持构建可双击启动的 `.app` 和 `.dmg` 安装包。它复用现有的文章解析和导出逻辑，通过 macOS 网络服务的 PAC 将微信文章/媒体请求送入本机 mitmproxy。

## 下载 DMG（推荐）

当前项目可在 Apple Silicon Mac 上生成 `WxArticleSaver-macos-arm64.dmg`。由于仓库目前没有 Apple Developer ID 签名证书，发布包是未签名测试包；首次打开时请在 Finder 中右键 `WxArticleSaver.app`，选择“打开”，再确认运行。

DMG 打开后将 `WxArticleSaver.app` 拖到 `Applications`，然后双击启动。应用会自动打开一个 Terminal 窗口，代理运行期间不要关闭该窗口。

## 从源码构建 DMG

仅在 Apple Silicon Mac 上执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python scripts/build-macos.py --skip-install
```

构建产物：

```text
dist/WxArticleSaver-macos-arm64.dmg
dist/WxArticleSaver-macos-arm64.dmg.sha256
```

如果已有 Apple Developer ID，可使用 `--sign-identity "Developer ID Application: ..."` 签名；公开分发前还需要 notarization。

## 环境要求

- macOS；
- Python 3.11 或 3.12；
- 可以正常登录并阅读公众号文章的微信 Mac；
- 当前用户可以修改所选 macOS 网络服务的代理设置；
- `openssl`、`networksetup`、`security` 和 `open`（macOS 系统自带）。

## 安装依赖

建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 启动

### 选择网络服务

先查看网络服务名称：

```bash
networksetup -listallnetworkservices
```

建议显式指定当前使用的服务，避免修改 VPN 或其他不需要代理的服务：

```bash
./run_macos.command --service "Wi-Fi"
```

如果不指定 `--service`，程序会尝试选择当前有 IP 地址的服务。也可以通过环境变量指定多个服务：

```bash
WXAS_NETWORK_SERVICES="Wi-Fi,Ethernet" ./run_macos.command
```

### 信任本机 CA

首次启动时，程序会生成并打印本机 CA 的路径和 SHA-256 指纹，但**不会静默修改 Keychain**。

1. 双击日志中显示的 `.wxas_ca/mitmproxy-ca-cert.cer`；
2. 选择导入到当前用户的 `Login` Keychain；
3. 在 Keychain Access 中双击该证书；
4. 展开 `Trust`；
5. 将 `When using this certificate` 设置为 `Always Trust`；
6. 确认指纹与程序输出一致。

只应信任本工具当前生成的 CA。不要把该 CA 或私钥分享给其他人。

### 导出文章

1. 保持 `run_macos.command` 对应的终端窗口运行；
2. 完全退出微信 Mac，然后重新打开；
3. 打开可以正常阅读的公众号文章；
4. 如果没有出现“导出本文”，手动按 `⌘R`；
5. 点击文章页面右下角的“导出本文”；
6. 导出文件会写入项目目录下的 `exports/`。

首版不申请 Accessibility 权限，也不会自动模拟 `⌘R`。

## 停止和恢复

回到启动窗口按 `Ctrl+C`，等待看到代理恢复日志后再关闭窗口。

如果发生强制退出、终端关闭或网络状态异常，可以执行：

```bash
./restore_proxy_macos.command
```

证书不会随主程序自动删除。确认不再使用后执行：

```bash
./remove_certificate_macos.command
```

该命令只尝试按本工具证书的指纹删除 Login Keychain 中的对应证书。

## 日志和状态文件

```text
run_macos.log
proxy_backup_macos.json
.wxas_ca/
exports/
```

`proxy_backup_macos.json` 用于异常退出后的代理恢复。不要手工删除它，除非已经确认系统代理恢复正常。

## 当前限制

- 默认构建的是未签名 arm64 `.app`，尚未 notarization；
- 尚未验证所有微信 Mac 版本；
- 需要用户手动信任 CA；
- 需要用户手动按 `⌘R`；
- 视频能力与 Windows 版本相同，仍受文章实际请求、未加密媒体和 DRM 限制；
- 如果微信 Mac 不读取系统 PAC 或不接受该 CA，当前方案无法完成拦截，需要另行评估 per-app interception / Network Extension。

## 验证记录

提交 PR 前请补充实际测试环境：

| 项目 | 值 |
| --- | --- |
| macOS 版本 | 待填写 |
| CPU 架构 | 待填写 |
| 微信 Mac 版本 | 待填写 |
| Python 版本 | 待填写 |
| 文章请求是否到达 `127.0.0.1:8899` | 待验证 |
| 含图片文章是否成功导出 | 待验证 |
| 退出后代理是否恢复 | 待验证 |

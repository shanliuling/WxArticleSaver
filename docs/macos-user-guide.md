# WxArticleSaver macOS 操作说明

本文面向直接下载并使用 macOS `.dmg` 安装包的用户。当前安装包适用于 Apple Silicon（`arm64`）Mac，包括 M1、M2、M3 和 M4 系列。

## 一、安装应用

1. 双击 `WxArticleSaver-macos-arm64.dmg`。
2. 将 `WxArticleSaver.app` 拖入 `Applications` 文件夹。
3. 第一次启动时，如果 macOS 提示“无法验证开发者”，在 Finder 中右键该 App，选择“打开”，然后再次确认。
4. 启动 App 后会自动打开一个 Terminal 窗口。代理运行期间不要关闭这个窗口。

如果电脑中已经安装旧版 WxArticleSaver，请确认新 App 已经替换旧版本。可以在终端检查实际启动文件：

```bash
exec '/Applications/WxArticleSaver.app/Contents/Resources/wxas-runner' --mitmdump --version
```

正常输出应包含 `Mitmproxy: 12.2.3 binary`。

## 二、首次启动和信任 CA

WxArticleSaver 使用本机 `mitmproxy` 读取和修改微信文章 HTTPS 响应，因此首次使用需要信任程序生成的本机 CA 证书。

程序启动后会在 Terminal 中打印证书路径和 SHA-256 指纹。证书通常位于：

```text
~/Library/Application Support/WxArticleSaver/.wxas_ca/mitmproxy-ca-cert.cer
```

也可以直接打开证书：

```bash
open "$HOME/Library/Application Support/WxArticleSaver/.wxas_ca/mitmproxy-ca-cert.cer"
```

在 Keychain Access 中完成以下操作：

1. 选择当前用户的 `Login` Keychain；
2. 导入上面的 `.cer` 证书；
3. 双击刚导入的证书；
4. 展开 `Trust`；
5. 将 `When using this certificate` 设置为 `Always Trust`；
6. 输入当前 Mac 用户密码确认；
7. 核对证书指纹必须与程序 Terminal 中打印的 SHA-256 指纹一致。

**不要信任来源不明的 CA，也不要把本工具的 CA 或私钥分享给其他人。**

当前版本不会静默修改 Login Keychain，这是因为根证书信任会影响 HTTPS 安全边界。PAC 配置、代理启动和退出恢复可以自动完成，但证书信任需要用户明确确认。

## 三、导出微信文章

1. 保持 WxArticleSaver 的 Terminal 窗口运行；
2. 完全退出微信 Mac；
3. 重新打开微信 Mac；
4. 打开可以正常阅读的公众号文章；
5. 如果页面没有显示“导出本文”，在文章页面按 `⌘R`；
6. 点击文章页面中的“导出本文”。

当前首版不申请 Accessibility 权限，因此不会自动向微信发送 `⌘R`。这样可以避免程序操作其他前台应用或影响用户未保存的内容。

打包版导出目录为：

```text
~/Library/Application Support/WxArticleSaver/exports/
```

打开导出目录：

```bash
open "$HOME/Library/Application Support/WxArticleSaver/exports"
```

## 四、停止程序和恢复代理

停止时回到 WxArticleSaver 的 Terminal 窗口，按：

```text
Ctrl+C
```

等待看到下面的恢复日志后再关闭 Terminal：

```text
[恢复] macOS 系统代理已恢复。
[恢复] PAC 服务已停止。
```

如果 Terminal 被强制关闭，双击 App 内置的恢复命令：

```text
/Applications/WxArticleSaver.app/Contents/Resources/恢复代理.command
```

也可以在终端执行：

```bash
open '/Applications/WxArticleSaver.app/Contents/Resources/恢复代理.command'
```

如果网络仍然异常，先查看网络服务名称：

```bash
networksetup -listallnetworkservices
```

然后关闭对应服务的 PAC：

```bash
sudo networksetup -setautoproxystate "Wi-Fi" off
networksetup -getautoproxyurl "Wi-Fi"
```

确认输出包含：

```text
Enabled: No
```

如果实际网络服务名称不是 `Wi-Fi`，请将命令中的名称替换为实际名称。

## 五、清理 CA 证书

确认不再使用 WxArticleSaver 后，可以双击：

```text
/Applications/WxArticleSaver.app/Contents/Resources/清理证书.command
```

或者执行：

```bash
open '/Applications/WxArticleSaver.app/Contents/Resources/清理证书.command'
```

该命令只会根据本工具当前 CA 的指纹尝试删除对应的 Login Keychain 证书，不会批量删除其他证书。

## 六、常见问题

### 1. 出现 `unrecognized arguments: -c`

这是旧版 DMG 的 runner 启动方式错误。请重新下载并安装包含修复的新版 DMG，不要只重启旧版 App。

### 2. 出现 `ModuleNotFoundError: No module named 'bs4'`

这是旧版 DMG 漏打包文章 addon 依赖。请重新安装新版 DMG。新版已经将 `bs4`、`markdownify`、`requests` 等依赖打包到 runner 中。

### 3. 程序启动后立即退出

先检查 Terminal 中最后几行日志：

- 如果显示代理已恢复，说明程序检测到错误后完成了清理；
- 如果显示证书、网络服务或权限错误，请按日志提示处理；
- 如果微信没有显示按钮，确认已经完全退出并重新打开微信，再手动按 `⌘R`。

### 4. 浏览器或其他 App 网络异常

WxArticleSaver 只通过 PAC 将微信文章和媒体域名送入本地代理，正常情况下其他域名会走 `DIRECT`。如果仍然异常，停止程序或执行“恢复代理”命令，并确认：

```bash
networksetup -getautoproxyurl "Wi-Fi"
```

输出中的 `Enabled` 为 `No`。

## 七、当前限制

- 当前 DMG 仅支持 Apple Silicon（`arm64`）；
- 安装包未使用 Developer ID 签名，也未 notarization；
- 首次使用需要用户手动信任 CA；
- 首版需要用户手动重启微信和按 `⌘R`；
- 只处理用户合法有权访问的内容，不绕过付费、权限、DRM 或其他技术保护措施；
- 视频导出仍受文章实际请求、未加密媒体和 DRM 限制。

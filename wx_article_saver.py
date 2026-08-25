# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
WxArticleSaver v1.0.0

Manual article export + best-effort video download.

Rules:
- Opening an article does NOT write an export folder.
- The article HTML and discovered media URLs live only in memory.
- Clicking "导出本文" creates the export folder and downloads article assets.
- Direct non-DRM video and unencrypted HLS are supported.
- Encrypted HLS/DRM is not bypassed; a link is preserved instead.
- Cookies/Authorization/pass_ticket are never persisted or reused for media download.
"""

import json
import os
import re
import time
import ctypes
import threading
import hashlib
import html as html_lib
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from mitmproxy import http, ctx

HOST = "mp.weixin.qq.com"
SAVE_PATH = "/__wxas_save__"
EXPORT_ROOT = Path(os.environ.get("WXAS_EXPORT_DIR", "exports")).resolve()

MEDIA_HOSTS = {
    "findermp.video.qq.com",
    "mpvideo.qpic.cn",
}
MEDIA_HOST_SUFFIXES = (
    ".video.qq.com",
    ".vod.tencent-cloud.com",
)

# token -> {url, html, created, media: [{url, content_type, headers, captured_at}]}
ARTICLE_CACHE = {}
CURRENT_ARTICLE_TOKEN = ""
CACHE_TTL = 30 * 60
MAX_VIDEO_BYTES = 1024 * 1024 * 1024  # 1 GiB/video safety cap
MAX_VIDEOS_PER_EXPORT = 12

# -------------------- cached WebView auto-refresh --------------------
# WeChat PC may restore an article from its own WebView/page cache.  In that
# case there is no new GET /s request for mitmproxy to modify, so the export
# button cannot be injected.  We detect article-owned follow-up requests whose
# Referer is an article URL, and (only when no recent /s request was seen) send
# one Ctrl+R to the foreground WeChat window.
AUTO_REFRESH_DELAY = 0.85
AUTO_REFRESH_COOLDOWN = 15.0
RECENT_DOC_GRACE = 2.0
REFRESH_STATE_TTL = 10 * 60

_REFRESH_LOCK = threading.Lock()
_ARTICLE_DOC_SEEN = {}       # article_key -> monotonic timestamp
_AUTO_REFRESH_PENDING = set()
_AUTO_REFRESH_ATTEMPTED = {} # article_key -> monotonic timestamp
_LAST_ARTICLE_DOC_AT = 0.0


def article_key_from_url(url: str) -> str:
    """Return a stable-ish key for a WeChat article URL, or empty string."""
    try:
        p = urlparse(url or "")
        if (p.hostname or "").lower() != HOST:
            return ""
        path = (p.path or "").rstrip("/")
        if not (path == "/s" or path.startswith("/s/")):
            return ""
        if path.startswith("/s/"):
            return f"{HOST}{path}"

        q = parse_qs(p.query)
        core = []
        for name in ("__biz", "mid", "appmsgid", "idx", "sn"):
            values = q.get(name)
            if values and values[0]:
                core.append(f"{name}={values[0]}")
        if core:
            return f"{HOST}/s?" + "&".join(core)
        return (url or "").split("#", 1)[0]
    except Exception:
        return ""


def _prune_refresh_state(now=None):
    now = time.monotonic() if now is None else now
    for mapping in (_ARTICLE_DOC_SEEN, _AUTO_REFRESH_ATTEMPTED):
        dead = [k for k, t in mapping.items() if now - t > REFRESH_STATE_TTL]
        for k in dead:
            mapping.pop(k, None)


def mark_article_document_seen(url: str):
    global _LAST_ARTICLE_DOC_AT
    key = article_key_from_url(url)
    now = time.monotonic()
    with _REFRESH_LOCK:
        _prune_refresh_state(now)
        _LAST_ARTICLE_DOC_AT = now
        if key:
            _ARTICLE_DOC_SEEN[key] = now
            _AUTO_REFRESH_PENDING.discard(key)
    return key


def _foreground_wechat_exe():
    """Return foreground WeChat executable name on Windows, otherwise ''."""
    if os.name != "nt":
        return ""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""

        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(2048)
            size = ctypes.c_ulong(len(buf))
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            if not ok:
                return ""
            return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def _send_ctrl_r_to_foreground_wechat():
    """Best-effort one-shot Ctrl+R; never sends keys to another foreground app."""
    exe = _foreground_wechat_exe()
    if not exe or ("wechat" not in exe and "weixin" not in exe):
        return False, exe
    try:
        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_R = 0x52
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_R, 0, 0, 0)
        user32.keybd_event(VK_R, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        return True, exe
    except Exception:
        return False, exe


def _auto_refresh_worker(key: str, referer: str, scheduled_at: float):
    global _LAST_ARTICLE_DOC_AT
    now = time.monotonic()
    with _REFRESH_LOCK:
        _AUTO_REFRESH_PENDING.discard(key)
        _prune_refresh_state(now)

        # A real article document request arrived while the timer was waiting:
        # the page is not cache-only, so do nothing.
        seen_at = _ARTICLE_DOC_SEEN.get(key, 0.0)
        if seen_at >= scheduled_at or now - _LAST_ARTICLE_DOC_AT < RECENT_DOC_GRACE:
            return

        last_attempt = _AUTO_REFRESH_ATTEMPTED.get(key, 0.0)
        if now - last_attempt < AUTO_REFRESH_COOLDOWN:
            return
        # Mark before sending so bursts of jsmonitor requests cannot create a
        # refresh loop even if sending the key fails.
        _AUTO_REFRESH_ATTEMPTED[key] = now

    ok, exe = _send_ctrl_r_to_foreground_wechat()
    if ok:
        print(
            f"[WxArticleSaver] 检测到文章从 WebView 缓存恢复，已自动 Ctrl+R 一次: "
            f"exe={exe} | {referer[:160]}",
            flush=True,
        )
    else:
        detail = f"前台={exe}" if exe else "无法确认前台微信窗口"
        print(
            f"[WxArticleSaver] 检测到文章可能来自 WebView 缓存，但未自动刷新（{detail}）。"
            f"如果没有导出按钮，请手动 Ctrl+R。",
            flush=True,
        )


def maybe_schedule_cached_article_refresh(flow: http.HTTPFlow):
    """Schedule one safe refresh when an article page is active only from cache."""
    if os.name != "nt":
        return

    path = urlparse(flow.request.pretty_url).path
    if path == SAVE_PATH or path == "/s" or path.startswith("/s/"):
        return

    referer = flow.request.headers.get("referer") or ""
    key = article_key_from_url(referer)
    if not key:
        return

    now = time.monotonic()
    with _REFRESH_LOCK:
        _prune_refresh_state(now)
        if now - _LAST_ARTICLE_DOC_AT < RECENT_DOC_GRACE:
            return
        if now - _ARTICLE_DOC_SEEN.get(key, 0.0) < REFRESH_STATE_TTL:
            return
        if key in _AUTO_REFRESH_PENDING:
            return
        if now - _AUTO_REFRESH_ATTEMPTED.get(key, 0.0) < AUTO_REFRESH_COOLDOWN:
            return
        _AUTO_REFRESH_PENDING.add(key)

    timer = threading.Timer(
        AUTO_REFRESH_DELAY,
        _auto_refresh_worker,
        args=(key, referer, now),
    )
    timer.daemon = True
    timer.start()


def safe_name(name: str, max_len=90) -> str:
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "_", name or "微信文章")
    name = re.sub(r"\s+", " ", name).strip(" ._")
    return (name or "微信文章")[:max_len]


def text_of(soup, selector):
    el = soup.select_one(selector)
    if not el:
        return ""
    return el.get_text(" ", strip=True)


def detect_title(soup):
    title = text_of(soup, "#activity-name")
    if title:
        return title
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        return og.get("content").strip()
    if soup.title:
        return soup.title.get_text(" ", strip=True)
    return "微信文章"


def detect_author(soup):
    for selector in ("#js_name", ".rich_media_meta_nickname", ".account_nickname_inner"):
        t = text_of(soup, selector)
        if t:
            return t
    return ""


def allowed_image_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        host = (p.hostname or "").lower()
        return (
            host.endswith(".qpic.cn")
            or host.endswith(".qq.com")
            or host.endswith(".weixin.qq.com")
            or host.endswith(".weixin.com")
            or host.endswith(".wechat.com")
        )
    except Exception:
        return False


def ext_from_response(url, content_type):
    ct = (content_type or "").split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    if ct in mapping:
        return mapping[ct]
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def _normalize_url(value, base_url):
    if not value:
        return ""
    value = str(value).strip()
    if not value or value.startswith(("javascript:", "data:")):
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("/"):
        return urljoin(base_url, value)
    return ""


def _first_video_url(tag, article_url):
    attrs = (
        "src", "data-src", "data-url", "data-link",
        "data-video-url", "data-video-src", "data-videourl",
        "data-origin-url", "data-player-url", "data-play-url",
    )
    nodes = [tag] + list(tag.find_all(True))
    candidates = []
    for node in nodes:
        for key in attrs:
            u = _normalize_url(node.get(key), article_url)
            if u:
                candidates.append(u)
    for u in candidates:
        low = u.lower()
        if any(x in low for x in (
            "video", "videoplayer", "findermp", "mpvideo",
            ".mp4", ".m3u8", "v.qq.com", "channels",
        )):
            return u
    return candidates[0] if candidates else ""


def _first_video_poster(tag, article_url):
    attrs = (
        "poster", "data-poster", "data-cover", "data-cover-url",
        "data-thumb", "data-thumb-url", "data-img", "data-img-url",
    )
    nodes = [tag] + list(tag.find_all(True))
    for node in nodes:
        for key in attrs:
            u = _normalize_url(node.get(key), article_url)
            if u:
                return u
    img = tag.find("img")
    if img:
        for key in ("data-src", "data-original", "src"):
            u = _normalize_url(img.get(key), article_url)
            if u:
                return u
    return ""


def replace_video_embeds(article, article_url):
    """Replace WeChat video widgets with portable placeholders."""
    candidates = []
    for tag in article.find_all(True):
        name = (tag.name or "").lower()
        cls = " ".join(tag.get("class", [])).lower()
        ident = str(tag.get("id") or "").lower()
        attrs = {str(k).lower() for k in tag.attrs.keys()}
        explicit = name in {
            "video", "iframe", "embed", "mp-common-videosnap",
            "mp-video", "mpvideosnap", "txpdiv",
        }
        videoish = (
            "video" in cls
            or "video" in ident
            or "videosnap" in cls
            or "data-mpvid" in attrs
            or "data-vid" in attrs
            or "data-video-url" in attrs
            or "data-video-src" in attrs
        )
        if explicit or videoish:
            candidates.append(tag)

    ids = {id(x) for x in candidates}
    outermost = []
    for tag in candidates:
        parent = tag.parent
        nested = False
        while parent is not None:
            if id(parent) in ids:
                nested = True
                break
            parent = getattr(parent, "parent", None)
        if not nested:
            outermost.append(tag)

    videos = []
    for idx, tag in enumerate(outermost, 1):
        direct_url = _first_video_url(tag, article_url)
        poster = _first_video_poster(tag, article_url)
        internal_id = tag.get("data-mpvid") or tag.get("data-vid") or tag.get("data-id") or ""
        link = direct_url or article_url
        label = "打开视频" if direct_url else "在微信原文中查看视频"
        poster_html = ""
        if poster:
            poster_html = (
                f'<p><img src="{html_lib.escape(poster, quote=True)}" '
                f'alt="视频封面 {idx}"></p>'
            )
        block = f"""
<div class="wxas-video-placeholder" data-wxas-video="{idx}">
  {poster_html}
  <p>🎬 <strong>视频 {idx}</strong></p>
  <p><a href="{html_lib.escape(link, quote=True)}">{label}</a></p>
</div>
"""
        repl = BeautifulSoup(block, "html.parser").div
        tag.replace_with(repl)
        videos.append({
            "index": idx,
            "url": direct_url,
            "fallback_url": article_url,
            "poster": poster,
            "internal_id": str(internal_id),
        })
    return videos


def normalize_article(article):
    for el in article.select(
        "script, style, #wxas-save-btn, #wxas-sink, #wxas-video-hint"
    ):
        el.decompose()
    for img in article.find_all("img"):
        src = img.get("data-src") or img.get("data-original") or img.get("data-backsrc") or img.get("src")
        if src:
            img["src"] = src
        for k in ("data-src", "data-original", "data-backsrc", "data-ratio", "data-w"):
            img.attrs.pop(k, None)
    return article


def download_images(article, folder, referer):
    images_dir = folder / "images"
    images_dir.mkdir(exist_ok=True)
    seen = {}
    count = 0
    for img in article.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        src = urljoin(referer, src)
        if not allowed_image_url(src):
            continue
        if src in seen:
            img["src"] = seen[src]
            continue
        try:
            r = requests.get(
                src,
                timeout=12,
                headers={"User-Agent": "Mozilla/5.0", "Referer": referer or f"https://{HOST}/"},
            )
            if r.status_code != 200 or not r.content:
                continue
            if len(r.content) > 25 * 1024 * 1024:
                continue
            count += 1
            digest = hashlib.sha1(src.encode("utf-8", "ignore")).hexdigest()[:8]
            ext = ext_from_response(src, r.headers.get("Content-Type", ""))
            filename = f"{count:03d}-{digest}{ext}"
            (images_dir / filename).write_bytes(r.content)
            rel = f"images/{filename}"
            img["src"] = rel
            seen[src] = rel
        except Exception as e:
            ctx.log.warn(f"[WxArticleSaver] 图片下载失败: {src[:100]} - {e}")
    if count == 0:
        try:
            images_dir.rmdir()
        except Exception:
            pass
    return count


# -------------------- video capture/download --------------------

def is_media_host(host: str) -> bool:
    host = (host or "").lower()
    return host in MEDIA_HOSTS or any(host.endswith(s) for s in MEDIA_HOST_SUFFIXES)


def looks_like_media_url(url: str) -> bool:
    low = (url or "").lower()
    path = urlparse(url or "").path.lower()
    return (
        path.endswith((".mp4", ".m4v", ".mov", ".webm", ".m3u8", ".ts", ".m4s"))
        or ".m3u8?" in low
        or ".mp4?" in low
        or "videoplay" in low
        or "video" in (urlparse(url or "").hostname or "").lower()
    )


def is_video_content_type(content_type: str) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    return ct.startswith("video/") or ct in {
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "audio/mpegurl",
        "audio/x-mpegurl",
    }


def safe_media_request_headers(flow: http.HTTPFlow):
    # Do not keep Cookie/Authorization/pass_ticket/etc.
    keep = ("user-agent", "referer", "origin", "accept", "accept-language")
    result = {}
    for name in keep:
        value = flow.request.headers.get(name)
        if value:
            result[name.title()] = value
    return result


def remember_media_for_current_article(flow: http.HTTPFlow):
    global CURRENT_ARTICLE_TOKEN
    if not CURRENT_ARTICLE_TOKEN:
        return
    item = ARTICLE_CACHE.get(CURRENT_ARTICLE_TOKEN)
    if not item:
        return

    url = flow.request.pretty_url
    ctype = (flow.response.headers.get("content-type") or "") if flow.response else ""
    if not (is_video_content_type(ctype) or looks_like_media_url(url)):
        return
    if flow.response and int(flow.response.status_code or 0) >= 400:
        return

    media = item.setdefault("media", [])
    canonical = url.split("#", 1)[0]
    if any(x.get("url") == canonical for x in media):
        return

    media.append({
        "url": canonical,
        "content_type": ctype,
        "headers": safe_media_request_headers(flow),
        "captured_at": time.time(),
    })
    ctx.log.info(f"[WxArticleSaver] 已捕获视频媒体地址，等待手动导出: {canonical[:180]}")


def response_extension(url: str, content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    mapping = {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
        "video/x-m4v": ".m4v",
        "video/mp2t": ".ts",
    }
    if ct in mapping:
        return mapping[ct]
    path = urlparse(url).path.lower()
    for ext in (".mp4", ".webm", ".mov", ".m4v", ".ts", ".m4s"):
        if path.endswith(ext):
            return ext
    return ".mp4"


def parse_hls_master(text: str, base_url: str):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    variants = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        bandwidth = 0
        m = re.search(r"BANDWIDTH=(\d+)", line, re.I)
        if m:
            bandwidth = int(m.group(1))
        j = i + 1
        while j < len(lines) and lines[j].startswith("#"):
            j += 1
        if j < len(lines):
            variants.append((bandwidth, urljoin(base_url, lines[j])))
    if not variants:
        return ""
    variants.sort(key=lambda x: x[0], reverse=True)
    return variants[0][1]


def hls_is_encrypted(text: str) -> bool:
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("#EXT-X-KEY:"):
            continue
        m = re.search(r"METHOD=([^,]+)", line, re.I)
        method = m.group(1).strip().upper() if m else ""
        if method and method != "NONE":
            return True
    return False


def download_hls_video(url, headers, videos_dir: Path, index: int):
    """Download unencrypted HLS only. Encrypted/DRM HLS is skipped."""
    try:
        r = requests.get(url, headers=headers or {}, timeout=30, allow_redirects=True)
    except Exception as e:
        return {"ok": False, "url": url, "reason": f"HLS 请求失败: {e}"}
    if r.status_code != 200:
        return {"ok": False, "url": url, "reason": f"HLS HTTP {r.status_code}"}

    playlist = r.text
    base_url = r.url or url
    variant = parse_hls_master(playlist, base_url)
    if variant:
        try:
            r2 = requests.get(variant, headers=headers or {}, timeout=30, allow_redirects=True)
        except Exception as e:
            return {"ok": False, "url": url, "reason": f"HLS 子清单请求失败: {e}"}
        if r2.status_code != 200:
            return {"ok": False, "url": url, "reason": f"HLS 子清单 HTTP {r2.status_code}"}
        playlist = r2.text
        base_url = r2.url or variant

    if hls_is_encrypted(playlist):
        return {
            "ok": False,
            "url": url,
            "reason": "检测到加密 HLS（EXT-X-KEY），未尝试解密",
            "encrypted": True,
        }

    lines = [x.strip() for x in playlist.splitlines() if x.strip()]
    segments = []
    init_segment = ""
    for line in lines:
        if line.startswith("#EXT-X-MAP:"):
            m = re.search(r'URI="([^"]+)"', line, re.I)
            if m:
                init_segment = urljoin(base_url, m.group(1))
        elif line.startswith("#EXT-X-BYTERANGE"):
            return {"ok": False, "url": url, "reason": "HLS 使用 BYTERANGE，当前版本仅保留链接"}
        elif not line.startswith("#"):
            segments.append(urljoin(base_url, line))

    if not segments:
        return {"ok": False, "url": url, "reason": "HLS 未找到媒体分片"}

    ext = ".mp4" if init_segment or any(".m4s" in x.lower() for x in segments) else ".ts"
    filename = f"video-{index:03d}{ext}"
    out = videos_dir / filename
    total = 0
    targets = ([init_segment] if init_segment else []) + segments

    try:
        with out.open("wb") as f:
            for seg_url in targets:
                sr = requests.get(seg_url, headers=headers or {}, timeout=45, stream=True, allow_redirects=True)
                if sr.status_code not in (200, 206):
                    raise RuntimeError(f"分片 HTTP {sr.status_code}")
                for chunk in sr.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_VIDEO_BYTES:
                        raise RuntimeError("视频超过 1 GiB 安全上限")
                    f.write(chunk)
                sr.close()
    except Exception as e:
        out.unlink(missing_ok=True)
        return {"ok": False, "url": url, "reason": f"HLS 下载失败: {e}"}

    if total < 1024:
        out.unlink(missing_ok=True)
        return {"ok": False, "url": url, "reason": "HLS 输出过小"}

    return {
        "ok": True,
        "url": url,
        "final_url": base_url,
        "local": f"videos/{filename}",
        "bytes": total,
        "content_type": "application/vnd.apple.mpegurl",
        "kind": "hls",
    }


def download_direct_video(url, headers, videos_dir: Path, index: int):
    try:
        r = requests.get(url, headers=headers or {}, timeout=60, stream=True, allow_redirects=True)
    except Exception as e:
        return {"ok": False, "url": url, "reason": f"请求失败: {e}"}

    try:
        if r.status_code not in (200, 206):
            return {"ok": False, "url": url, "reason": f"HTTP {r.status_code}"}

        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        final_url = r.url or url
        if "mpegurl" in ct or urlparse(final_url).path.lower().endswith(".m3u8"):
            r.close()
            return download_hls_video(final_url, headers, videos_dir, index)

        if not (
            ct.startswith("video/")
            or urlparse(final_url).path.lower().endswith((".mp4", ".webm", ".mov", ".m4v", ".ts", ".m4s"))
        ):
            return {"ok": False, "url": url, "reason": f"不是可直接下载的视频响应: {ct or 'unknown'}"}

        length = r.headers.get("Content-Length")
        if length:
            try:
                if int(length) > MAX_VIDEO_BYTES:
                    return {"ok": False, "url": url, "reason": "视频超过 1 GiB 安全上限"}
            except Exception:
                pass

        ext = response_extension(final_url, ct)
        filename = f"video-{index:03d}{ext}"
        out = videos_dir / filename
        total = 0
        with out.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    out.unlink(missing_ok=True)
                    return {"ok": False, "url": url, "reason": "视频超过 1 GiB 安全上限"}
                f.write(chunk)

        if total < 1024:
            out.unlink(missing_ok=True)
            return {"ok": False, "url": url, "reason": "视频响应过小"}

        return {
            "ok": True,
            "url": url,
            "final_url": final_url,
            "local": f"videos/{filename}",
            "bytes": total,
            "content_type": ct,
            "kind": "direct",
        }
    finally:
        try:
            r.close()
        except Exception:
            pass


def collect_video_candidates(embed_videos, captured_media):
    result = []
    seen = set()

    def add(url, headers=None, source=""):
        if not url:
            return
        canonical = url.split("#", 1)[0]
        if canonical in seen:
            return
        seen.add(canonical)
        result.append({"url": canonical, "headers": dict(headers or {}), "source": source})

    # Captured playback URLs first: they are usually actual signed media URLs.
    for m in captured_media or []:
        add(m.get("url"), m.get("headers"), "captured")

    # Article DOM may already expose MP4/m3u8 directly.
    for v in embed_videos or []:
        u = v.get("url") or ""
        if looks_like_media_url(u):
            add(u, {"Referer": v.get("fallback_url") or ""}, "article")

    return result[:MAX_VIDEOS_PER_EXPORT]


def download_videos(embed_videos, captured_media, folder: Path, article_url: str):
    candidates = collect_video_candidates(embed_videos, captured_media)
    if not candidates:
        return []

    videos_dir = folder / "videos"
    videos_dir.mkdir(exist_ok=True)
    results = []
    next_index = 1

    for item in candidates:
        url = item["url"]
        headers = dict(item.get("headers") or {})
        headers.setdefault("Referer", article_url)
        low_path = urlparse(url).path.lower()
        if low_path.endswith(".m3u8") or ".m3u8?" in url.lower():
            result = download_hls_video(url, headers, videos_dir, next_index)
        else:
            result = download_direct_video(url, headers, videos_dir, next_index)
        result["source"] = item.get("source")
        results.append(result)
        if result.get("ok"):
            next_index += 1

    if not any(x.get("ok") for x in results):
        try:
            videos_dir.rmdir()
        except Exception:
            pass
    return results


def apply_downloaded_video_links(article, download_results):
    downloaded = [x for x in download_results if x.get("ok") and x.get("local")]
    placeholders = article.select(".wxas-video-placeholder")

    for idx, item in enumerate(downloaded):
        if idx >= len(placeholders):
            break
        block = placeholders[idx]
        a = block.find("a")
        if a:
            a["href"] = item["local"]
            a.string = "打开本地视频"
        p = BeautifulSoup(
            f'<p class="wxas-video-local">✅ 已下载：'
            f'<a href="{html_lib.escape(item["local"], quote=True)}">'
            f'{html_lib.escape(Path(item["local"]).name)}</a></p>',
            "html.parser",
        ).p
        block.append(p)

    if len(downloaded) > len(placeholders):
        section = BeautifulSoup('<div class="wxas-video-downloads"><h3>本地视频</h3></div>', "html.parser").div
        for item in downloaded[len(placeholders):]:
            p = BeautifulSoup(
                f'<p>🎬 <a href="{html_lib.escape(item["local"], quote=True)}">'
                f'{html_lib.escape(Path(item["local"]).name)}</a></p>',
                "html.parser",
            ).p
            section.append(p)
        article.append(section)


def find_article_content(soup):
    """Find the rendered article body using stable selectors first, then conservative fallbacks."""
    selectors = (
        "#js_content",
        ".rich_media_content",
        "article",
        ".rich_media_area_primary_inner",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        text_len = len(node.get_text(" ", strip=True))
        image_count = len(node.find_all("img"))
        # Some WeChat posts are image-heavy, so do not require lots of text.
        if text_len >= 20 or image_count > 0:
            return node, selector
    return None, ""


def save_article(url: str, html: str, captured_media=None):
    soup = BeautifulSoup(html, "html.parser")
    title = detect_title(soup)
    author = detect_author(soup)
    article, article_selector = find_article_content(soup)
    if article is None:
        raise ValueError("暂时无法识别当前文章正文，请刷新文章后重试")
    ctx.log.info(
        f"[WxArticleSaver] 正文解析成功: selector={article_selector} | "
        f"text={len(article.get_text(' ', strip=True))} | images={len(article.find_all('img'))}"
    )

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    folder = EXPORT_ROOT / f"{timestamp}_{safe_name(title)}"
    base = folder
    n = 1
    while folder.exists():
        n += 1
        folder = Path(str(base) + f"_{n}")
    folder.mkdir(parents=True)

    (folder / "raw_wechat_response.html").write_text(html, encoding="utf-8")
    article_copy = BeautifulSoup(str(article), "html.parser")

    videos = replace_video_embeds(article_copy, url)
    video_downloads = download_videos(videos, captured_media or [], folder, url)
    apply_downloaded_video_links(article_copy, video_downloads)

    article_copy = normalize_article(article_copy)
    visible_text = article_copy.get_text("\n", strip=True)
    (folder / "article.txt").write_text(visible_text + "\n", encoding="utf-8")

    image_count = download_images(article_copy, folder, url)
    markdown_body = md(str(article_copy), heading_style="ATX", bullets="-", strip=["script", "style"]).strip()

    header = f"# {title}\n\n"
    if author:
        header += f"- 作者：{author}\n"
    header += f"- 原文：{url}\n"
    header += f"- 导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"
    (folder / "article.md").write_text(header + markdown_body + "\n", encoding="utf-8")

    title_html = html_lib.escape(title)
    author_html = html_lib.escape(author)
    url_html = html_lib.escape(url)
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title_html}</title>
<style>
body{{max-width:860px;margin:40px auto;padding:0 22px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.75;color:#222}}
img{{max-width:100%;height:auto}}
pre{{overflow:auto;background:#f6f8fa;padding:14px;border-radius:8px}}
code{{font-family:Consolas,Monaco,monospace}}
blockquote{{border-left:4px solid #ddd;margin-left:0;padding-left:14px;color:#666}}
.wxas-video-placeholder{{border:1px solid #e5e7eb;border-radius:10px;padding:14px;margin:18px 0;background:#fafafa}}
.wxas-video-placeholder img{{max-width:100%;border-radius:8px}}
.wxas-video-local{{color:#16803c}}
.wxas-video-downloads{{border-top:1px solid #eee;margin-top:26px;padding-top:12px}}
.meta{{color:#777;font-size:14px;margin-bottom:28px}}
</style>
</head>
<body>
<h1>{title_html}</h1>
<div class="meta">{("作者：" + author_html + "<br>") if author else ""}原文：{url_html}</div>
{str(article_copy)}
</body></html>"""
    (folder / "article.html").write_text(doc, encoding="utf-8")

    meta = {
        "title": title,
        "author": author,
        "url": url,
        "html_bytes": len(html.encode("utf-8", "ignore")),
        "text_chars": len(visible_text),
        "markdown_chars": len(markdown_body),
        "images_downloaded": image_count,
        "videos_found": len(videos),
        "videos": videos,
        "captured_media_count": len(captured_media or []),
        "video_downloads": video_downloads,
        "videos_downloaded": sum(1 for x in video_downloads if x.get("ok")),
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "manual",
    }
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    downloaded_count = sum(1 for x in video_downloads if x.get("ok"))
    ctx.log.info(
        f"[WxArticleSaver] 手动导出成功: {title} | text={len(visible_text)} chars | "
        f"images={image_count} | videos={len(videos)} | downloaded={downloaded_count} | {folder}"
    )
    return folder, title, downloaded_count


def cleanup_cache():
    global CURRENT_ARTICLE_TOKEN
    now = time.time()
    dead = [token for token, item in ARTICLE_CACHE.items() if now - item.get("created", now) > CACHE_TTL]
    for token in dead:
        ARTICLE_CACHE.pop(token, None)
        if CURRENT_ARTICLE_TOKEN == token:
            CURRENT_ARTICLE_TOKEN = ""


def make_token(url, html):
    raw = f"{url}\n{len(html)}\n{time.time_ns()}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()[:24]


def button_markup(token):
    endpoint = f"https://{HOST}{SAVE_PATH}?id={token}"
    return f"""
<button id="wxas-save-btn" type="button"
 onclick="window.__wxasExport && window.__wxasExport(this);"
 style="position:fixed;right:20px;bottom:76px;z-index:2147483647;border:0;border-radius:999px;padding:11px 18px;background:#07c160;color:white;font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.18);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
 导出本文
</button>
<div id="wxas-video-hint" style="position:fixed;right:20px;bottom:42px;z-index:2147483646;color:#8a8a8a;font-size:11px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;">
 有视频时先点播放，再导出
</div>
<script id="wxas-export-script">
(function() {{
  if (window.__wxasExport) return;
  window.__wxasExport = async function(btn) {{
    var oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '正在导出…';
    btn.style.background = '#5f6368';
    try {{
      // Capture the DOM at click time, after WeChat's client-side rendering has finished.
      var renderedHtml = document.documentElement.outerHTML;
      var resp = await fetch('{endpoint}', {{
        method: 'POST',
        headers: {{'Content-Type': 'text/plain;charset=UTF-8'}},
        body: renderedHtml,
        credentials: 'same-origin',
        cache: 'no-store'
      }});
      var msg = await resp.text();
      if (!resp.ok) throw new Error(msg || ('HTTP ' + resp.status));
      btn.textContent = '✓ 已导出';
      btn.style.background = '#19a974';
      setTimeout(function() {{
        btn.disabled = false;
        btn.textContent = oldText.trim() || '导出本文';
        btn.style.background = '#07c160';
      }}, 3000);
    }} catch (e) {{
      btn.disabled = false;
      btn.textContent = '导出失败，重试';
      btn.style.background = '#d93025';
      console.error('[WxArticleSaver] export failed', e);
      setTimeout(function() {{
        btn.textContent = oldText.trim() || '导出本文';
        btn.style.background = '#07c160';
      }}, 4000);
    }}
  }};
}})();
</script>
"""


def is_article_candidate(flow, html):
    """Be permissive when deciding whether to show the export button.

    Parsing is intentionally deferred until the user clicks export, when the fully
    rendered DOM is posted back to the local proxy.
    """
    if (flow.request.pretty_host or "").lower() != HOST:
        return False

    path = urlparse(flow.request.pretty_url).path.rstrip("/")
    if path == "/s" or path.startswith("/s/"):
        return True

    # Keep a compatibility fallback for unusual article URLs without injecting
    # into unrelated WeChat pages.
    markers = (
        'id="js_content"', "id='js_content'",
        'class="rich_media_content', "class='rich_media_content",
        'id="activity-name"', "id='activity-name'",
    )
    return any(marker in html for marker in markers)


class WxArticleSaver:
    def request(self, flow: http.HTTPFlow):
        host = (flow.request.pretty_host or "").lower()
        if host != HOST:
            return
        path = urlparse(flow.request.pretty_url).path

        # If an already-cached article produces follow-up requests with an
        # article Referer but no new /s document request, schedule one safe
        # foreground-WeChat Ctrl+R. Normal article loads are left untouched.
        if not (path == "/s" or path.startswith("/s/")):
            maybe_schedule_cached_article_refresh(flow)

        # Only touch real WeChat article document requests.  This asks the
        # WebView/network stack to revalidate instead of reusing an HTTP cache
        # entry.  It deliberately does NOT affect /mp/* APIs, JS, CSS, images,
        # video, login state or cookies.
        if path == "/s" or path.startswith("/s/"):
            mark_article_document_seen(flow.request.pretty_url)
            flow.request.headers["Cache-Control"] = "no-cache, max-age=0"
            flow.request.headers["Pragma"] = "no-cache"
            ctx.log.info(f"[WxArticleSaver] 文章请求已要求重新验证缓存: path={path}")

        if path != SAVE_PATH:
            return

        cleanup_cache()
        qs = parse_qs(urlparse(flow.request.pretty_url).query)
        token = (qs.get("id") or [""])[0]
        item = ARTICLE_CACHE.get(token)
        if not item:
            body = """<!doctype html><html><meta charset="utf-8"><body style="font-family:sans-serif;padding:20px">导出失败：当前文章缓存已失效，请返回文章重新打开后再点一次。</body></html>"""
            flow.response = http.Response.make(404, body.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"})
            return

        try:
            rendered_html = ""
            if flow.request.method.upper() == "POST":
                try:
                    rendered_html = flow.request.get_text(strict=False) or ""
                except Exception:
                    rendered_html = ""

            html_to_export = rendered_html if rendered_html.strip() else item["html"]
            source = "rendered-dom" if rendered_html.strip() else "cached-response"
            ctx.log.info(
                f"[WxArticleSaver] 开始导出: source={source} | html_bytes="
                f"{len(html_to_export.encode('utf-8', 'ignore'))} | url={item['url'][:150]}"
            )

            folder, title, video_count = save_article(
                item["url"], html_to_export, item.get("media") or []
            )
            body = f"已导出：{title}；本地视频：{video_count} 个"
            flow.response = http.Response.make(
                200,
                body.encode("utf-8"),
                {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"},
            )
        except Exception as e:
            ctx.log.error(f"[WxArticleSaver] 手动导出失败: {type(e).__name__}: {e}")
            body = f"导出失败：{type(e).__name__}: {e}"
            flow.response = http.Response.make(
                500,
                body.encode("utf-8"),
                {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"},
            )

    def response(self, flow: http.HTTPFlow):
        global CURRENT_ARTICLE_TOKEN
        if not flow.response:
            return

        host = (flow.request.pretty_host or "").lower()
        if is_media_host(host):
            remember_media_for_current_article(flow)
            return

        if host != HOST:
            return

        path = urlparse(flow.request.pretty_url).path
        if path == SAVE_PATH:
            return

        ctype = (flow.response.headers.get("content-type") or "").lower()
        if "text/html" not in ctype:
            return
        try:
            html = flow.response.get_text(strict=False)
        except Exception:
            return
        if not is_article_candidate(flow, html):
            return

        cleanup_cache()
        url = flow.request.pretty_url
        token = make_token(url, html)
        ARTICLE_CACHE[token] = {"url": url, "html": html, "created": time.time(), "media": []}
        CURRENT_ARTICLE_TOKEN = token

        markup = button_markup(token)
        lower = html.lower()
        idx = lower.rfind("</body>")
        if idx >= 0:
            html = html[:idx] + markup + html[idx:]
        else:
            html += markup

        for h in (
            "content-security-policy",
            "content-security-policy-report-only",
            "x-webkit-csp",
            "x-content-security-policy",
        ):
            if h in flow.response.headers:
                del flow.response.headers[h]

        flow.response.set_text(html)

        # Prevent the injected article HTML from being kept as a reusable HTTP
        # cache entry.  Scope is intentionally limited to article HTML only.
        # This helps subsequent opens go through the proxy again so the export
        # button can be injected reliably.
        flow.response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        flow.response.headers["Pragma"] = "no-cache"
        flow.response.headers["Expires"] = "0"
        # A cached upstream validator can otherwise still produce a 304 on some
        # WebView builds.  Remove validators from the modified document only.
        for h in ("ETag", "Last-Modified"):
            if h in flow.response.headers:
                del flow.response.headers[h]

        ctx.log.info(
            f"[WxArticleSaver] 已识别候选文章页，已注入导出按钮: "
            f"path={urlparse(url).path} | html_bytes={len(html.encode('utf-8', 'ignore'))} | {url[:150]}"
        )


addons = [WxArticleSaver()]

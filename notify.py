#!/usr/bin/env python3
"""
把當日早安圖推送到 Telegram、LINE。
用法: python notify.py <site_dir>
Telegram 直接上傳圖檔；LINE 需公開網址，使用 GitHub Pages 上的圖。
未設定某平台的 Secret 時跳過該平台。
"""
import datetime as dt
import os
import sys
import time

import requests

BASE_URL = "https://ch88chen.github.io/good-morning"
TZ = dt.timezone(dt.timedelta(hours=8))


def log(msg):
    print(f"[{dt.datetime.now(TZ):%H:%M:%S}] {msg}", flush=True)


def wait_until_live(urls, timeout=600):
    """LINE 以網址讀圖，要等 GitHub Pages 部署完成"""
    deadline = time.time() + timeout
    pending = set(urls)
    while pending and time.time() < deadline:
        pending = {u for u in pending if requests.head(u, timeout=15).status_code != 200}
        if pending:
            time.sleep(15)
    if pending:
        raise RuntimeError(f"GitHub Pages 尚未提供：{pending}")


def send_telegram(card):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log("⚠️  未設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，跳過 Telegram")
        return True
    with open(card, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", timeout=120,
                          data={"chat_id": chat}, files={"photo": (os.path.basename(card), f, "image/jpeg")})
    log(f"Telegram: {r.status_code}{'' if r.ok else ' ' + r.text[:200]}")
    return r.ok


def send_line(day):
    token, to = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"), os.environ.get("LINE_TO")
    if not token or not to:
        log("⚠️  未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_TO，跳過 LINE")
        return True
    original, preview = f"{BASE_URL}/cards/{day}.jpg", f"{BASE_URL}/cards/{day}_preview.jpg"
    wait_until_live([original, preview])
    r = requests.post("https://api.line.me/v2/bot/message/push", timeout=30,
                      headers={"Authorization": f"Bearer {token}"},
                      json={"to": to, "messages": [{"type": "image", "originalContentUrl": original,
                                                    "previewImageUrl": preview}]})
    log(f"LINE: {r.status_code}{'' if r.ok else ' ' + r.text[:200]}")
    return r.ok


def main():
    site = sys.argv[1]
    day = f"{dt.datetime.now(TZ):%Y%m%d}"
    card = os.path.join(site, "cards", f"{day}.jpg")
    results = []
    for name, fn in (("Telegram", lambda: send_telegram(card)), ("LINE", lambda: send_line(day))):
        try:
            results.append(fn())
        except Exception as e:  # 一個平台失敗不影響另一個
            log(f"❌ {name} 失敗：{e}")
            results.append(False)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""每日早安圖：景點全景照 + 四地天氣 + 地點標示 + 日期。"""
import datetime as dt
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "GoodMorningCard/1.0 (ch88chen)"}
TZ = dt.timezone(dt.timedelta(hours=8))

W = 2048            # 輸出寬度
PHOTO_RATIO = 1.9   # 全景比例（寬/高）
BAND_H = 220        # 下方半透明資訊帶高度（疊在照片上）

# 開源字型隨 repo 附上（SIL OFL），雲端 runner 不需安裝
CJK_BOLD = str(HERE / "fonts/NotoSansTC-Bold.otf")
CJK_MEDIUM = str(HERE / "fonts/NotoSansTC-Medium.otf")
LATIN_FONT = str(HERE / "fonts/Lora-BoldItalic.ttf")
CREDIT_FONT = str(HERE / "fonts/NotoSans-Regular.ttf")   # 作者名可能含歐洲字母（ł、ö…）

CITIES = [
    ("新竹市", 24.8138, 120.9675),
    ("台北市", 25.0330, 121.5654),
    ("宜蘭縣", 24.7021, 121.7378),
    ("高雄市", 22.6273, 120.3014),
]

# 景點照片庫：title 為 Wikimedia Commons 檔名；crop_x / crop_y 為裁成全景時保留區域的位置 (0=左/頂, 1=右/底)
SPOTS = json.loads((HERE / "spots.json").read_text(encoding="utf-8"))

DAY_HOURS = range(6, 18)  # 白天時段 06:00~17:59，用來判斷當日天氣描述


def describe_day(cloud, codes, pops):
    """依白天逐時資料組出天氣描述與圖示（避免單一小時的毛毛雨把整天標成雨天）。"""
    avg_cloud = sum(cloud) / len(cloud)
    sunny_h = sum(c < 50 for c in cloud)   # 有陽光的小時數
    if sunny_h >= 10 and avg_cloud < 20:
        sky, icon = "晴", "sun"
    elif sunny_h >= 4:
        sky, icon = "晴時多雲", "sun_cloud"
    elif sunny_h >= 2:
        sky, icon = "多雲時晴", "sun_cloud"
    elif avg_cloud < 85:
        sky, icon = "多雲", "cloud"
    else:
        sky, icon = "陰", "cloud"
    rain_h = sum(c >= 51 for c in codes)
    storm_h = sum(c >= 95 for c in codes)
    if max(pops) < 30:
        return sky, icon
    if storm_h:
        return sky + "短暫雷陣雨", "storm"
    if rain_h >= 6:
        return "陰有雨" if sky == "陰" else "多雲有雨", "rain"
    if rain_h >= 2:
        return sky + "短暫雨", "rain"
    return sky, icon


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def fetch_weather():
    q = urllib.parse.urlencode({
        "latitude": ",".join(str(c[1]) for c in CITIES),
        "longitude": ",".join(str(c[2]) for c in CITIES),
        "daily": "temperature_2m_max,temperature_2m_min",
        "hourly": "weather_code,cloud_cover,precipitation_probability",
        "timezone": "Asia/Taipei", "forecast_days": 1,
    })
    data = get_json("https://api.open-meteo.com/v1/forecast?" + q)
    out = []
    for (name, *_), d in zip(CITIES, data):
        h = d["hourly"]
        day = [i for i, t in enumerate(h["time"]) if int(t[11:13]) in DAY_HOURS]
        pops = [h["precipitation_probability"][i] or 0 for i in day]
        desc, icon = describe_day([h["cloud_cover"][i] for i in day],
                                  [h["weather_code"][i] for i in day], pops)
        out.append({
            "name": name, "desc": desc, "icon": icon,
            "lo": round(d["daily"]["temperature_2m_min"][0]),
            "hi": round(d["daily"]["temperature_2m_max"][0]),
            "pop": max(pops),
        })
    return out


def fetch_photo(title, width):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": title,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": width,
    })
    info = next(iter(get_json("https://commons.wikimedia.org/w/api.php?" + q)["query"]["pages"].values()))
    url = info["imageinfo"][0]["thumburl"]
    for attempt in range(5):   # Commons 偶爾回 429，退避重試
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGB")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            time.sleep(30 * (attempt + 1))


def load_photo(spot):
    """優先用 repo 內已裁好的照片（photos/<key>.jpg）；沒有才從 Commons 下載並存起來。"""
    path = HERE / "photos" / f"{spot['key']}.jpg"
    if path.exists():
        return Image.open(path).convert("RGB")
    photo = crop_panorama(fetch_photo(spot["title"], 3840), spot.get("crop_x", 0.5), spot.get("crop_y", 0.0))
    path.parent.mkdir(exist_ok=True)
    photo.save(path, quality=92)
    return photo


def crop_panorama(img, crop_x=0.5, crop_y=0.0):
    h = round(W / PHOTO_RATIO)
    if img.width / img.height > PHOTO_RATIO:   # 比全景更寬：左右裁切
        img = img.resize((round(img.width * h / img.height), h), Image.LANCZOS)
        left = round((img.width - W) * crop_x)
        return img.crop((left, 0, left + W, h))
    img = img.resize((W, round(img.height * W / img.width)), Image.LANCZOS)
    top = round((img.height - h) * crop_y)
    return img.crop((0, top, W, top + h))


def font(path, size):
    return ImageFont.truetype(path, size)


# ---------- 天氣小圖示（純繪製，避免依賴 emoji 字型） ----------
def draw_icon(d, kind, x, y, s):
    sun, cloud, rain = (255, 214, 102), (245, 247, 250), (150, 200, 255)
    if kind in ("sun", "sun_cloud"):
        cx, cy, r = (x + s * 0.5, y + s * 0.5, s * 0.22) if kind == "sun" else (x + s * 0.36, y + s * 0.36, s * 0.18)
        import math
        for i in range(8):
            a = i * math.pi / 4
            d.line([(cx + math.cos(a) * r * 1.4, cy + math.sin(a) * r * 1.4),
                    (cx + math.cos(a) * r * 1.9, cy + math.sin(a) * r * 1.9)], fill=sun, width=max(3, s // 16))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sun)
    if kind != "sun":
        oy = s * 0.08 if kind in ("rain", "storm") else s * 0.18
        bx, by = x + s * 0.12, y + oy
        d.ellipse([bx + s * 0.05, by + s * 0.30, bx + s * 0.40, by + s * 0.62], fill=cloud)
        d.ellipse([bx + s * 0.22, by + s * 0.16, bx + s * 0.62, by + s * 0.56], fill=cloud)
        d.ellipse([bx + s * 0.45, by + s * 0.30, bx + s * 0.78, by + s * 0.62], fill=cloud)
        d.rectangle([bx + s * 0.22, by + s * 0.42, bx + s * 0.62, by + s * 0.62], fill=cloud)
    if kind in ("rain", "storm"):
        for i in range(3):
            rx = x + s * (0.32 + i * 0.18)
            d.line([(rx, y + s * 0.78), (rx - s * 0.07, y + s * 0.96)], fill=rain, width=max(3, s // 14))
    if kind == "storm":
        d.polygon([(x + s * .55, y + s * .62), (x + s * .42, y + s * .84), (x + s * .52, y + s * .84),
                   (x + s * .45, y + s), (x + s * .66, y + s * .76), (x + s * .55, y + s * .76)], fill=sun)


def draw_pin(d, x, y, s, color):
    """地點標示（水滴形大頭針）。(x, y) 為頂端左上角。"""
    r = s * 0.32
    cx, cy = x + s * 0.5, y + r + 2
    d.polygon([(cx - r * 0.86, cy + r * 0.5), (cx + r * 0.86, cy + r * 0.5), (cx, y + s)], fill=color)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    d.ellipse([cx - r * 0.42, cy - r * 0.42, cx + r * 0.42, cy + r * 0.42], fill=(0, 0, 0, 0))


def text_with_shadow(img, xy, text, f, fill, shadow=(0, 0, 0, 210), blur=6, anchor="la"):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] + 2, xy[1] + 3), text, font=f, fill=shadow, anchor=anchor)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(img).text(xy, text, font=f, fill=fill, anchor=anchor)


def tint(rgb, toward, k):
    return tuple(round(c + (t - c) * k) for c, t in zip(rgb, toward))


def build(spot, weather, today, out_path):
    photo = load_photo(spot)
    ph = photo.height
    canvas = Image.new("RGBA", (W, ph), (0, 0, 0, 255))
    canvas.paste(photo, (0, 0))

    # 依照片取色：天空色做淡色字，底部色做資訊帶底色
    sky = ImageStat.Stat(photo.crop((0, 0, W, ph // 5))).mean
    bottom = ImageStat.Stat(photo.crop((0, ph * 4 // 5, W, ph))).mean
    light = tint(tuple(map(int, sky)), (255, 255, 255), 0.85)        # 淡色系文字
    band = tint(tuple(map(int, bottom)), (20, 24, 32), 0.72)          # 深色資訊帶

    # 上方中間：Have a nice day!
    text_with_shadow(canvas, (W // 2, 34), "Have a nice day!", font(LATIN_FONT, 66),
                     fill=light + (255,), shadow=(10, 20, 40, 230), blur=7, anchor="ma")

    # 左上：天氣面板
    f_name, f_temp, f_desc = font(CJK_BOLD, 58), font(CJK_BOLD, 58), font(CJK_MEDIUM, 44)
    x0, y0, row_h, icon_s, pad = 40, 128, 88, 70, 22
    name_w = max(f_name.getlength(w["name"]) for w in weather)
    temp_w = max(f_temp.getlength(f"{w['lo']}~{w['hi']}°C") for w in weather)
    desc_w = max(f_desc.getlength(f"{w['desc']} 降雨{w['pop']}%") for w in weather)
    panel_w = pad + icon_s + 22 + name_w + 30 + temp_w + 30 + desc_w + pad
    if spot.get("panel") == "right":   # 主景在左側的照片，面板改放右上
        x0 = W - x0 - panel_w
    panel_h = pad * 2 + row_h * len(weather) - 10
    panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle([x0, y0, x0 + panel_w, y0 + panel_h], 28, fill=(15, 25, 45, 50))
    canvas.alpha_composite(panel)
    d = ImageDraw.Draw(canvas)
    for i, w in enumerate(weather):
        ry = y0 + pad + i * row_h
        cy = ry + icon_s / 2
        draw_icon(d, w["icon"], x0 + pad, ry, icon_s)
        x = x0 + pad + icon_s + 22
        text_with_shadow(canvas, (x, cy), w["name"], f_name, (255, 255, 255, 255), anchor="lm", blur=4)
        x += name_w + 30
        text_with_shadow(canvas, (x, cy), f"{w['lo']}~{w['hi']}°C", f_temp, (255, 236, 179, 255), anchor="lm", blur=4)
        x += temp_w + 30
        text_with_shadow(canvas, (x, cy), f"{w['desc']} 降雨{w['pop']}%", f_desc, light + (255,), anchor="lm", blur=4)

    # 下方資訊帶：半透明漸層疊在照片上，地點 + 日期
    grad = Image.new("L", (1, BAND_H))
    for yy in range(BAND_H):
        grad.putpixel((0, yy), round(170 * min(1, (yy / BAND_H) * 1.6)))
    shade = Image.new("RGBA", (W, BAND_H), band + (255,))
    shade.putalpha(grad.resize((W, BAND_H)))
    canvas.alpha_composite(shade, (0, ph - BAND_H))
    d = ImageDraw.Draw(canvas)
    f_loc, f_date, f_cred = font(CJK_BOLD, 44), font(CJK_BOLD, 46), font(CREDIT_FONT, 20)
    pin_s = 50
    loc_w = pin_s + 14 + f_loc.getlength(spot["name"])
    lx = (W - loc_w) / 2
    ly = ph - 128
    pin_layer = Image.new("RGBA", (pin_s + 4, pin_s + 4), (0, 0, 0, 0))
    draw_pin(ImageDraw.Draw(pin_layer), 2, 2, pin_s, (240, 120, 100, 255))
    canvas.alpha_composite(pin_layer, (round(lx), ly - pin_s // 2))
    text_with_shadow(canvas, (lx + pin_s + 14, ly), spot["name"], f_loc, light + (255,), anchor="lm", blur=4)

    weekday = "一二三四五六日"[today.weekday()]
    text_with_shadow(canvas, (W / 2, ph - 50), f"{today:%Y/%m/%d}（{weekday}）", f_date,
                     (255, 255, 255, 255), anchor="mm", blur=4)
    d = ImageDraw.Draw(canvas)
    d.text((W - 20, ph - 12), spot["credit"], font=f_cred, fill=light + (140,), anchor="rd")

    card = canvas.convert("RGB")
    card.save(out_path, quality=88)
    # LINE 預覽圖需 ≤ 1MB
    card.resize((1024, round(card.height * 1024 / W)), Image.LANCZOS).save(
        out_path.with_name(out_path.stem + "_preview.jpg"), quality=80)
    return out_path


def main():
    today = dt.datetime.now(TZ).date()
    spot = SPOTS[today.toordinal() % len(SPOTS)]   # 依日期輪播
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(build(spot, fetch_weather(), today, out_dir / f"{today:%Y%m%d}.jpg"))


if __name__ == "__main__":
    sys.exit(main())

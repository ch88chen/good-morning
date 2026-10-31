# Good Morning Card

每天台北時間 06:30 自動產生早安圖（歐洲／日本／加拿大景點全景 + 新竹、台北、宜蘭、高雄天氣），
推送到 LINE 官方帳號與 Telegram「我的第一個AI助理」。全程在 GitHub Actions 執行，不需開電腦。

- `make_card.py`：產圖（天氣來源 Open-Meteo，依白天 06–18 時逐時資料判斷晴／多雲／雨）
- `spots.json`：381 張景點照片（約 180 個景點，每個景點 1–4 張不同季節／角度），從 2026-10-29 起每天依序一張，一整輪約一年才重複；同景點至少間隔 55 天。新照片加在尾端，不會打亂既有順序。`panel: "right"` 表示主景在左，天氣面板改放右上
- `photos/`：前 30 張已裁好的照片；其餘當天才從 Wikimedia 下載，下載失敗就改用 photos/ 內的照片，當天照常推送
- `notify.py`：Telegram 直接上傳圖檔；LINE 使用 GitHub Pages 上的圖片網址
- `.github/workflows/daily.yml`：05:47 / 06:07 / 06:27 啟動（防 GitHub 排程延遲），產圖後等到 06:30 推送，當天已推送就跳過

手動重送：`gh workflow run daily.yml -R ch88chen/good-morning -f force=true`（不加 force 時，當天已送過會自動跳過）

準時觸發：GitHub 排程常延遲 1～3 小時，所以由 Claude 雲端排程（routine）每天台北 05:50 推一個空 commit 到 `claude/good-morning-trigger` 分支觸發；GitHub 排程保留當備援。

## 授權
- 照片：Wikimedia Commons，各張作者與授權（CC BY / CC BY-SA）見 `spots.json` 的 `credit`，並印在圖片右下角
- 字型：Noto Sans TC、Lora，SIL Open Font License（見 `fonts/`）

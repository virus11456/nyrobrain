# BTC Quantitative Intelligence Dashboard

判斷大錢在買還是在賣的量化中台。聚合三個維度的鏈上 + 市場數據，產出一個簡單的行動建議。

## 一眼看懂

```
╔══════════════════════════════════════════════╗
║  BTC: $63,948                                ║
║  Trade: WAIT        ← 交易者：觀望           ║
║  HODL:  HODL        ← 長期持有：不動         ║
║  Overall: +0.3   Whale: +0.5  VP: -0.1  SM: -0.1 ║
╚══════════════════════════════════════════════╝
```

## 三個監測模組

| 模組 | 看什麼 | 資料來源 |
|------|--------|---------|
| **Whale Flow** | 大戶在囤幣還是出貨 | 交易所儲備、淨流入/流出、鯨魚比率、穩定幣儲備、MPI |
| **Volume-Price** | 量價是否背離，趨勢是否健康 | OHLCV、OBV、成交量移動平均 |
| **Smart Money** | 機構在買還是在賣 | Coinbase 溢價、主動買賣比、資金費率、OI |

## 分數 → 行動

| Overall Score | Trade（交易） | HODL（長期持有） |
|:--:|:--|:--|
| **+3 ~ +6** | BUY — 跟趨勢作多 | ADD — 加大 DCA |
| **+1 ~ +3** | WATCH — 可考慮進場 | DCA — 正常定投 |
| **-1 ~ +1** | WAIT — 觀望不動 | HODL — 持有不動 |
| **-3 ~ -1** | CAUTION — 減倉觀望 | PAUSE — 暫停加倉 |
| **-6 ~ -3** | SELL — 避險或作空 | REDUCE — 減倉 30-50% |

## 快速開始

```bash
# 安裝依賴
uv sync

# 執行三個模組（產出訊號 CSV）
uv run python brain/source/whale/run.py
uv run python brain/source/volume_price/run.py
uv run python brain/source/smart_money/run.py

# 啟動互動看板
uv run streamlit run brain/source/dashboard/app.py --server.port 8501

# 或產出靜態 PNG
uv run python brain/source/dashboard/run.py
```

## 互動看板

**Live Demo:** https://virus11456.github.io/nyrobrain/

`streamlit run brain/source/dashboard/app.py`

- 即時決策橫幅（BUY/WATCH/WAIT/CAUTION/SELL）
- 三個互動式儀表板
- Plotly 圖表，支援縮放、懸停
- 側欄時間範圍選擇（30~365 天）
- 三個模組詳細頁籤，各有 4 張子圖
- 深色主題 UI

## 檔案結構

```
brain/source/
├── whale/            # 鯨魚持倉監測
│   ├── analyzer.py   # 信號計算邏輯
│   ├── run.py        # 主程式
│   ├── assets/       # 圖表 PNG
│   └── data/         # 原始數據 (parquet)
├── volume_price/     # 量價背離監測
│   ├── analyzer.py
│   ├── run.py
│   ├── assets/
│   └── data/
├── smart_money/      # 聰明錢監測
│   ├── analyzer.py
│   ├── run.py
│   ├── assets/
│   └── data/
├── dashboard/
│   ├── app.py        # Streamlit 互動看板
│   ├── run.py        # 靜態 PNG 產生器
│   └── assets/
└── chart_style.py    # 共用圖表樣式

brain/concept/
└── dashboard-reading-guide.md   # 看板閱讀指南

oms/                  # 下單系統 (Bybit 模擬盤)
```

## 資料來源

- [CryptoQuant](https://cryptoquant.com/) — 鏈上數據（交易所流動、衍生品、市場數據）
- [Glassnode](https://glassnode.com/) — 鏈上指標
- [ADRS](https://docs.balaenaquant.com/docs/adrs) — 策略回測框架

## License

MIT

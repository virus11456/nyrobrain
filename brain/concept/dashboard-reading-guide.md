---
type: concept
title: "Quant Intelligence Dashboard Reading Guide"
created: 2026-06-23
tags: [dashboard, guide, interpretation, decision-making, hodl, long-term]
links:
  - target: brain/source/whale/
    kind: derives_from
  - target: brain/source/volume_price/
    kind: derives_from
  - target: brain/source/smart_money/
    kind: derives_from
  - target: brain/source/dashboard/
    kind: derives_from
---

# 量化中台看板閱讀指南

## 一句話總結

這個看板幫你判斷「大錢現在在買還是在賣」，給你一個簡單的行動建議。

## 看板結構

看板由上到下分為：

### 1. 決策欄（Decision Bar）
最頂端一行，直接告訴你：
- **DECISION**: BUY / WATCH / WAIT / CAUTION / SELL
- 三個模組分數（Whale / VP / Smart Money）
- BTC 即時價格
- 一句話摘要（例如：Whales accumulating | Volume neutral | Institutions selling）

### 2. 三個指針儀表
每個模組的分數範圍 -3 到 +3：
- 紅區（-3 ~ -1）= 偏空
- 灰區（-1 ~ +1）= 中性
- 綠區（+1 ~ +3）= 偏多
- 箭頭指向當前分數位置

### 3. 分數→行動對照條（Score Range → Action Guide）
橫向色條顯示分數對應的行動：
- **-6 ~ -3**: SELL — 全力賣出，避險或作空
- **-3 ~ -1**: CAUTION — 賣壓增，減倉
- **-1 ~ +1**: WAIT — 無方向，觀望
- **+1 ~ +3**: WATCH — 可考慮進場
- **+3 ~ +6**: BUY — 全力買入，跟趨勢

箭頭標記當前分數的實際位置。

### 4. 綜合分數歷史
過去 270 天每天的綜合分數，綠色 = 偏多、紅色 = 偏空。

### 5. 分數明細表
列出 Overall Score + 三個模組個別分數 + BTC 價格 + 行動建議。

### 6. 趨勢子圖
四個關鍵指標過去 270 天走勢：
- Reserve Z-Score（BTC 儲備 Z 分數）
- Whale Reserve Signal（鯨魚儲備訊號）
- OBV-Price Correlation（OBV-價格相關性）
- CPI Z vs Taker Z（Coinbase 溢價 vs 主動買賣比）

### 7. 行動建議框
右下角精簡版：燈號 + 行動 + 理由。

---

## 三個模組分別看什麼

### Whale Accumulation（鯨魚持倉）
追蹤大戶把幣從交易所提出（囤幣）還是存入（準備賣）。

**資料來源**：
- BTC 交易所儲備量
- 交易所淨流入/流出
- 鯨魚交易比率
- 穩定幣儲備量
- 資金流向比率
- 礦工持倉指數（MPI）

**正分數 = 吸籌（大戶在買）**，負分數 = 派發（大戶在賣）。

### Volume-Price Divergence（量價背離）
追蹤成交量和價格的關係，判斷趨勢強弱。

**資料來源**：
- 每日 OHLCV
- OBV（能量潮指標）
- 成交量移動平均（5d / 20d / 50d）
- 價格移動平均

**正分數 = 量價偏多**（如：跌時量縮 = 賣壓衰竭），**負分數 = 量價偏空**（如：漲時量縮 = 買盤不足）。

### Smart Money（聰明錢）
追蹤專業機構的資金流向。

**資料來源**：
- Coinbase 溢價指數（機構偏好 Coinbase）
- 主動買賣比率（全市場合約）
- 永續合約資金費率
- 未平倉合約量（OI）

**正分數 = 機構買入**，**負分數 = 機構賣出**。

特別關注：當 Coinbase 溢價為負（機構賣）但全市場買盤偏多（散戶買）時，形成「派發結構」—聰明錢出貨給散戶。

---

## 綜合分數怎麼算

```
Overall = Whale（標準化到 -2~+2）
        + Volume-Price（標準化到 -2~+2）
        + Smart Money（標準化到 -2~+2）
```

範圍：-6 到 +6。

---

## 雙軌行動建議

看板同時提供兩種角色的建議：

### Trade（交易者）
適合短中線交易者，判斷進出場時機。

| 燈號 | 分數 | 交易者動作 |
|------|------|-----------|
| **BUY** | +3~+6 | 跟趨勢作多 |
| **WATCH** | +1~+3 | 可考慮進場，分批建倉 |
| **WAIT** | -1~+1 | 觀望不動 |
| **CAUTION** | -3~-1 | 減倉，注意風險 |
| **SELL** | -6~-3 | 避險或作空 |

### HODL（長期持有者）
適合長期現貨持有者，判斷加倉/減倉時機。

| 燈號 | 分數 | 長期持有者動作 |
|------|------|---------------|
| **BUY** | +3~+6 | **ADD** — 加大 DCA 金額，積極加倉 |
| **WATCH** | +1~+3 | **DCA** — 保持正常定投，可略加 |
| **WAIT** | -1~+1 | **HODL** — 什麼都不做，繼續持有 |
| **CAUTION** | -3~-1 | **PAUSE** — 暫停加倉，觀察 |
| **SELL** | -6~-3 | **REDUCE** — 減倉 30-50%，或開對沖 |

### 核心原則

> 長期持有者不需要頻繁操作。只有在 BUY（加倉）或 SELL（減倉）燈號亮起時才需要行動。WAIT 就是 HODL — 拿著就好。

---

## 使用建議

1. **打開看板** → 看 TRADE / HODL 兩欄，決定交易和持倉策略
2. **WAIT → HODL** → 不用多看，繼續持有
3. **WATCH / BUY** → 往下看三個模組誰在帶動，確認訊號一致性
4. **如果模組彼此矛盾**（如：鯨魚在買但機構在賣）→ 分數會落在中性區，系統自動叫你觀望
5. **分數開始移動**（如：從 -2 爬到 0）→ 趨勢正在轉變，值得追蹤

---

## 檔案位置

| 模組 | 分析邏輯 | 主程式 | 數據目錄 |
|------|---------|--------|---------|
| 鯨魚 | `brain/source/whale/analyzer.py` | `brain/source/whale/run.py` | `brain/source/whale/data/` |
| 量價 | `brain/source/volume_price/analyzer.py` | `brain/source/volume_price/run.py` | `brain/source/volume_price/data/` |
| 聰明錢 | `brain/source/smart_money/analyzer.py` | `brain/source/smart_money/run.py` | `brain/source/smart_money/data/` |
| 整合看板 | — | `brain/source/dashboard/run.py` | — |

---

## 執行指令

```bash
# 單一模組
uv run python brain/source/whale/run.py
uv run python brain/source/volume_price/run.py
uv run python brain/source/smart_money/run.py

# 整合看板（需先跑三個模組生成 CSV）
uv run python brain/source/dashboard/run.py
```

# CRT Signal Monitor

CRT 信號頻道漏跳監控工具

用 OANDA K 線驗證頻道的每筆信號是否正確回報 TP/SL。

## 安裝

```bash
pip install -r requirements.txt
```

## 設定

```bash
copy config.example.yaml config.yaml
```

填入你的 Telegram API（從 https://my.telegram.org 取得）

## 使用

### 1. 同步歷史 + 驗證

```bash
python monitor.py sync
```

第一次會要求輸入 Telegram 驗證碼。
會自動抓取頻道所有歷史信號，用 OANDA K 線比對。

### 2. 看報告

```bash
python monitor.py report
```

### 3. 開儀表板

```bash
streamlit run dashboard.py
```

瀏覽器開 http://localhost:8501

## 顯示內容

- 每筆信號的 TP1~TP4 和 SL 是否被 K 線觸及
- 頻道有沒有回報
- 漏跳明細（K 線到了但頻道沒報的）
- 漏跳率趨勢圖
- K 線實際 vs 頻道回報 對比圖

## 排除規則

- 已達 TP1 後碰 SL：不算漏跳（頻道設計如此）
- 貫穿報高 TP：代表低 TP 也到了，不算漏

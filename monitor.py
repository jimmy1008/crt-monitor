"""
CRT Signal Monitor - 信號監控工具

功能：
1. 讀取 Telegram 頻道的所有信號
2. 用 TradingView OANDA/Binance K 線驗證
3. 比對哪些 TP/SL 到了但頻道沒回報
4. 統計準確率

使用：
    python monitor.py sync       # 同步歷史訊息 + 驗證
    python monitor.py live       # 即時監聽 + 驗證
    python monitor.py report     # 只看報告
    streamlit run dashboard.py   # 開儀表板
"""

import asyncio
import argparse
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

import yaml
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Text, Enum as SAEnum, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from telethon import TelegramClient, events

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
# DB Models
# ============================================================

class Base(DeclarativeBase):
    pass


class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True)
    source = Column(String(50))
    signal_key = Column(String(200), unique=True)
    symbol = Column(String(50))
    side = Column(String(10))         # long / short
    entry = Column(Float)
    sl = Column(Float)
    tp1 = Column(Float)
    tp2 = Column(Float)
    tp3 = Column(Float)
    tp4 = Column(Float)
    timeframe = Column(String(10))
    signal_time = Column(DateTime)
    # 頻道回報
    reported_tp1 = Column(Boolean, default=False)
    reported_tp2 = Column(Boolean, default=False)
    reported_tp3 = Column(Boolean, default=False)
    reported_tp4 = Column(Boolean, default=False)
    reported_sl = Column(Boolean, default=False)
    # K 線驗證
    actual_tp1 = Column(Boolean, default=False)
    actual_tp2 = Column(Boolean, default=False)
    actual_tp3 = Column(Boolean, default=False)
    actual_tp4 = Column(Boolean, default=False)
    actual_sl = Column(Boolean, default=False)
    # 漏跳
    missed = Column(Text, default="")   # 漏跳的 TP/SL
    verified = Column(Boolean, default=False)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class RawMsg(Base):
    __tablename__ = "raw_messages"
    id = Column(Integer, primary_key=True)
    source = Column(String(50))
    chat_id = Column(String(50))
    message_id = Column(String(50))
    timestamp = Column(DateTime)
    raw_text = Column(Text)


# ============================================================
# Config & DB
# ============================================================

def load_config():
    p = Path("config.yaml")
    if not p.exists():
        print("請複製 config.example.yaml 為 config.yaml 並填入設定")
        sys.exit(1)
    return yaml.safe_load(p.read_text(encoding="utf-8"))


_engine = None
_Session = None


def init_db(url="sqlite:///data/monitor.db"):
    global _engine, _Session
    Path("data").mkdir(exist_ok=True)
    _engine = create_engine(url)
    _Session = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)


def get_session():
    return _Session()


# ============================================================
# Parser（跟主系統一樣）
# ============================================================

SIGNAL_KEY_RE = re.compile(r"#(\w+)")
ENTRY_RE = re.compile(r"CRT SNIPE")
PRICE_RE = re.compile(r"(?:進場價|收盤價)[：:]\s*([\d.]+)")
DIRECTION_RE = re.compile(r"方向[：:]\s*看(多|空)\s*\((LONG|SHORT)\)")
DIRECTION_SIMPLE_RE = re.compile(r"(🟢\s*看多|🔴\s*看空)")
SYMBOL_RE = re.compile(r"([A-Z0-9]+(?:\.[A-Z])?)\s*\|\s*\d+H?\s*CRT")
SYMBOL_BRACKET_RE = re.compile(r"【([A-Z0-9.]+)】")
TP_RE = re.compile(r"TP(\d)[：:]\s*([\d.]+)")
SL_RE = re.compile(r"SL[：:]\s*([\d.]+)")
TIMEFRAME_RE = re.compile(r"\|\s*(\d+H)\s*CRT", re.IGNORECASE)
TP_UPDATE_RE = re.compile(r"CRT TP")
SL_UPDATE_RE = re.compile(r"CRT SL")


def parse_message(text, timestamp):
    """解析訊息，回傳 dict 或 None"""
    key_match = SIGNAL_KEY_RE.search(text)
    signal_key = key_match.group(1) if key_match else None

    if ENTRY_RE.search(text):
        return _parse_entry(text, timestamp, signal_key)
    elif TP_UPDATE_RE.search(text):
        return _parse_tp(text, signal_key)
    elif SL_UPDATE_RE.search(text):
        return {"type": "sl", "key": signal_key}
    return None


def _parse_entry(text, timestamp, key):
    sym = SYMBOL_RE.search(text) or SYMBOL_BRACKET_RE.search(text)
    if not sym:
        return None
    symbol = sym.group(1)

    price = PRICE_RE.search(text)
    if not price:
        return None
    entry = float(price.group(1))

    d = DIRECTION_RE.search(text)
    if d:
        side = "long" if d.group(2) == "LONG" else "short"
    else:
        ds = DIRECTION_SIMPLE_RE.search(text)
        if not ds:
            return None
        side = "long" if "多" in ds.group(1) else "short"

    sl_m = SL_RE.search(text)
    if not sl_m:
        return None

    tps = {}
    for m in TP_RE.finditer(text):
        tps[f"tp{m.group(1)}"] = float(m.group(2))

    tf = TIMEFRAME_RE.search(text)

    return {
        "type": "entry",
        "key": key,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "sl": float(sl_m.group(1)),
        "tp1": tps.get("tp1"),
        "tp2": tps.get("tp2"),
        "tp3": tps.get("tp3"),
        "tp4": tps.get("tp4"),
        "timeframe": tf.group(1).lower() if tf else None,
        "signal_time": timestamp,
    }


def _parse_tp(text, key):
    levels = []
    for m in TP_RE.finditer(text):
        levels.append(int(m.group(1)))
    return {"type": "tp", "key": key, "levels": levels} if levels else None


# ============================================================
# K 線驗證
# ============================================================

def verify_signal(sig, session):
    """用 OANDA/Binance K 線驗證信號"""
    from tvDatafeed import TvDatafeed, Interval

    sym_clean = sig.symbol.replace(".P", "")
    is_crypto = sym_clean.endswith("USDT")

    if is_crypto:
        exchange = "BINANCE"
        tv_sym = sym_clean
    else:
        exchange = "OANDA"
        tv_sym = sym_clean

    tf_map = {"1h": Interval.in_1_hour, "4h": Interval.in_4_hour}
    interval = tf_map.get(sig.timeframe or "1h", Interval.in_1_hour)

    try:
        tv = TvDatafeed()
        df = tv.get_hist(symbol=tv_sym, exchange=exchange, interval=interval, n_bars=200)
        if df is None or df.empty:
            return
    except Exception:
        return

    is_long = sig.side == "long"
    missed = []

    for _, row in df.iterrows():
        t = _.to_pydatetime().replace(tzinfo=None)
        if t < sig.signal_time:
            continue
        if t > sig.signal_time + timedelta(hours=72):
            break

        h, l = float(row["high"]), float(row["low"])

        for level, price, attr in [
            ("TP1", sig.tp1, "actual_tp1"), ("TP2", sig.tp2, "actual_tp2"),
            ("TP3", sig.tp3, "actual_tp3"), ("TP4", sig.tp4, "actual_tp4"),
        ]:
            if price and not getattr(sig, attr):
                hit = (is_long and h >= price) or (not is_long and l <= price)
                if hit:
                    setattr(sig, attr, True)

        if sig.sl and not sig.actual_sl:
            hit = (is_long and l <= sig.sl) or (not is_long and h >= sig.sl)
            if hit:
                sig.actual_sl = True

    # 比對漏跳（排除：已達 TP1 後碰 SL 不算漏）
    tp1_hit = sig.actual_tp1 or sig.reported_tp1
    max_reported = 0
    for i in [1, 2, 3, 4]:
        if getattr(sig, f"reported_tp{i}"):
            max_reported = i

    for i in [1, 2, 3, 4]:
        actual = getattr(sig, f"actual_tp{i}")
        reported = getattr(sig, f"reported_tp{i}")
        if actual and not reported and i > max_reported:
            missed.append(f"TP{i}")

    if sig.actual_sl and not sig.reported_sl and not tp1_hit:
        missed.append("SL")

    sig.missed = ", ".join(missed)
    sig.verified = True
    sig.verified_at = datetime.utcnow()
    session.commit()


# ============================================================
# Sync & Live
# ============================================================

async def sync_history(config):
    """同步歷史訊息"""
    tg = config["telegram"]
    client = TelegramClient(tg["session_name"], tg["api_id"], tg["api_hash"])
    await client.start(phone=tg["phone"])

    session = get_session()

    for ch in tg["channels"]:
        chat_id = ch["chat_id"]
        name = ch["name"]
        logger.info(f"同步 {name}...")

        count = 0
        async for msg in client.iter_messages(chat_id, limit=None):
            if not msg.text:
                continue

            # 去重
            exists = session.query(RawMsg).filter_by(chat_id=str(chat_id), message_id=str(msg.id)).first()
            if exists:
                continue

            raw = RawMsg(
                source=name, chat_id=str(chat_id), message_id=str(msg.id),
                timestamp=msg.date.replace(tzinfo=None) if msg.date else None,
                raw_text=msg.text,
            )
            session.add(raw)

            ts = msg.date.replace(tzinfo=None) if msg.date else datetime.utcnow()
            parsed = parse_message(msg.text, ts)

            if parsed and parsed["type"] == "entry" and parsed.get("key"):
                sig_key = f"{name}_{parsed['key']}"
                if not session.query(Signal).filter_by(signal_key=sig_key).first():
                    sig = Signal(
                        source=name, signal_key=sig_key, symbol=parsed["symbol"],
                        side=parsed["side"], entry=parsed["entry"], sl=parsed["sl"],
                        tp1=parsed.get("tp1"), tp2=parsed.get("tp2"),
                        tp3=parsed.get("tp3"), tp4=parsed.get("tp4"),
                        timeframe=parsed.get("timeframe"), signal_time=ts,
                    )
                    session.add(sig)
                    count += 1

            elif parsed and parsed["type"] == "tp" and parsed.get("key"):
                sig_key = f"{name}_{parsed['key']}"
                sig = session.query(Signal).filter_by(signal_key=sig_key).first()
                if sig:
                    for lv in parsed["levels"]:
                        setattr(sig, f"reported_tp{lv}", True)

            elif parsed and parsed["type"] == "sl" and parsed.get("key"):
                sig_key = f"{name}_{parsed['key']}"
                sig = session.query(Signal).filter_by(signal_key=sig_key).first()
                if sig:
                    sig.reported_sl = True

            if count % 100 == 0 and count > 0:
                session.commit()
                logger.info(f"  {count} 筆信號...")

        session.commit()
        logger.info(f"{name}: {count} 筆新信號")

    await client.disconnect()

    # 第二輪：重新掃描 TP/SL 回報（第一輪因時序問題可能漏掉）
    logger.info("重新掃描 TP/SL 回報...")
    all_raws = session.query(RawMsg).order_by(RawMsg.timestamp.asc()).all()
    tp_sl_updated = 0
    for raw in all_raws:
        if not raw.raw_text:
            continue
        ts = raw.timestamp or datetime.utcnow()
        parsed = parse_message(raw.raw_text, ts)

        if parsed and parsed["type"] == "tp" and parsed.get("key"):
            sig_key = f"{raw.source}_{parsed['key']}"
            sig = session.query(Signal).filter_by(signal_key=sig_key).first()
            if sig:
                changed = False
                for lv in parsed["levels"]:
                    if not getattr(sig, f"reported_tp{lv}"):
                        setattr(sig, f"reported_tp{lv}", True)
                        changed = True
                if changed:
                    tp_sl_updated += 1

        elif parsed and parsed["type"] == "sl" and parsed.get("key"):
            sig_key = f"{raw.source}_{parsed['key']}"
            sig = session.query(Signal).filter_by(signal_key=sig_key).first()
            if sig and not sig.reported_sl:
                sig.reported_sl = True
                tp_sl_updated += 1

    session.commit()
    logger.info(f"補回 {tp_sl_updated} 筆 TP/SL 回報")

    # 重置已驗證信號（TP/SL 回報可能已更新，需重新計算漏跳）
    session.query(Signal).filter_by(verified=True).update({"verified": False})
    session.commit()

    # 驗證所有信號
    unverified = session.query(Signal).filter_by(verified=False).all()
    logger.info(f"驗證 {len(unverified)} 筆信號...")
    for i, sig in enumerate(unverified):
        try:
            verify_signal(sig, session)
        except Exception as e:
            logger.debug(f"驗證失敗 {sig.symbol}: {e}")
        if (i + 1) % 50 == 0:
            logger.info(f"  已驗證 {i + 1}/{len(unverified)}")

    session.close()
    logger.info("同步完成")


def print_report():
    """印出漏跳報告"""
    session = get_session()

    for source in ["CFD", "CRYPTO"]:
        sigs = session.query(Signal).filter_by(source=source, verified=True).all()
        if not sigs:
            continue

        total = len(sigs)
        with_miss = [s for s in sigs if s.missed]
        tp1_rate = sum(1 for s in sigs if s.actual_tp1) / total * 100 if total else 0
        tp4_rate = sum(1 for s in sigs if s.actual_tp4) / total * 100 if total else 0
        sl_rate = sum(1 for s in sigs if s.actual_sl) / total * 100 if total else 0
        miss_rate = len(with_miss) / total * 100 if total else 0

        print(f"\n===== {source} =====")
        print(f"總信號: {total}")
        print(f"TP1 觸達: {tp1_rate:.0f}%")
        print(f"TP4 觸達: {tp4_rate:.0f}%")
        print(f"SL 觸達: {sl_rate:.0f}%")
        print(f"漏跳: {len(with_miss)} 筆 ({miss_rate:.0f}%)")
        print()

        if with_miss:
            print("漏跳明細（最近 20 筆）:")
            for s in with_miss[-20:]:
                reported = []
                for i in [1, 2, 3, 4]:
                    if getattr(s, f"reported_tp{i}"):
                        reported.append(f"TP{i}")
                if s.reported_sl:
                    reported.append("SL")
                rep_str = ", ".join(reported) if reported else "-"
                print(f"  {s.symbol} {s.side.upper()} @ {s.entry}")
                print(f"    已報: {rep_str} | 漏: {s.missed}")

    session.close()


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="CRT Signal Monitor")
    parser.add_argument("command", choices=["sync", "live", "report"], help="sync=同步歷史 live=即時 report=報告")
    args = parser.parse_args()

    config = load_config()
    init_db(config["database"]["url"])

    if args.command == "sync":
        asyncio.run(sync_history(config))
        print_report()

    elif args.command == "report":
        print_report()

    elif args.command == "live":
        print("即時監聽模式 - 按 Ctrl+C 停止")
        asyncio.run(sync_history(config))


if __name__ == "__main__":
    main()

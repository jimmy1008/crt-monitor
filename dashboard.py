"""
CRT Signal Monitor Dashboard - Kawaii Cyber Terminal
Design by Gemini, Logic by Claude
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ============================================================
# Style
# ============================================================

def set_page_style():
    st.set_page_config(page_title="Yuki CRT Monitor", layout="wide", initial_sidebar_state="collapsed")
    st.markdown("""
    <style>
        #MainMenu, footer, header { visibility: hidden; height: 0; }

        .block-container {
            padding: 0.2rem 1.5rem 0.3rem 1.5rem !important;
        }

        .stApp {
            background-color: #1A151A;
            color: #FFC0CB;
            font-family: 'Courier New', Courier, monospace;
        }

        /* Metric - Neon Kawaii */
        [data-testid="stMetric"] {
            background: rgba(26, 21, 26, 0.9);
            border: 1px solid rgba(255, 105, 180, 0.3);
            border-radius: 8px;
            padding: 8px 12px;
        }
        [data-testid="stMetricValue"] {
            background: transparent !important;
            border: none !important;
            color: #FF69B4 !important;
            padding: 0 !important;
            font-size: 1.2rem !important;
            font-weight: 900 !important;
            text-shadow: 0 0 10px rgba(255, 105, 180, 0.6), 0 0 20px rgba(255, 105, 180, 0.3) !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.6rem !important;
            color: #FFC0CB !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        h1, h2, h3 {
            color: #FF69B4 !important;
            text-shadow: 0 0 8px rgba(255, 105, 180, 0.5);
            margin-top: 0.2rem !important;
            margin-bottom: 0.2rem !important;
        }
        h1 { font-size: 1.3rem !important; border-bottom: 2px solid #FF69B4; padding-bottom: 4px; }

        .stButton>button {
            color: #FFC0CB !important;
            background: transparent !important;
            border: 1px solid rgba(255, 105, 180, 0.5) !important;
            border-radius: 6px !important;
            padding: 0.3rem 0.8rem !important;
            font-weight: 600 !important;
            font-size: 0.7rem !important;
            font-family: 'Courier New', monospace !important;
        }
        .stButton>button:hover {
            background: rgba(255, 105, 180, 0.15) !important;
            border-color: #FF69B4 !important;
            color: #FF69B4 !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            border-bottom: 1px solid rgba(255, 105, 180, 0.4);
            gap: 0;
        }
        .stTabs [data-baseweb="tab"] {
            color: #FFC0CB;
            padding: 6px 16px;
            font-size: 0.8rem;
        }
        .stTabs [aria-selected="true"] {
            border-bottom: 2px solid #FF69B4 !important;
            color: #FF69B4 !important;
        }

        .stDataFrame {
            border: 1px solid rgba(255, 105, 180, 0.3);
            border-radius: 8px;
            font-size: 0.8rem;
        }

        .setup-box {
            background: rgba(255, 105, 180, 0.08);
            border: 1px solid rgba(255, 105, 180, 0.4);
            border-radius: 10px;
            padding: 14px;
            margin: 6px 0;
            color: #FFC0CB;
            font-size: 0.82rem;
            line-height: 1.6;
        }

        hr { border-color: rgba(255, 105, 180, 0.2) !important; margin: 0.2rem 0 !important; }
        p { margin-bottom: 0.2rem !important; }

        /* Form */
        [data-testid="stForm"] {
            border: 1px solid rgba(255, 105, 180, 0.3) !important;
            border-radius: 10px;
            padding: 12px !important;
        }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# Config & DB
# ============================================================

def check_config():
    p = Path("config.yaml")
    if not p.exists():
        return False, "not found"
    import yaml
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    tg = cfg.get("telegram", {})
    if not tg.get("api_id") or str(tg["api_id"]) == "YOUR_API_ID":
        return False, "not configured"
    return True, cfg


def check_db():
    if not Path("data/monitor.db").exists():
        return False, 0
    from monitor import init_db, get_session, Signal
    init_db()
    s = get_session()
    count = s.query(Signal).count()
    s.close()
    return count > 0, count


def load_signals(source_filter="all", days=0):
    from monitor import init_db, get_session, Signal
    init_db()
    s = get_session()
    query = s.query(Signal).filter_by(verified=True)
    if source_filter != "all":
        query = query.filter_by(source=source_filter)
    if days > 0:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Signal.signal_time > cutoff)
    sigs = query.order_by(Signal.signal_time.desc()).all()
    s.close()
    return sigs


# ============================================================
# Page: Setup
# ============================================================

def page_setup():
    st.markdown("<h1>Yuki CRT Monitor - 首次設定</h1>", unsafe_allow_html=True)

    config_ok, _ = check_config()

    # Step 1
    st.markdown("### Step 1: Telegram API")

    if config_ok:
        st.success("Telegram API 已設定")
    else:
        st.markdown("""
        <div class="setup-box">
        <b>如何取得 Telegram API？</b><br><br>
        1. 用瀏覽器打開 <a href="https://my.telegram.org" target="_blank" style="color:#FF69B4">my.telegram.org</a><br>
        2. 輸入你的 <b>Telegram 手機號碼</b>登入（會收到驗證碼）<br>
        3. 登入後點選 <b>「API development tools」</b><br>
        4. 填入 App 資訊（隨便填就好）：<br>
        &nbsp;&nbsp;&nbsp;&nbsp;- App title: <code>CRT Monitor</code><br>
        &nbsp;&nbsp;&nbsp;&nbsp;- Short name: <code>crtmonitor</code><br>
        &nbsp;&nbsp;&nbsp;&nbsp;- Platform: 選 <code>Desktop</code><br>
        &nbsp;&nbsp;&nbsp;&nbsp;- 其他留空<br>
        5. 按 <b>Create application</b><br>
        6. 你會看到 <b>App api_id</b>（一串數字）和 <b>App api_hash</b>（一串英數字）<br>
        7. 把這兩個填到下方
        </div>
        """, unsafe_allow_html=True)

        with st.form("setup_form"):
            api_id = st.text_input("API ID（數字）", placeholder="例如: 12345678")
            api_hash = st.text_input("API Hash（英數字串）", placeholder="例如: a1b2c3d4e5f6...")
            phone = st.text_input("手機號碼（含國碼）", placeholder="例如: +886912345678")
            st.caption("以上資料只存在你的電腦本機，不會上傳到任何地方")
            submitted = st.form_submit_button("儲存設定")

        if submitted:
            if not api_id or not api_hash or not phone:
                st.error("請填寫所有欄位")
                return False
            try:
                int(api_id)
            except ValueError:
                st.error("API ID 必須是數字")
                return False

            import yaml
            config_data = {
                "telegram": {
                    "api_id": int(api_id),
                    "api_hash": api_hash,
                    "phone": phone,
                    "session_name": "crt_monitor",
                    "channels": [
                        {"chat_id": -1003706518531, "name": "CFD"},
                        {"chat_id": -1003868559200, "name": "CRYPTO"},
                    ],
                },
                "database": {"url": "sqlite:///data/monitor.db"},
            }
            Path("config.yaml").write_text(
                yaml.dump(config_data, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
            st.success("設定已儲存！")
            st.rerun()
        return False

    # Step 2
    st.markdown("### Step 2: 同步頻道資料")
    has_data, count = check_db()

    if has_data:
        st.success(f"已有 {count} 筆信號")
        if st.button("重新同步"):
            with st.spinner("同步中..."):
                r = subprocess.run(
                    ["python", "monitor.py", "sync"],
                    capture_output=True, text=True, timeout=600,
                    cwd=str(Path(__file__).parent),
                )
                if r.returncode == 0:
                    st.success("完成！")
                    st.rerun()
                else:
                    st.error(f"失敗:\n{r.stderr}")
        return True
    else:
        st.info("尚未同步資料")
        st.caption("第一次同步會在終端機視窗要求輸入 Telegram 驗證碼（手機會收到）")
        if st.button("開始同步"):
            subprocess.Popen(
                ["python", "monitor.py", "sync"],
                cwd=str(Path(__file__).parent),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            st.warning("同步已啟動！請到終端機視窗輸入驗證碼，完成後重新整理此頁面。")
        return False


# ============================================================
# Page: Dashboard
# ============================================================

def page_dashboard():
    # Title + Filters same row
    c_title, c_src, c_days, c_btns = st.columns([4, 1.2, 1, 0.8])
    c_title.markdown("<h1>Yuki CRT Monitor</h1>", unsafe_allow_html=True)
    source = c_src.selectbox("頻道", ["all", "CFD", "CRYPTO"],
                             format_func=lambda x: {"all": "全部", "CFD": "CFD", "CRYPTO": "CRYPTO"}[x])
    days = c_days.selectbox("範圍", [7, 14, 30, 90, 0],
                            format_func=lambda x: f"{x}天" if x else "全部")
    with c_btns:
        st.markdown("<br>", unsafe_allow_html=True)
        bc1, bc2 = st.columns(2)
        do_sync = bc1.button("sync")
        do_upd = bc2.button("update")
        if do_upd:
            with st.spinner("..."):
                updated, errors, no_change = do_update()
            if updated:
                st.toast(f"已更新: {', '.join(updated)}")
                st.rerun()
            elif no_change:
                st.toast("已是最新版本")
            if errors:
                st.error(f"{'; '.join(errors)}")

    if do_sync:
        with st.spinner("同步中..."):
            r = subprocess.run(
                ["python", "monitor.py", "sync"],
                capture_output=True, text=True, timeout=600,
                cwd=str(Path(__file__).parent),
            )
            if r.returncode == 0:
                st.rerun()

    sigs = load_signals(source, days)
    total = len(sigs)

    if total == 0:
        st.info("此範圍無已驗證信號")
        return

    missed_sigs = [s for s in sigs if s.missed]

    # Metrics
    st.markdown("---")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("總信號", total)
    c2.metric("TP1 觸達", f"{sum(1 for s in sigs if s.actual_tp1) / total * 100:.0f}%")
    c3.metric("TP4 觸達", f"{sum(1 for s in sigs if s.actual_tp4) / total * 100:.0f}%")
    c4.metric("SL 觸達", f"{sum(1 for s in sigs if s.actual_sl) / total * 100:.0f}%")
    c5.metric("漏跳數", len(missed_sigs))
    c6.metric("漏跳率", f"{len(missed_sigs) / total * 100:.0f}%")

    st.markdown("---")

    # Tabs
    t1, t2, t3 = st.tabs(["漏跳明細", "完整報告", "統計圖表"])

    with t1:
        if missed_sigs:
            rows = []
            for s in missed_sigs[:100]:
                reported = []
                for i in [1, 2, 3, 4]:
                    if getattr(s, f"reported_tp{i}"):
                        reported.append(f"TP{i}")
                if s.reported_sl:
                    reported.append("SL")
                rows.append({
                    "時間": s.signal_time.strftime("%m/%d %H:%M") if s.signal_time else "",
                    "頻道": s.source,
                    "商品": s.symbol,
                    "方向": s.side.upper(),
                    "進場": s.entry,
                    "已回報": ", ".join(reported) if reported else "-",
                    "漏跳": s.missed,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)
        else:
            st.success("全部正常，無漏跳！")

    with t2:
        rows = []
        for s in sigs[:200]:
            actual, reported = [], []
            for i in [1, 2, 3, 4]:
                if getattr(s, f"actual_tp{i}"): actual.append(f"TP{i}")
                if getattr(s, f"reported_tp{i}"): reported.append(f"TP{i}")
            if s.actual_sl: actual.append("SL")
            if s.reported_sl: reported.append("SL")
            rows.append({
                "時間": s.signal_time.strftime("%m/%d %H:%M") if s.signal_time else "",
                "頻道": s.source,
                "商品": s.symbol,
                "方向": s.side.upper(),
                "進場": s.entry,
                "K線實際": ", ".join(actual) if actual else "-",
                "頻道回報": ", ".join(reported) if reported else "-",
                "漏跳": s.missed if s.missed else "-",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

    with t3:
        col_bar, col_line = st.columns(2)

        with col_bar:
            levels = ["TP1", "TP2", "TP3", "TP4", "SL"]
            actual_vals = [
                sum(1 for s in sigs if s.actual_tp1),
                sum(1 for s in sigs if s.actual_tp2),
                sum(1 for s in sigs if s.actual_tp3),
                sum(1 for s in sigs if s.actual_tp4),
                sum(1 for s in sigs if s.actual_sl),
            ]
            reported_vals = [
                sum(1 for s in sigs if s.reported_tp1),
                sum(1 for s in sigs if s.reported_tp2),
                sum(1 for s in sigs if s.reported_tp3),
                sum(1 for s in sigs if s.reported_tp4),
                sum(1 for s in sigs if s.reported_sl),
            ]

            fig = go.Figure()
            fig.add_trace(go.Bar(name="K線實際", x=levels, y=actual_vals, marker_color="#FF69B4"))
            fig.add_trace(go.Bar(name="頻道回報", x=levels, y=reported_vals, marker_color="#FFC0CB"))
            fig.update_layout(
                barmode="group",
                paper_bgcolor="#1A151A", plot_bgcolor="#1A151A",
                height=440, title=dict(text="K線實際 vs 頻道回報", font=dict(color="#FFC0CB", size=13)),
                font=dict(color="#FFC0CB", size=10, family="Courier New"),
                xaxis=dict(gridcolor="rgba(255,105,180,0.1)"),
                yaxis=dict(gridcolor="rgba(255,105,180,0.1)"),
                legend=dict(font=dict(size=10)),
                margin=dict(l=40, r=20, t=40, b=30),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_line:
            by_date = {}
            for s in sigs:
                if not s.signal_time: continue
                d = s.signal_time.strftime("%m/%d")
                if d not in by_date:
                    by_date[d] = {"total": 0, "missed": 0}
                by_date[d]["total"] += 1
                if s.missed:
                    by_date[d]["missed"] += 1

            if by_date:
                dates = sorted(by_date.keys())
                rates = [by_date[d]["missed"] / by_date[d]["total"] * 100 for d in dates]
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=dates, y=rates, mode="lines+markers",
                    line=dict(color="#FF69B4", width=2),
                    marker=dict(size=6, color="#FFC0CB", line=dict(color="#FF69B4", width=1)),
                ))
                fig2.update_layout(
                    paper_bgcolor="#1A151A", plot_bgcolor="#1A151A",
                    height=440, title=dict(text="每日漏跳率 (%)", font=dict(color="#FFC0CB", size=13)),
                    yaxis_title="%",
                    font=dict(color="#FFC0CB", size=10, family="Courier New"),
                    xaxis=dict(gridcolor="rgba(255,105,180,0.1)"),
                    yaxis=dict(gridcolor="rgba(255,105,180,0.1)"),
                    margin=dict(l=40, r=20, t=40, b=30),
                )
                st.plotly_chart(fig2, use_container_width=True)


# ============================================================
# Main
# ============================================================

# ============================================================
# Update
# ============================================================

# 改成你的 GitHub repo（建好後填）
GITHUB_RAW = "https://raw.githubusercontent.com/jimmy1008/crt-monitor/main"
UPDATE_FILES = ["monitor.py", "dashboard.py", "requirements.txt"]


def do_update():
    """從 GitHub 下載最新代碼，比對是否有變更"""
    import httpx
    updated = []
    errors = []
    no_change = True

    for fname in UPDATE_FILES:
        try:
            url = f"{GITHUB_RAW}/{fname}"
            r = httpx.get(url, timeout=15, follow_redirects=True)
            if r.status_code == 200:
                new_content = r.text
                # 比對本地檔案
                local = Path(fname)
                if local.exists() and local.read_text(encoding="utf-8") == new_content:
                    continue  # 沒變
                local.write_text(new_content, encoding="utf-8")
                updated.append(fname)
                no_change = False
            elif r.status_code == 404:
                continue  # repo 還沒建，跳過
            else:
                errors.append(f"{fname}: HTTP {r.status_code}")
        except Exception as e:
            errors.append(f"{fname}: {e}")

    return updated, errors, no_change


def main():
    set_page_style()

    has_data, count = check_db()
    config_ok, _ = check_config()

    if not config_ok or not has_data:
        ready = page_setup()
        if ready:
            page_dashboard()
    else:
        page_dashboard()


if __name__ == "__main__":
    main()

# Standalone daily signal exporter for Scheme A PWA (GitHub Actions & Local)
# Strictly reuses the audited V2 Dual-Tranche Multi-Asset Dual Momentum logic.
# Outputs ONLY public market signal data to docs/signal_latest.json (ZERO personal data).

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "signal_latest.json"

HORIZONS = (63, 126, 252)
CAP_LEV = 0.50

ASSET_META = {
    "1579": {"yf": "1579.T", "raw": "1579", "name": "日経ブル2倍(1579)", "short": "日股 2x", "lot": 10, "is_lev": True, "fee": "0.99%"},
    "1458": {"yf": "1458.T", "raw": "1458", "name": "楽天 日経225レバ 2x", "short": "日股 2x", "lot": 1, "is_lev": True, "fee": "0.88%"},
    "1321": {"yf": "1321.T", "raw": "1321", "name": "NF 日経225 1x", "short": "日股 1x", "lot": 10, "is_lev": False, "fee": "0.12%"},
    "1545": {"yf": "1545.T", "raw": "1545", "name": "NF ナスダック100", "short": "纳指 100", "lot": 10, "is_lev": False, "fee": "0.22%"},
    "2631": {"yf": "2631.T", "raw": "2631", "name": "MAXIS ナスダック100", "short": "纳指 100", "lot": 1, "is_lev": False, "fee": "0.22%"},
    "314A": {"yf": "314A.T", "raw": "314A", "name": "iShares 黄金(円)", "short": "实物黄金", "lot": 10, "is_lev": False, "fee": "0.22%"},
}

# Built-in JPX TSE market holidays fallback (2025-2028) including Dec 31 & Jan 1-3 closures
TSE_HOLIDAYS_FALLBACK = {
    # 2025
    "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-13", "2025-02-11", "2025-02-24",
    "2025-03-20", "2025-04-29", "2025-05-03", "2025-05-04", "2025-05-05", "2025-05-06",
    "2025-07-21", "2025-08-11", "2025-09-15", "2025-09-23", "2025-10-13", "2025-11-03",
    "2025-11-24", "2025-12-31",
    # 2026
    "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-12", "2026-02-11", "2026-02-23",
    "2026-03-20", "2026-04-29", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06",
    "2026-07-20", "2026-08-11", "2026-09-21", "2026-09-22", "2026-09-23", "2026-10-12",
    "2026-11-03", "2026-11-23", "2026-12-31",
    # 2027
    "2027-01-01", "2027-01-02", "2027-01-03", "2027-01-11", "2027-02-11", "2027-02-23",
    "2027-03-22", "2027-04-29", "2027-05-03", "2027-05-04", "2027-05-05", "2027-07-19",
    "2027-08-11", "2027-09-20", "2027-09-23", "2027-10-11", "2027-11-03", "2027-11-23",
    "2027-12-31",
    # 2028
    "2028-01-01", "2028-01-02", "2028-01-03", "2028-01-10", "2028-02-11", "2028-02-23",
    "2028-03-20", "2028-04-29", "2028-05-03", "2028-05-04", "2028-05-05", "2028-07-17",
    "2028-08-11", "2028-09-18", "2028-09-22", "2028-10-09", "2028-11-03", "2028-11-23",
    "2028-12-31",
}


def is_tse_trading_day(d: date) -> bool:
    """True if `d` is an open Tokyo Stock Exchange business day."""
    if d.weekday() >= 5:
        return False
    if (d.month == 12 and d.day == 31) or (d.month == 1 and d.day in (1, 2, 3)):
        return False
    if d.isoformat() in TSE_HOLIDAYS_FALLBACK:
        return False
    try:
        import jpholiday  # optional in local env, installed in GitHub Actions
        if jpholiday.is_holiday(d):
            return False
    except ImportError:
        pass
    return True


def list_month_tse_days(year: int, month: int) -> list[date]:
    d = date(year, month, 1)
    out = []
    while d.month == month:
        if is_tse_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def compute_next_rebal_info(asof_date: date, mode: str) -> dict:
    """Compute exact upcoming TSE rebalance dates (Day 1 & Day 11 for Mode A; Day 1 for Mode C)."""
    is_open = is_tse_trading_day(asof_date)
    cur_days = list_month_tse_days(asof_date.year, asof_date.month)
    ny, nm = (asof_date.year + 1, 1) if asof_date.month == 12 else (asof_date.year, asof_date.month + 1)
    next_days = list_month_tse_days(ny, nm)

    candidates: list[tuple[date, str]] = []
    if len(cur_days) >= 1:
        candidates.append((cur_days[0], "切片 A（本月第1交易日）" if mode == "A" else "月度调仓（本月第1交易日）"))
    if mode == "A" and len(cur_days) >= 11:
        candidates.append((cur_days[10], "切片 B（本月第11交易日）"))
    if len(next_days) >= 1:
        candidates.append((next_days[0], "切片 A（下月第1交易日）" if mode == "A" else "月度调仓（下月第1交易日）"))
    if mode == "A" and len(next_days) >= 11:
        candidates.append((next_days[10], "切片 B（下月第11交易日）"))

    # Next strictly upcoming (or today if today is a rebalance day)
    next_dt, next_lbl = None, ""
    for dt, lbl in candidates:
        if dt > asof_date:
            next_dt, next_lbl = dt, lbl
            break

    # Count TSE trading days from asof_date to next_dt
    td_until = 0
    if next_dt:
        cur = asof_date + timedelta(days=1)
        while cur <= next_dt:
            if is_tse_trading_day(cur):
                td_until += 1
            cur += timedelta(days=1)

    wd_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return {
        "is_tse_open_today": is_open,
        "today_weekday": wd_cn[asof_date.weekday()],
        "next_rebal_date": next_dt.isoformat() if next_dt else "",
        "next_rebal_weekday": wd_cn[next_dt.weekday()] if next_dt else "",
        "next_rebal_label": next_lbl,
        "trading_days_until_next": td_until,
    }


def _fetch_one_yf(symbol: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.Ticker(symbol).history(start=start, end=end, interval="1d", auto_adjust=False, actions=True)
    if df is None or df.empty:
        raise RuntimeError(f"Yahoo Finance 返回空数据: {symbol}")
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _load_one_csv(raw_dir: Path, raw_name: str) -> pd.DataFrame:
    p = raw_dir / f"{raw_name}.csv"
    if not p.exists():
        raise FileNotFoundError(f"离线缓存不存在: {p}")
    df = pd.read_csv(p, parse_dates=["Date"], index_col="Date").sort_index()
    return df[~df.index.duplicated(keep="last")]


def _sanitize_etf_series(code: str, df: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    """Clean known Yahoo split glitches and warn on any new >25% single-day jump."""
    warnings: list[str] = []
    s = df["Close"].astype(float).copy()
    if code == "1579":
        for dt in ["2021-03-03", "2021-03-04"]:
            ts = pd.Timestamp(dt)
            if ts in s.index and 5000.0 < s.loc[ts] < 12000.0:
                s.loc[ts] *= 2.0
        mask_pre = (s.index < pd.Timestamp("2024-06-28")) & (s > 5000.0)
        s.loc[mask_pre] /= 100.0
        ts24 = pd.Timestamp("2024-07-01")
        if ts24 in s.index and s.loc[ts24] < 20.0:
            s.loc[ts24] *= 100.0
    elif code == "1545":
        mask_pre = (s.index < pd.Timestamp("2026-05-22")) & (s > 5000.0)
        s.loc[mask_pre] /= 200.0
        ts25 = pd.Timestamp("2026-05-25")
        if ts25 in s.index and s.loc[ts25] < 20.0:
            s.loc[ts25] *= 200.0
    elif code == "314A":
        s = s.loc["2025-01-17":]
    elif code == "1321":
        for dt in ["2026-10-05", "2026-10-06"]:
            ts = pd.Timestamp(dt)
            if ts in s.index and s.loc[ts] < 50.0:
                s.loc[ts] *= 100.0

    r = s.tail(300).pct_change()
    bad = r[r.abs() > 0.25]
    for dt, val in bad.items():
        warnings.append(
            f"异常报价警报: {code}.T 在 {dt.date()} 单日变动 {val*100:+.2f}% "
            f"(Close={s.loc[dt]:.2f})！请先在券商核对是否拆股或 Yahoo 报错再下单。"
        )
    return s, warnings


def compute_single_tranche(sig_df: pd.DataFrame, signal_idx: int, jp_code: str, us_code: str) -> dict:
    assets = [jp_code, us_code, "314A"]
    sub = sig_df[assets].iloc[: signal_idx + 1]
    sig_date = sub.index[-1]

    metrics = {}
    for a in assets:
        s = sub[a]
        r63 = float(s.iloc[-1] / s.iloc[-1 - 63] - 1.0)
        r126 = float(s.iloc[-1] / s.iloc[-1 - 126] - 1.0)
        r252 = float(s.iloc[-1] / s.iloc[-1 - 252] - 1.0)
        mom = (r63 + r126 + r252) / 3.0
        rv60 = float(s.pct_change().iloc[-60:].std(ddof=1) * np.sqrt(252.0))
        score = mom / max(rv60, 0.05)
        metrics[a] = {
            "r63": round(r63, 6),
            "r126": round(r126, 6),
            "r252": round(r252, 6),
            "mom": round(mom, 6),
            "rv60": round(rv60, 6),
            "score": round(score, 6),
        }

    ranked = sorted(assets, key=lambda x: metrics[x]["score"], reverse=True)
    top2 = ranked[:2]
    pos_sel = [a for a in top2 if metrics[a]["mom"] > 0.0]

    cap_jp = CAP_LEV if ASSET_META[jp_code]["is_lev"] else 1.0
    weights = {a: 0.0 for a in assets}

    if len(pos_sel) == 2:
        inv_v = {a: 1.0 / max(metrics[a]["rv60"], 0.05) for a in pos_sel}
        tot_iv = sum(inv_v.values())
        for a in pos_sel:
            weights[a] = inv_v[a] / tot_iv
        if weights[jp_code] > cap_jp:
            excess = weights[jp_code] - cap_jp
            weights[jp_code] = cap_jp
            other = [a for a in pos_sel if a != jp_code][0]
            weights[other] += excess
    elif len(pos_sel) == 1:
        a = pos_sel[0]
        weights[a] = min(0.50, cap_jp) if a == jp_code else 0.50

    weights = {a: round(weights[a], 6) for a in assets}
    cash_w = round(max(0.0, 1.0 - sum(weights.values())), 6)
    return {
        "signal_date": str(sig_date.date()),
        "ranked": ranked,
        "top2": top2,
        "positive": pos_sel,
        "weights": weights,
        "cash_weight": cash_w,
        "metrics": metrics,
    }


def locate_tranche_indices(closed_cal: pd.DatetimeIndex, asof: pd.Timestamp, is_tse_open: bool) -> dict:
    cur_ym = asof.to_period("M")
    ym_series = closed_cal.to_period("M")
    in_cur_pos = np.where(ym_series == cur_ym)[0]
    completed_cur = len(in_cur_pos)
    today_td_num = (completed_cur + 1) if is_tse_open else completed_cur

    before_cur = np.where(ym_series < cur_ym)[0]
    if len(before_cur) == 0:
        raise RuntimeError("找不到上月末交易日以计算切片 A。")
    tr_a_idx = int(before_cur[-1])

    if completed_cur >= 10:
        tr_b_idx = int(in_cur_pos[9])
        tr_b_label = f"{cur_ym} 第10交易日收盘 (本月切片B)"
    else:
        prev_ym = ym_series[tr_a_idx]
        in_prev_pos = np.where(ym_series == prev_ym)[0]
        tr_b_idx = int(in_prev_pos[min(9, len(in_prev_pos) - 1)])
        tr_b_label = f"{prev_ym} 第10交易日收盘 (上月切片B)"

    is_a_day = is_tse_open and (today_td_num == 1)
    is_b_day = is_tse_open and (today_td_num == 11)
    return {
        "cur_month": str(cur_ym),
        "completed_cur_month": int(completed_cur),
        "today_td_num": int(today_td_num),
        "is_tranche_a_day": is_a_day,
        "is_tranche_b_day": is_b_day,
        "is_rebal_day_A": is_a_day or is_b_day,
        "is_rebal_day_C": is_a_day,
        "tr_a_idx": tr_a_idx,
        "tr_b_idx": tr_b_idx,
        "tr_b_label": tr_b_label,
    }


def build_payload(asof_date: date, offline_raw_dir: Path | None) -> dict:
    asof = pd.Timestamp(asof_date).normalize()
    start_str = (asof - timedelta(days=920)).strftime("%Y-%m-%d")
    end_str = (asof + timedelta(days=2)).strftime("%Y-%m-%d")

    symbols = {
        "N225": ("^N225", "N225"),
        "NDX": ("^NDX", "NDX"),
        "GCF": ("GC=F", "GCF"),
        "USDJPY": ("JPY=X", "USDJPY"),
        "1579": ("1579.T", "1579"),
        "1458": ("1458.T", "1458"),
        "1321": ("1321.T", "1321"),
        "1545": ("1545.T", "1545"),
        "314A": ("314A.T", "314A"),
    }

    raw_dfs = {}
    for k, (yf_sym, csv_name) in symbols.items():
        if offline_raw_dir is not None:
            raw_dfs[k] = _load_one_csv(offline_raw_dir, csv_name)
        else:
            raw_dfs[k] = _fetch_one_yf(yf_sym, start_str, end_str)

    warnings: list[str] = []
    clean_etf: dict[str, pd.Series] = {}
    for code in ["1579", "1458", "1321", "1545", "314A"]:
        s, ws = _sanitize_etf_series(code, raw_dfs[code])
        clean_etf[code] = s
        warnings.extend(ws)

    # Reliable Tokyo trading calendar from intersection of core TSE ETFs
    tokyo_cal = clean_etf["1579"].index.intersection(clean_etf["1545"].index)
    tokyo_cal = tokyo_cal[tokyo_cal <= asof].sort_values()
    closed_cal = tokyo_cal[tokyo_cal < asof]
    if len(closed_cal) < 260:
        raise RuntimeError(f"有效东京交易日不足 260 天（当前 {len(closed_cal)} 天）。")

    last_closed_tokyo = closed_cal[-1]
    if (asof - last_closed_tokyo).days > 6:
        warnings.append(f"数据陈旧警告：最近已收盘东京交易日为 {last_closed_tokyo.date()}，距今超过 6 天。")

    # Align foreign closes strictly < asof (06:00 JST US close prior to Tokyo day `asof`)
    ndx_c = raw_dfs["NDX"]["Close"].astype(float)
    gcf_c = raw_dfs["GCF"]["Close"].astype(float)
    fx_c = raw_dfs["USDJPY"]["Close"].astype(float)

    ndx_al = ndx_c[ndx_c.index < asof].reindex(closed_cal, method="ffill")
    gcf_al = gcf_c[gcf_c.index < asof].reindex(closed_cal, method="ffill")
    fx_al = fx_c[fx_c.index < asof].reindex(closed_cal, method="ffill")

    r_us = (ndx_al * fx_al).pct_change().fillna(0.0) - 0.0022 / 252.0
    r_au = (gcf_al * fx_al).pct_change().fillna(0.0) - 0.0022 / 252.0

    sig_df = pd.DataFrame({
        "1579": clean_etf["1579"].reindex(closed_cal).ffill(),
        "1458": clean_etf["1458"].reindex(closed_cal).ffill(),
        "1321": clean_etf["1321"].reindex(closed_cal).ffill(),
        "1545": (1.0 + r_us).cumprod() * 100.0,
        "314A": (1.0 + r_au).cumprod() * 100.0,
    }, index=closed_cal)

    # Cross-check 1579 vs 2*N225 on last closed day
    n225_c = raw_dfs["N225"]["Close"].astype(float)
    if last_closed_tokyo in n225_c.index and len(closed_cal) >= 2 and closed_cal[-2] in n225_c.index:
        r_jp = float(sig_df["1579"].iloc[-1] / sig_df["1579"].iloc[-2] - 1.0)
        r_n = float(n225_c.loc[last_closed_tokyo] / n225_c.loc[closed_cal[-2]] - 1.0)
        if abs(r_jp - 2.0 * r_n) > 0.04:
            warnings.append(f"跟踪偏离警告: 1579.T 最近一日涨幅 {r_jp*100:+.2f}% vs 2×N225 {2*r_n*100:+.2f}%，请核对行情。")

    # Latest known board prices & 1-day change
    latest_prices: dict[str, dict] = {}
    for code in ["1579", "1458", "1321", "1545", "314A"]:
        sub = clean_etf[code][clean_etf[code].index <= asof].dropna()
        p_now = float(sub.iloc[-1])
        p_prev = float(sub.iloc[-2]) if len(sub) >= 2 else p_now
        chg = (p_now / p_prev - 1.0) if p_prev > 0 else 0.0
        latest_prices[code] = {
            "price": round(p_now, 2),
            "date": str(sub.index[-1].date()),
            "chg_1d": round(chg, 6),
        }

    next_info_A = compute_next_rebal_info(asof_date, "A")
    next_info_C = compute_next_rebal_info(asof_date, "C")
    cal_info = locate_tranche_indices(closed_cal, asof, next_info_A["is_tse_open_today"])

    presets_spec = {
        "A_1579": {"label": "方案 A · 标准版 (1579 + 1545 + 314A)", "mode": "A", "jp": "1579", "us": "1545", "next": next_info_A},
        "A_1458": {"label": "方案 A · 300万+版 (1458 + 1545 + 314A)", "mode": "A", "jp": "1458", "us": "1545", "next": next_info_A},
        "C_1321": {"label": "方案 C · NISA零杠杆 (1321 + 1545 + 314A)", "mode": "C", "jp": "1321", "us": "1545", "next": next_info_C},
    }

    presets_out = {}
    for key, sp in presets_spec.items():
        jp, us, mode = sp["jp"], sp["us"], sp["mode"]
        assets = [jp, us, "314A"]
        tr_a = compute_single_tranche(sig_df, cal_info["tr_a_idx"], jp, us)
        tr_b = compute_single_tranche(sig_df, cal_info["tr_b_idx"], jp, us)
        if mode == "A":
            target_w = {a: round(0.5 * tr_a["weights"][a] + 0.5 * tr_b["weights"][a], 6) for a in assets}
            is_rebal = cal_info["is_rebal_day_A"]
        else:
            target_w = dict(tr_a["weights"])
            is_rebal = cal_info["is_rebal_day_C"]
        target_cash = round(max(0.0, 1.0 - sum(target_w.values())), 6)
        presets_out[key] = {
            "label": sp["label"],
            "mode": mode,
            "assets": assets,
            "is_rebal_today": is_rebal,
            "next_rebal": sp["next"],
            "target_weights": target_w,
            "target_cash": target_cash,
            "tranche_a": tr_a,
            "tranche_b": tr_b if mode == "A" else None,
        }

    now_jst = datetime.now(JST)
    last_us_dt = str(ndx_c[ndx_c.index < asof].index.max().date())
    return {
        "schema_version": 1,
        "generated_at_jst": now_jst.strftime("%Y-%m-%d %H:%M JST"),
        "asof_date": asof_date.isoformat(),
        "data_source": "offline_cache" if offline_raw_dir else "yahoo_live",
        "last_tokyo_date": str(last_closed_tokyo.date()),
        "last_us_date": last_us_dt,
        "calendar": {
            "cur_month": cal_info["cur_month"],
            "today_td_num": cal_info["today_td_num"],
            "is_tse_open_today": next_info_A["is_tse_open_today"],
            "today_weekday": next_info_A["today_weekday"],
            "is_tranche_a_day": cal_info["is_tranche_a_day"],
            "is_tranche_b_day": cal_info["is_tranche_b_day"],
            "tranche_b_label": cal_info["tr_b_label"],
        },
        "warnings": warnings,
        "asset_meta": ASSET_META,
        "latest_prices": latest_prices,
        "presets": presets_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="导出方案 A 实盘公开信号 JSON（供 GitHub Pages PWA 使用）")
    parser.add_argument("--asof", type=str, default=None, help="指定 JST 日期 YYYY-MM-DD（默认当前东京日期）")
    parser.add_argument("--offline-dir", type=str, default=None, help="离线调试：指定本地 data/raw 目录")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT), help="输出 JSON 路径")
    args = parser.parse_args()

    asof_date = date.fromisoformat(args.asof) if args.asof else datetime.now(JST).date()
    offline_dir = Path(args.offline_dir) if args.offline_dir else None

    payload = build_payload(asof_date, offline_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    p_a = payload["presets"]["A_1579"]
    w_str = ", ".join(f"{k}={v*100:.1f}%" for k, v in p_a["target_weights"].items())
    print(f"[OK] Exported {out_path} | asof={payload['asof_date']} | tokyo={payload['last_tokyo_date']} | us={payload['last_us_date']}")
    print(f"     A_1579 target: {w_str}, Cash={p_a['target_cash']*100:.1f}% | rebal_today={p_a['is_rebal_today']} | warnings={len(payload['warnings'])}")


if __name__ == "__main__":
    main()

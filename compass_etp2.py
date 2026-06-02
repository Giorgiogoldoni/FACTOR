#!/usr/bin/env python3
"""
COMPASS ETP2 — compass_etp2.py v1.0  IWMO Timing
══════════════════════════════════════════════════════════════════════
Strategia semplicissima:
  - Tieni IWMO.MI al 100% finché va bene
  - Esci progressivamente su XEON quando IWMO dà segnali di crisi
  - Rientra su IWMO quando i segnali si disattivano

SEGNALI DI USCITA (identici a IWMO+)
  S1 — Mom 1M IWMO < 0
  S2 — Prezzo IWMO < KAMA(IWMO) e KAMA in discesa
  S3 — IWMO sotto massimo 60gg di oltre 10%

  0 segnali → 100% IWMO
  1 segnale → 70% IWMO + 30% XEON
  2 segnali → 30% IWMO + 70% XEON
  3 segnali → 100% XEON

Output: data/compass_etp2.json
"""

import json, math, datetime, time, urllib.request
from pathlib import Path
from collections import defaultdict

# ── CONFIGURAZIONE ──────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
OUT_FILE       = BASE_DIR / "data" / "compass_etp2.json"
BACKTEST_START = "2024-01-01"
CAPITALE       = 100_000
BENCHMARK      = "IWMO.MI"
BENCHMARK2     = "VWCE.DE"
REBAL_DAYS     = 10

# ── UTILITIES ────────────────────────────────────────────────────────────────
def fetch_yahoo(ticker, days=900):
    end   = int(datetime.datetime.utcnow().timestamp())
    start = end - days * 86400
    url   = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
             f"?interval=1d&period1={start}&period2={end}&events=history")
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            result = data.get("chart", {}).get("result")
            if not result: time.sleep(2); continue
            ts  = result[0]["timestamp"]
            q   = result[0]["indicators"]["quote"][0]
            adj = result[0]["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
            dates  = [datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d") for t in ts]
            closes = [float(v) if v else None for v in adj]
            valid  = [(d, c) for d, c in zip(dates, closes) if c]
            if len(valid) < 60: return None
            d, c = zip(*valid)
            return {"dates": list(d), "closes": list(c)}
        except Exception:
            time.sleep(2 * attempt + 1)
    return None

def closes_at(data, ticker, target_date):
    d = data.get(ticker)
    if not d: return []
    n = min(len(d["closes"]), len(d["dates"]))
    return [d["closes"][i] for i in range(n) if d["dates"][i] <= target_date]

def get_price_on_date(data, ticker, target_date):
    cl = closes_at(data, ticker, target_date)
    return cl[-1] if cl else None

# ── INDICATORI ────────────────────────────────────────────────────────────────
def calc_mom(closes, days):
    if len(closes) <= days: return None
    old = closes[-(days + 1)]
    return round((closes[-1] - old) / old * 100, 2) if old else None

def calc_kama(closes, period=10, fast=2, slow=30):
    if len(closes) < period + 2: return None, None, 0
    fast_sc = 2 / (fast + 1)
    slow_sc = 2 / (slow + 1)
    kama = closes[period]
    kama_series = [kama]
    for i in range(period + 1, len(closes)):
        direction  = abs(closes[i] - closes[i - period])
        volatility = sum(abs(closes[j] - closes[j-1]) for j in range(i - period + 1, i + 1))
        er  = direction / volatility if volatility else 0
        sc  = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama = kama + sc * (closes[i] - kama)
        kama_series.append(kama)
    kama_now  = kama_series[-1]
    kama_prev = kama_series[-2] if len(kama_series) >= 2 else kama_now
    direzione = 1 if kama_now > kama_prev else (-1 if kama_now < kama_prev else 0)
    return round(kama_now, 4), round(kama_prev, 4), direzione

def calc_er(closes, period=20):
    if len(closes) <= period: return 0.0
    direction  = abs(closes[-1] - closes[-period - 1])
    volatility = sum(abs(closes[i] - closes[i-1]) for i in range(-period, 0))
    return round(direction / volatility, 4) if volatility else 0.0

# ── SEGNALI IWMO ─────────────────────────────────────────────────────────────
def calc_segnali_iwmo(closes_iwmo):
    if not closes_iwmo or len(closes_iwmo) < 130:
        return 0, {"s1": False, "s2": False, "s3": False,
                   "n_segnali": 0, "descrizione": "Dati insufficienti"}

    m1 = calc_mom(closes_iwmo, 21)
    s1 = (m1 is not None and m1 < 0)

    kama_now, kama_prev, kama_dir = calc_kama(closes_iwmo)
    price = closes_iwmo[-1]
    s2 = (kama_now is not None and price < kama_now and kama_dir < 0)

    if len(closes_iwmo) >= 60:
        max_60 = max(closes_iwmo[-60:])
        s3 = (price < max_60 * 0.90)
    else:
        s3 = False

    n = sum([s1, s2, s3])

    desc = []
    desc.append(f"S1{'✓' if s1 else '✗'} Mom1M={m1:+.1f}%" if m1 is not None else "S1✗")
    desc.append(f"S2{'✓' if s2 else '✗'} Prezzo{'<' if s2 else '>'}KAMA({kama_now:.2f})" if kama_now else "S2✗")
    if len(closes_iwmo) >= 60:
        max_60 = max(closes_iwmo[-60:])
        pct_down = (max_60 - price) / max_60 * 100
        desc.append(f"S3{'✓' if s3 else '✗'} -{pct_down:.1f}% da max60gg")
    else:
        desc.append("S3✗")

    return n, {
        "s1": s1, "s2": s2, "s3": s3,
        "n_segnali": n,
        "mom1m_iwmo":    round(m1, 2) if m1 is not None else None,
        "kama_iwmo":     round(kama_now, 4) if kama_now else None,
        "kama_dir_iwmo": kama_dir,
        "price_iwmo":    round(price, 4),
        "descrizione":   " | ".join(desc),
    }

def quota_iwmo(n_segnali):
    return [1.0, 0.7, 0.3, 0.0][min(n_segnali, 3)]

# ── COMMENTO TECNICO IWMO TIMING ──────────────────────────────────────────────
def genera_commento_timing(n_segnali, seg, qa, prev_n=None):
    livelli = ["100% IWMO — nessun segnale attivo, massima esposizione momentum",
               "70% IWMO + 30% XEON — primo segnale: momentum 1M negativo",
               "30% IWMO + 70% XEON — due segnali: trend KAMA invertito",
               "100% XEON — tutti i segnali attivi, protezione totale"]
    commento = livelli[min(n_segnali, 3)]

    if prev_n is not None and prev_n != n_segnali:
        if n_segnali > prev_n:
            commento += f" — ⚠️ aumentata protezione (da {prev_n} a {n_segnali} segnali)"
        else:
            commento += f" — ✅ ridotta protezione, rientro parziale (da {prev_n} a {n_segnali} segnali)"

    # Dettaglio tecnico
    m1 = seg.get("mom1m_iwmo")
    kama = seg.get("kama_iwmo")
    if m1 is not None:
        commento += f". IWMO mom1M={m1:+.1f}%"
    if kama:
        commento += f", KAMA={kama:.2f}"
        if seg.get("kama_dir_iwmo", 0) > 0:
            commento += "↑"
        elif seg.get("kama_dir_iwmo", 0) < 0:
            commento += "↓"

    return commento

# ── BACKTEST IWMO TIMING ──────────────────────────────────────────────────────
def run_backtest_timing(etf_data, backtest_start, oggi):
    all_dates = []
    for d in etf_data.values():
        all_dates.extend(d.get("dates", []))
    all_dates = sorted(set(d for d in all_dates
                          if backtest_start <= d <= oggi))

    rebal_dates = [all_dates[i] for i in range(0, len(all_dates), REBAL_DAYS)]
    if all_dates and all_dates[-1] not in rebal_dates:
        rebal_dates.append(all_dates[-1])

    versioni          = []
    capitale_corrente = float(CAPITALE)
    rendimenti        = {}
    storia_segnali    = []
    prev_n_segnali    = 0

    for idx, rdate in enumerate(rebal_dates):
        # Segnali IWMO
        cl_iwmo = closes_at(etf_data, "IWMO.MI", rdate)
        n_seg, seg_det = calc_segnali_iwmo(cl_iwmo)
        storia_segnali.append({"data": rdate, "n_segnali": n_seg, **seg_det})

        qa = quota_iwmo(n_seg)
        peso_iwmo = round(qa * 100, 1)
        peso_xeon = round((1 - qa) * 100, 1)

        commento = genera_commento_timing(n_seg, seg_det, qa, prev_n_segnali if idx > 0 else None)

        # Composizione
        composizione = []
        if peso_iwmo > 0:
            kama_now, _, kama_dir = calc_kama(cl_iwmo) if cl_iwmo else (None, None, 0)
            er_val = calc_er(cl_iwmo) if cl_iwmo else 0
            composizione.append({
                "ticker":      "IWMO.MI",
                "nome":        "iShares MSCI World Momentum",
                "cat":         "az_globale",
                "sub":         "GLOBAL_MOM",
                "peso":        peso_iwmo,
                "mom6m":       calc_mom(cl_iwmo, 126) if cl_iwmo else None,
                "mom3m":       calc_mom(cl_iwmo, 63)  if cl_iwmo else None,
                "mom1m":       calc_mom(cl_iwmo, 21)  if cl_iwmo else None,
                "er":          round(er_val, 3),
                "kama":        round(kama_now, 4) if kama_now else None,
                "kama_dir":    kama_dir,
                "data_ingresso": backtest_start,
                "azione":      "MANTIENI" if n_seg == 0 else "RIDUCI",
                "commento":    commento,
            })
        if peso_xeon > 0:
            composizione.append({
                "ticker":    "XEON.MI",
                "nome":      "Xtrackers EUR Overnight",
                "cat":       "monetario",
                "sub":       "CASH",
                "peso":      peso_xeon,
                "mom6m": None, "mom3m": None, "mom1m": None,
                "er": 1.0, "kama": None, "kama_dir": 0,
                "data_ingresso": rdate if n_seg > 0 else None,
                "azione":   "CASH",
                "commento": f"Protezione — {n_seg} segnale/i attiv{'o' if n_seg==1 else 'i'}",
            })

        # Rendimento dal periodo precedente
        if idx > 0 and versioni and rebal_dates[idx-1] < rdate:
            prev_date = rebal_dates[idx - 1]
            ptf_ret   = 0.0
            prev_comp = versioni[-1]["composizione"]
            for pos in prev_comp:
                t = pos["ticker"]
                d = etf_data.get(t)
                if not d: continue
                n  = min(len(d["closes"]), len(d["dates"]))
                pp = next((d["closes"][i] for i in range(n-1,-1,-1) if d["dates"][i] <= prev_date), None)
                pn = next((d["closes"][i] for i in range(n-1,-1,-1) if d["dates"][i] <= rdate), None)
                if pp and pn and pp > 0:
                    ptf_ret += (pn - pp) / pp * pos["peso"] / 100
            capitale_corrente  = round(capitale_corrente * (1 + ptf_ret), 2)
            rendimenti[rdate]  = round(ptf_ret * 100, 4)

        for c in composizione:
            c["importo"] = round(capitale_corrente * c["peso"] / 100, 2)

        versioni.append({
            "data":         rdate,
            "n_segnali":    n_seg,
            "segnali":      seg_det,
            "quota_iwmo":   peso_iwmo,
            "quota_xeon":   peso_xeon,
            "composizione": composizione,
            "capitale":     round(capitale_corrente, 2),
        })
        prev_n_segnali = n_seg

    # ── Metriche ──────────────────────────────────────────────────────────────
    perf_tot = round((capitale_corrente - CAPITALE) / CAPITALE * 100, 2)

    equity_mensile = []
    cap_tmp = float(CAPITALE)
    months_seen = set()
    for rd, ret in sorted(rendimenti.items()):
        cap_tmp = round(cap_tmp * (1 + ret / 100), 2)
        month = rd[:7]
        if month not in months_seen:
            equity_mensile.append({"mese": month, "valore": cap_tmp})
            months_seen.add(month)

    cap_series = [float(CAPITALE)] + [v["capitale"] for v in versioni]
    peak = cap_series[0]; mdd = 0
    for c in cap_series:
        if c > peak: peak = c
        dd = (c - peak) / peak * 100
        if dd < mdd: mdd = dd
    mdd = round(mdd, 2)

    rets_list = [rendimenti[d] for d in sorted(rendimenti)]

    def sharpe_n(rl, n, rf=0.03/52):
        if len(rl) < n: return None
        w = rl[-n:]
        mr = sum(w) / len(w) - rf
        var = sum((r - sum(w)/len(w))**2 for r in w) / (len(w)-1) if len(w) > 1 else 0
        std = math.sqrt(var) if var > 0 else 0
        return round(mr / std * math.sqrt(52), 2) if std > 0 else None

    sharpe_6m  = sharpe_n(rets_list, 26)
    sharpe_12m = sharpe_n(rets_list, 52)

    # Drawdown series
    cap2 = [float(CAPITALE)]
    for d in sorted(rendimenti):
        cap2.append(cap2[-1] * (1 + rendimenti[d] / 100))
    peak = cap2[0]
    dd_series = []
    dates_w = sorted(rendimenti.keys())
    for i, v in enumerate(cap2[1:]):
        if v > peak: peak = v
        dd_series.append({"data": dates_w[i], "dd": round((v-peak)/peak*100, 3)})

    # Rolling Sharpe
    rolling_sh = []
    dates_s = sorted(rendimenti.keys())
    window = 13
    for i in range(window, len(rets_list)+1):
        w = rets_list[i-window:i]
        rf = 0.03/52
        mr = sum(w)/len(w) - rf
        var = sum((r-sum(w)/len(w))**2 for r in w)/(len(w)-1) if len(w)>1 else 0
        std = math.sqrt(var) if var > 0 else 0
        sh = round(mr/std*math.sqrt(52), 3) if std > 0 else 0
        rolling_sh.append({"data": dates_s[i-1] if i-1 < len(dates_s) else None, "sharpe": sh})

    # Rendimenti mensili
    rend_per_anno = defaultdict(dict)
    prev_val = float(CAPITALE)
    for e in equity_mensile:
        anno, mese = e["mese"].split("-")
        rend_per_anno[anno][mese] = round((e["valore"] - prev_val) / prev_val * 100, 2)
        prev_val = e["valore"]

    rend_annuo = {}
    for anno, mesi in rend_per_anno.items():
        cum = 1.0
        for r in mesi.values(): cum *= (1 + r/100)
        rend_annuo[anno] = round((cum-1)*100, 2)

    def calc_rend_bm(ticker, etf_data):
        d = etf_data.get(ticker)
        if not d: return {}, {}
        closes = d["closes"]; dates = d["dates"]
        n = min(len(closes), len(dates))
        pairs = [(dates[i], closes[i]) for i in range(n) if dates[i] >= BACKTEST_START]
        if not pairs: return {}, {}
        mc = defaultdict(list)
        for dt, cl in pairs: mc[dt[:7]].append((dt, cl))
        mesi_ord = sorted(mc.keys())
        rpa = defaultdict(dict); ra = {}
        prev = mc[mesi_ord[0]][0][1]
        for mese in mesi_ord:
            last = mc[mese][-1][1]
            ret = round((last - prev) / prev * 100, 2) if prev else 0
            anno, m = mese.split("-")
            rpa[anno][m] = ret
            prev = last
        for anno, mesi in rpa.items():
            cum = 1.0
            for r in mesi.values(): cum *= (1 + r/100)
            ra[anno] = round((cum-1)*100, 2)
        return dict(rpa), ra

    rend_iwmo_mese, rend_iwmo_anno = calc_rend_bm(BENCHMARK, etf_data)

    # Performance per step (0/1/2/3 segnali)
    perf_per_step = defaultdict(list)
    for v in versioni:
        ns = str(v["n_segnali"])
        if v["data"] in rendimenti:
            perf_per_step[ns].append(rendimenti[v["data"]])
    labels_step = {
        "0": "100% IWMO",
        "1": "70% IWMO",
        "2": "30% IWMO",
        "3": "100% XEON"
    }
    perf_per_step_summary = {}
    for ns, rets in perf_per_step.items():
        perf_per_step_summary[ns] = {
            "media_sett": round(sum(rets)/len(rets), 3),
            "n": len(rets),
            "positivi": sum(1 for r in rets if r > 0),
            "label": labels_step.get(ns, ""),
        }

    # Turnover (sempre basso — solo IWMO/XEON)
    turnover_medio = 0.0  # non cambia i ticker, cambia solo i pesi

    # Storia segnali per HTML
    storia_segnali_slim = [
        {k: v[k] for k in ["data","n_segnali","s1","s2","s3","descrizione"] if k in v}
        for v in storia_segnali
    ]

    return {
        "performance_totale_pct": perf_tot,
        "performance_totale_eur": round(capitale_corrente - CAPITALE, 2),
        "capitale_attuale":       round(capitale_corrente, 2),
        "max_drawdown":           mdd,
        "sharpe_6m":              sharpe_6m,
        "sharpe_12m":             sharpe_12m,
        "rolling_sharpe":         rolling_sh,
        "drawdown_series":        dd_series,
        "rend_per_anno":          dict(rend_per_anno),
        "rend_annuo":             rend_annuo,
        "rend_iwmo_mese":         rend_iwmo_mese,
        "rend_iwmo_anno":         rend_iwmo_anno,
        "turnover_medio":         turnover_medio,
        "perf_per_step":          perf_per_step_summary,
        "versioni":               versioni,
        "composizione_corrente":  versioni[-1]["composizione"] if versioni else [],
        "rendimenti":             rendimenti,
        "equity_mensile":         equity_mensile,
        "storia_segnali":         storia_segnali_slim,
        "n_rebalancing":          len(versioni),
    }

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    oggi = datetime.date.today().isoformat()
    print(f"COMPASS ETP2 — IWMO Timing v1.0 — {oggi}")

    existing = {}
    run_number = 1
    if OUT_FILE.exists():
        try:
            existing = json.loads(OUT_FILE.read_text())
            run_number = existing.get("run_number", 0) + 1
        except: pass
    print(f"  Run: {run_number}")

    # Download IWMO + XEON + benchmark
    tickers = ["IWMO.MI", "XEON.MI", "VWCE.DE"]
    print(f"\n[1/3] Download {len(tickers)} ticker (900gg)...")
    etf_data = {}
    for t in tickers:
        d = fetch_yahoo(t, days=900)
        if d:
            etf_data[t] = d
            m6  = None
            cl = d["closes"]
            if len(cl) > 127: m6 = round((cl[-1]-cl[-127])/cl[-127]*100, 1)
            print(f"  {t}... OK mom6M={f'+{m6}%' if m6 and m6>=0 else f'{m6}%' if m6 else 'n.d.'}")
        else:
            print(f"  {t}... ERR")
        time.sleep(0.3)

    # Segnali oggi
    cl_iwmo = closes_at(etf_data, "IWMO.MI", oggi)
    n_seg, seg_det = calc_segnali_iwmo(cl_iwmo)
    qa = quota_iwmo(n_seg)
    print(f"\n  Segnali IWMO oggi: {n_seg}/3 → quota IWMO {qa*100:.0f}%")
    print(f"  {seg_det['descrizione']}")

    # Backtest
    print(f"\n[2/3] Backtest IWMO Timing (da {BACKTEST_START}, rebalancing ogni {REBAL_DAYS}gg)...")
    risultato = run_backtest_timing(etf_data, BACKTEST_START, oggi)
    print(f"  Performance: {risultato['performance_totale_pct']:+.1f}% | "
          f"MDD: {risultato['max_drawdown']:.1f}% | "
          f"Rebalancing: {risultato['n_rebalancing']}")

    # Benchmark
    print(f"\n[3/3] Benchmark {BENCHMARK} + {BENCHMARK2}...")
    def bm_perf(ticker):
        d = etf_data.get(ticker)
        if not d: return None
        p0 = next((d["closes"][i] for i in range(len(d["dates"])) if d["dates"][i] >= BACKTEST_START), None)
        p1 = d["closes"][-1]
        return round((p1-p0)/p0*100, 2) if p0 and p1 else None

    bm1 = bm_perf(BENCHMARK)
    bm2 = bm_perf(BENCHMARK2)
    if bm1:
        op1 = round(risultato["performance_totale_pct"] - bm1, 2)
        print(f"  {BENCHMARK}: {bm1:+.1f}% | Outperf: {op1:+.1f}pp")
    if bm2:
        op2 = round(risultato["performance_totale_pct"] - bm2, 2)
        print(f"  {BENCHMARK2}: {bm2:+.1f}% | Outperf: {op2:+.1f}pp")

    # Output
    output = {
        "generated":      datetime.datetime.utcnow().isoformat(),
        "version":        "etp2_1.0",
        "run_number":     run_number,
        "strategy":       "COMPASS ETP2 — IWMO Timing (KAMA + XEON)",
        "backtest_start": BACKTEST_START,
        "benchmark":      BENCHMARK,
        "benchmark2":     BENCHMARK2,
        "segnali_oggi":   {**seg_det, "quota_iwmo_pct": round(qa*100), "quota_xeon_pct": round((1-qa)*100)},
        "benchmark_perf":   bm1,
        "benchmark2_perf":  bm2,
        "outperformance":   round(risultato["performance_totale_pct"] - bm1, 2) if bm1 else None,
        "outperformance2":  round(risultato["performance_totale_pct"] - bm2, 2) if bm2 else None,
        "batte_benchmark":  risultato["performance_totale_pct"] > bm1 if bm1 else None,
        **risultato,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size = OUT_FILE.stat().st_size / 1024
    print(f"\n✅ Done → {OUT_FILE} ({size:.0f} KB)")
    print(f"   IWMO Timing v1.0 | Run: {run_number}")
    print(f"   Performance: {risultato['performance_totale_pct']:+.1f}% | "
          f"vs IWMO: {output.get('outperformance',0):+.1f}pp | "
          f"MDD: {risultato['max_drawdown']:.1f}%")
    print(f"\n   Posizione corrente:")
    for p in (risultato["composizione_corrente"] or []):
        print(f"   {p['ticker']:<14} {p['peso']:>5.1f}% | {p.get('commento','')[:60]}")

if __name__ == "__main__":
    main()

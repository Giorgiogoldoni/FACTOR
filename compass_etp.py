#!/usr/bin/env python3
"""
COMPASS ETP — compass_etp.py v3.0  IWMO+
══════════════════════════════════════════════════════════════════════
Strategia: clonare IWMO con universo più ampio + protezione crash

OBIETTIVO
  Battere IWMO su ciclo completo usando:
  1. Universo più ampio (tematici, EM, leva) — cattura alpha che IWMO
     non può fare per vincoli strutturali
  2. Uscita progressiva in 3 step basata su segnali tecnici di IWMO —
     evita i crash sistemici (-30%) che IWMO incassa sempre

SCORE MOMENTUM PURO
  score = mom6M×0.40 + mom3M×0.35 + mom1M×0.25
  × moltiplicatore_ER   (0.85 / 1.0 / 1.15)
  × moltiplicatore_KAMA (0.75 / 1.0 / 1.15)

SEGNALI DI USCITA SU IWMO (attivazione progressiva)
  S1 — Mom 1M IWMO < 0
  S2 — Prezzo IWMO < KAMA(IWMO) e KAMA in discesa
  S3 — IWMO sotto massimo 60gg di oltre 10%

  0 segnali → 100% momentum ETF
  1 segnale → 70% momentum + 30% XEON
  2 segnali → 30% momentum + 70% XEON
  3 segnali → 100% XEON

UNIVERSO (52 ETF momentum puri)
  Azionario globale, europa, usa, EM/asia, tematici, leva
  ESCLUSI: HY, bond IG, EM bond (non momentum puri)
  XEON: solo cash di parcheggio in uscita

PORTAFOGLIO
  8-10 ETF concentrati, max 2 per categoria
  IWMO cap 20%, leva solo con 0 segnali attivi

Output: data/compass_etp.json
"""

import json, math, datetime, time, urllib.request
from pathlib import Path
from collections import defaultdict

# ── CONFIGURAZIONE ──────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).parent
OUT_FILE         = BASE_DIR / "data" / "compass_etp.json"
BACKTEST_START   = "2024-01-01"
CAPITALE         = 100_000
BENCHMARK        = "IWMO.MI"
BENCHMARK2       = "VWCE.DE"
N_ETF_MIN        = 8
N_ETF_MAX        = 10
SOGLIA_ROTAZIONE = 12        # punti minimi per sostituire ETF già in ptf
IWMO_CAP         = 20.0      # peso massimo IWMO in portafoglio
REBAL_DAYS       = 10        # giorni lavorativi tra rebalancing

# ── UNIVERSO IWMO+ (52 ETF momentum puri) ───────────────────────────────────
UNIVERSE = [
    # ── AZIONARIO GLOBALE (13) ─────────────────────────────────────────────
    {"t":"WWRD.MI",  "n":"WT World",                        "cat":"az_globale", "sub":"GLOBAL"},
    {"t":"SWDA.MI",  "n":"iShares Core MSCI World",         "cat":"az_globale", "sub":"GLOBAL"},
    {"t":"VWCE.DE",  "n":"Vanguard FTSE All-World",         "cat":"az_globale", "sub":"GLOBAL"},
    {"t":"XDWT.MI",  "n":"Xtrackers MSCI World Swap",       "cat":"az_globale", "sub":"GLOBAL"},
    {"t":"IWMO.MI",  "n":"iShares MSCI World Momentum",     "cat":"az_globale", "sub":"GLOBAL_MOM"},
    {"t":"IWQU.MI",  "n":"iShares MSCI World Quality",      "cat":"az_globale", "sub":"GLOBAL_F"},
    {"t":"WOEE.DE",  "n":"iShares World Enhanced Active",   "cat":"az_globale", "sub":"GLOBAL_F"},
    {"t":"IFSW.MI",  "n":"iShares STOXX World Multifactor", "cat":"az_globale", "sub":"GLOBAL_F"},
    {"t":"JPGL.MI",  "n":"JPMorgan Global Multi-Factor",    "cat":"az_globale", "sub":"GLOBAL_F"},
    {"t":"FCRN.DE",  "n":"iShares World Factor Rotation",   "cat":"az_globale", "sub":"GLOBAL_F"},
    {"t":"NTSX.MI",  "n":"WT US Efficient Core",            "cat":"az_globale", "sub":"GLOBAL_EC"},
    {"t":"NTSG.MI",  "n":"WT Global Efficient Core",        "cat":"az_globale", "sub":"GLOBAL_EC"},
    {"t":"IBCZ.DE",  "n":"iShares STOXX World MF",          "cat":"az_globale", "sub":"GLOBAL_F"},
    # ── AZIONARIO EUROPA (8) ───────────────────────────────────────────────
    {"t":"WS5X.MI",  "n":"WT Euro Stoxx 50",                "cat":"az_europa",  "sub":"EU"},
    {"t":"SMEA.MI",  "n":"iShares Europe Small Cap",        "cat":"az_europa",  "sub":"EU_SMALL"},
    {"t":"EXX5.DE",  "n":"iShares EURO STOXX 50",           "cat":"az_europa",  "sub":"EU"},
    {"t":"EXV1.DE",  "n":"iShares STOXX Europe 600",        "cat":"az_europa",  "sub":"EU"},
    {"t":"EUEE.DE",  "n":"iShares Europe Enhanced Active",  "cat":"az_europa",  "sub":"EU_F"},
    {"t":"IEMO.MI",  "n":"iShares MSCI Europe Momentum",    "cat":"az_europa",  "sub":"EU_MOM"},
    {"t":"IEQU.MI",  "n":"iShares MSCI Europe Quality",     "cat":"az_europa",  "sub":"EU_F"},
    {"t":"EXXW.DE",  "n":"iShares MSCI Europe",             "cat":"az_europa",  "sub":"EU"},
    # ── AZIONARIO USA (8) ──────────────────────────────────────────────────
    {"t":"WSPX.MI",  "n":"WT S&P 500",                      "cat":"az_usa",     "sub":"US"},
    {"t":"WNAS.MI",  "n":"WT Nasdaq-100",                   "cat":"az_usa",     "sub":"TECH"},
    {"t":"CSSPX.MI", "n":"iShares Core S&P 500",            "cat":"az_usa",     "sub":"US"},
    {"t":"USEE.DE",  "n":"iShares US Enhanced Active",      "cat":"az_usa",     "sub":"US_F"},
    {"t":"QDVB.DE",  "n":"iShares MSCI USA Quality",        "cat":"az_usa",     "sub":"US_F"},
    {"t":"XUTC.MI",  "n":"Xtrackers MSCI USA IT",           "cat":"az_usa",     "sub":"TECH"},
    {"t":"WRTY.MI",  "n":"WT Russell 2000 Efficient Core",  "cat":"az_usa",     "sub":"US_SMALL"},
    {"t":"WSPE.MI",  "n":"WT S&P 500 EUR Hedged",           "cat":"az_usa",     "sub":"US_EUR"},
    # ── AZIONARIO EM/ASIA (11) ─────────────────────────────────────────────
    {"t":"VFEM.MI",  "n":"Vanguard FTSE EM",                "cat":"az_em",      "sub":"EM_BROAD"},
    {"t":"EIMI.MI",  "n":"iShares MSCI EM",                 "cat":"az_em",      "sub":"EM_CORE"},
    {"t":"DXJF.MI",  "n":"WisdomTree Japan EUR Hedged",     "cat":"az_em",      "sub":"JAPAN"},
    {"t":"XCHA.MI",  "n":"iShares China",                   "cat":"az_em",      "sub":"CHINA"},
    {"t":"XASX.DE",  "n":"iShares Asia Pacific",            "cat":"az_em",      "sub":"ASIA_PAC"},
    {"t":"EMEE.MI",  "n":"iShares EM Enhanced Active",      "cat":"az_em",      "sub":"EM_F"},
    {"t":"AXEE.MI",  "n":"iShares Asia ex Japan Enhanced",  "cat":"az_em",      "sub":"ASIA_F"},
    {"t":"IS3N.DE",  "n":"iShares MSCI EM Small Cap",       "cat":"az_em",      "sub":"EM_SMALL"},
    {"t":"VAPX.MI",  "n":"Vanguard Dev Asia Pacific",       "cat":"az_em",      "sub":"ASIA_PAC"},
    {"t":"JPNH.MI",  "n":"Amundi MSCI Japan EUR Hdg",       "cat":"az_em",      "sub":"JAPAN"},
    {"t":"NTSZ.MI",  "n":"WT EM Efficient Core",            "cat":"az_em",      "sub":"EM_EC"},
    # ── TEMATICO (10) ──────────────────────────────────────────────────────
    {"t":"PHAU.MI",  "n":"WT Physical Gold",                "cat":"tematico",   "sub":"GOLD"},
    {"t":"CRUD.MI",  "n":"WT WTI Crude Oil",                "cat":"tematico",   "sub":"CRUDE"},
    {"t":"SMH.MI",   "n":"VanEck Semiconductor",            "cat":"tematico",   "sub":"TECH_T"},
    {"t":"DFNS.MI",  "n":"VanEck Defense",                  "cat":"tematico",   "sub":"DEFENSE"},
    {"t":"IART.DE",  "n":"iShares AI Innovation",           "cat":"tematico",   "sub":"AI"},
    {"t":"RARE.MI",  "n":"VanEck Rare Earth",               "cat":"tematico",   "sub":"MATERIALS"},
    {"t":"COPA.MI",  "n":"WT Copper",                       "cat":"tematico",   "sub":"MATERIALS"},
    {"t":"CMOD.MI",  "n":"iShares Commodity",               "cat":"tematico",   "sub":"COMMODITY"},
    {"t":"IFFF.MI",  "n":"iShares MSCI Global Financials",  "cat":"tematico",   "sub":"FINANCIAL"},
    {"t":"AIGA.MI",  "n":"WT Agriculture",                  "cat":"tematico",   "sub":"COMMODITY"},
    # ── LEVA (3) — solo con 0 segnali attivi ───────────────────────────────
    {"t":"3USL.MI",  "n":"WT S&P 500 3x Lev",              "cat":"leva",       "sub":"LEVA_US"},
    {"t":"QQQ3.MI",  "n":"WT Nasdaq 3x Lev",               "cat":"leva",       "sub":"LEVA_US"},
    {"t":"3NVD.MI",  "n":"Leverage Shares 3x NVIDIA",      "cat":"leva",       "sub":"LEVA_TEMA"},
]

# XEON — solo cash, non selezionabile come ETF momentum
XEON = {"t":"XEON.MI", "n":"Xtrackers EUR Overnight", "cat":"monetario", "sub":"CASH"}

# Cap peso per ETF singolo
PESO_MAX_ETF = {
    "IWMO.MI": IWMO_CAP,
    "3USL.MI": 12.0,
    "QQQ3.MI": 12.0,
    "3NVD.MI": 8.0,
    "IART.DE": 12.0,
}

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
            if not result:
                time.sleep(2); continue
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

def closes_at(etf_data, ticker, target_date):
    """Ritorna closes fino a target_date."""
    d = etf_data.get(ticker)
    if not d: return []
    n = min(len(d["closes"]), len(d["dates"]))
    return [d["closes"][i] for i in range(n) if d["dates"][i] <= target_date]

def get_price_on_date(etf_data, ticker, target_date):
    cl = closes_at(etf_data, ticker, target_date)
    return cl[-1] if cl else None

# ── INDICATORI TECNICI ───────────────────────────────────────────────────────
def calc_mom(closes, days):
    """Momentum su N giorni."""
    if len(closes) <= days: return None
    old = closes[-(days + 1)]
    return round((closes[-1] - old) / old * 100, 2) if old else None

def calc_er(closes, period=20):
    """Efficiency Ratio su period giorni."""
    if len(closes) <= period: return 0.0
    direction  = abs(closes[-1] - closes[-period - 1])
    volatility = sum(abs(closes[i] - closes[i-1]) for i in range(-period, 0))
    return round(direction / volatility, 4) if volatility else 0.0

def calc_kama(closes, period=10, fast=2, slow=30):
    """
    Kaufman Adaptive Moving Average.
    Ritorna (kama_corrente, kama_precedente, direzione).
    """
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

def mult_er(er_val):
    """Moltiplicatore score basato su ER."""
    if er_val >= 0.6:  return 1.15
    if er_val >= 0.4:  return 1.0
    return 0.85

def mult_kama(closes):
    """
    Moltiplicatore score basato su posizione prezzo vs KAMA.
    1.15 = sopra KAMA con KAMA in salita
    1.0  = sopra KAMA ma KAMA piatta
    0.75 = sotto KAMA
    """
    kama_now, kama_prev, direzione = calc_kama(closes)
    if kama_now is None: return 1.0
    price = closes[-1]
    if price >= kama_now and direzione >= 0: return 1.15
    if price >= kama_now and direzione < 0:  return 1.0
    return 0.75

# ── SCORE MOMENTUM PURO ─────────────────────────────────────────────────────
def calc_score(closes):
    """
    Score IWMO+ basato su momentum puro multi-timeframe + ER + KAMA.
    Ritorna dict con score e dettagli per commento tecnico.
    """
    if not closes or len(closes) < 130: return None

    m6  = calc_mom(closes, 126) or 0   # ~6 mesi
    m3  = calc_mom(closes, 63)  or 0   # ~3 mesi
    m1  = calc_mom(closes, 21)  or 0   # ~1 mese
    er  = calc_er(closes, 20)
    kama_now, kama_prev, kama_dir = calc_kama(closes)

    # Score base momentum (può essere negativo)
    score_base = m6 * 0.40 + m3 * 0.35 + m1 * 0.25

    # Moltiplicatori
    m_er   = mult_er(er)
    m_kama = mult_kama(closes) if kama_now else 1.0

    score_final = score_base * m_er * m_kama

    # Normalizza in [0, 100] con curva logistica per confronto
    # score_base tipicamente in [-30, +60] → normalizzo su questa scala
    score_norm = max(0, min(100, (score_final + 30) / 90 * 100))

    return {
        "score":      round(score_norm, 1),
        "score_raw":  round(score_final, 2),
        "mom6m":      round(m6, 2),
        "mom3m":      round(m3, 2),
        "mom1m":      round(m1, 2),
        "er":         round(er, 3),
        "kama":       round(kama_now, 4) if kama_now else None,
        "kama_dir":   kama_dir,
        "mult_er":    m_er,
        "mult_kama":  m_kama,
        "price":      round(closes[-1], 4),
    }

# ── COMMENTO TECNICO ─────────────────────────────────────────────────────────
def genera_commento(ticker, sc, azione, giorni_in_ptf=None):
    """
    Genera commento tecnico leggibile per ogni ETF in portafoglio.
    """
    if not sc: return "Dati insufficienti"

    m6, m3, m1 = sc["mom6m"], sc["mom3m"], sc["mom1m"]
    er  = sc["er"]
    kd  = sc["kama_dir"]
    mk  = sc["mult_kama"]

    # Momentum narrative
    if m6 > 15 and m3 > 5:
        mom_txt = f"Momentum forte su tutti i timeframe (6M {m6:+.1f}%, 3M {m3:+.1f}%, 1M {m1:+.1f}%)"
    elif m6 > 5 and m3 > 0:
        mom_txt = f"Momentum positivo (6M {m6:+.1f}%, 3M {m3:+.1f}%, 1M {m1:+.1f}%)"
    elif m6 > 0 and m3 < 0:
        mom_txt = f"Momentum in rallentamento — 6M ancora positivo ({m6:+.1f}%) ma 3M negativo ({m3:+.1f}%)"
    else:
        mom_txt = f"Momentum debole (6M {m6:+.1f}%, 3M {m3:+.1f}%, 1M {m1:+.1f}%)"

    # ER narrative
    if er >= 0.6:
        er_txt = f"Trend efficiente (ER {er:.2f}) — movimento diretto senza rumore"
    elif er >= 0.4:
        er_txt = f"Trend discreto (ER {er:.2f})"
    else:
        er_txt = f"Movimento caotico (ER {er:.2f}) — alta volatilità relativa"

    # KAMA narrative
    if mk == 1.15:
        kama_txt = "Prezzo sopra KAMA in salita — trend confermato ✅"
    elif mk == 1.0:
        kama_txt = "Prezzo sopra KAMA ma trend in rallentamento ⚠️"
    else:
        kama_txt = "Prezzo sotto KAMA — trend negativo 🔴"

    # Azione narrative
    if azione == "ACQUISTA":
        az_txt = "Nuovo ingresso"
        if giorni_in_ptf:
            az_txt = f"Rientro dopo {giorni_in_ptf}gg fuori portafoglio"
    elif azione == "MANTIENI":
        az_txt = f"Mantenuto{f' da {giorni_in_ptf}gg' if giorni_in_ptf else ''} — score stabile"
    elif azione == "RAFFORZA":
        az_txt = "Peso aumentato — score in crescita"
    else:
        az_txt = "Monitorare"

    return f"{az_txt}. {mom_txt}. {er_txt}. {kama_txt}"

# ── SEGNALI DI USCITA SU IWMO ────────────────────────────────────────────────
def calc_segnali_iwmo(closes_iwmo):
    """
    Calcola i 3 segnali di uscita basati su IWMO.
    Ritorna (n_segnali, dettaglio_segnali).
    """
    if not closes_iwmo or len(closes_iwmo) < 130:
        return 0, {"s1": False, "s2": False, "s3": False, "descrizione": "Dati insufficienti"}

    # S1: Momentum 1M IWMO negativo
    m1 = calc_mom(closes_iwmo, 21)
    s1 = (m1 is not None and m1 < 0)

    # S2: Prezzo IWMO < KAMA e KAMA in discesa
    kama_now, kama_prev, kama_dir = calc_kama(closes_iwmo)
    price = closes_iwmo[-1]
    s2 = (kama_now is not None and price < kama_now and kama_dir < 0)

    # S3: IWMO sotto massimo 60gg di oltre 10%
    if len(closes_iwmo) >= 60:
        max_60 = max(closes_iwmo[-60:])
        s3 = (price < max_60 * 0.90)
    else:
        s3 = False

    n = sum([s1, s2, s3])

    desc_parts = []
    if s1: desc_parts.append(f"S1✓ Mom1M={m1:+.1f}%")
    else:  desc_parts.append(f"S1✗ Mom1M={m1:+.1f}%" if m1 else "S1✗")
    if s2: desc_parts.append(f"S2✓ Prezzo<KAMA({kama_now:.2f}) KAMA↓")
    else:  desc_parts.append(f"S2✗ Prezzo>KAMA" if kama_now else "S2✗")
    if s3:
        max_60 = max(closes_iwmo[-60:]) if len(closes_iwmo) >= 60 else 0
        desc_parts.append(f"S3✓ -{((max_60-price)/max_60*100):.1f}% da max60gg")
    else:
        desc_parts.append("S3✗")

    return n, {
        "s1": s1, "s2": s2, "s3": s3,
        "n_segnali": n,
        "mom1m_iwmo": round(m1, 2) if m1 else None,
        "kama_iwmo": round(kama_now, 4) if kama_now else None,
        "kama_dir_iwmo": kama_dir,
        "descrizione": " | ".join(desc_parts),
    }

def quota_azionario(n_segnali):
    """Quota azionaria momentum in base ai segnali attivi."""
    if n_segnali == 0: return 1.0
    if n_segnali == 1: return 0.7
    if n_segnali == 2: return 0.3
    return 0.0   # 3 segnali → 100% XEON

# ── BACKTEST ─────────────────────────────────────────────────────────────────
def run_backtest(etf_data, backtest_start, oggi):
    all_dates = []
    for d in etf_data.values():
        all_dates.extend(d.get("dates", []))
    all_dates = sorted(set(d for d in all_dates if backtest_start <= d <= oggi))

    rebal_dates = [all_dates[i] for i in range(0, len(all_dates), REBAL_DAYS)]
    if all_dates and all_dates[-1] not in rebal_dates:
        rebal_dates.append(all_dates[-1])

    versioni               = []
    composizione_attuale   = []
    comp_precedente        = []
    data_ingresso_map      = {}   # ticker → prima data in ptf
    capitale_corrente      = float(CAPITALE)
    rendimenti             = {}   # data → rendimento %
    storia_segnali         = []

    for idx, rdate in enumerate(rebal_dates):
        # ── Segnali IWMO ──────────────────────────────────────────────────
        cl_iwmo = closes_at(etf_data, "IWMO.MI", rdate)
        n_seg, dettaglio_seg = calc_segnali_iwmo(cl_iwmo)
        storia_segnali.append({"data": rdate, "n_segnali": n_seg, **dettaglio_seg})

        qa = quota_azionario(n_seg)   # 0.0 – 1.0

        # ── Score tutti gli ETF ────────────────────────────────────────────
        candidati = []
        for etf in UNIVERSE:
            t  = etf["t"]
            cl = closes_at(etf_data, t, rdate)
            sc = calc_score(cl)
            if sc is None: continue

            # Leva: solo con 0 segnali
            if etf["cat"] == "leva" and n_seg > 0:
                continue

            # Bonus stabilità per ETF già in ptf
            bonus = SOGLIA_ROTAZIONE / 2 if any(p["ticker"] == t for p in comp_precedente) else 0

            candidati.append({
                "ticker":  t,
                "nome":    etf["n"],
                "cat":     etf["cat"],
                "sub":     etf["sub"],
                "score":   round(sc["score"] + bonus, 1),
                "score_raw": sc["score_raw"],
                "mom6m":   sc["mom6m"],
                "mom3m":   sc["mom3m"],
                "mom1m":   sc["mom1m"],
                "er":      sc["er"],
                "kama":    sc["kama"],
                "kama_dir": sc["kama_dir"],
                "mult_er":  sc["mult_er"],
                "mult_kama": sc["mult_kama"],
                "price":   sc["price"],
            })

        if not candidati and qa > 0: continue

        # ── Selezione portafoglio ──────────────────────────────────────────
        candidati.sort(key=lambda x: x["score"], reverse=True)
        selected = []
        cat_count = {}
        for c in candidati:
            if len(selected) >= N_ETF_MAX: break
            if cat_count.get(c["cat"], 0) >= 2: continue
            cat_count[c["cat"]] = cat_count.get(c["cat"], 0) + 1
            selected.append(c)

        if len(selected) < N_ETF_MIN and len(candidati) >= N_ETF_MIN:
            selected = candidati[:N_ETF_MAX]

        # ── Pesi score^1.5 + cap ──────────────────────────────────────────
        def w(s): return max(0, s) ** 1.5
        tot_w = sum(w(c["score"]) for c in selected) or 1
        for c in selected:
            p = w(c["score"]) / tot_w * 100 * qa
            p = min(p, PESO_MAX_ETF.get(c["ticker"], 35.0))
            c["peso_momentum"] = round(p, 1)

        # Rinormalizza la quota momentum
        tot_mom = sum(c["peso_momentum"] for c in selected) or 1
        target_mom = qa * 100
        for c in selected:
            c["peso"] = round(c["peso_momentum"] / tot_mom * target_mom, 1)

        # ── Aggiunge XEON per la quota difensiva ──────────────────────────
        peso_xeon = round((1 - qa) * 100, 1)
        composizione_finale = []
        if peso_xeon > 0:
            composizione_finale.append({
                **XEON,
                "ticker": XEON["t"],
                "nome":   XEON["n"],
                "peso":   peso_xeon,
                "score":  0,
                "mom6m": 0, "mom3m": 0, "mom1m": 0,
                "er": 1.0, "kama": None, "kama_dir": 0,
            })
        composizione_finale.extend(selected)

        # ── Data ingresso ─────────────────────────────────────────────────
        for c in composizione_finale:
            t = c["ticker"]
            if t not in data_ingresso_map:
                data_ingresso_map[t] = rdate
            c["data_ingresso"] = data_ingresso_map[t]

        # ── Azioni operative ──────────────────────────────────────────────
        ticker_prec = {p["ticker"] for p in comp_precedente}
        ticker_corr = {c["ticker"] for c in composizione_finale}
        for c in composizione_finale:
            t = c["ticker"]
            if t == XEON["t"]:
                c["azione"] = "CASH"
                c["commento"] = f"Parcheggio difensivo — {n_seg} segnale/i IWMO attiv{'o' if n_seg==1 else 'i'}: {dettaglio_seg['descrizione']}"
                continue
            giorni = None
            if c["data_ingresso"] and c["data_ingresso"] != rdate:
                try:
                    d1 = datetime.date.fromisoformat(c["data_ingresso"])
                    d2 = datetime.date.fromisoformat(rdate)
                    giorni = (d2 - d1).days
                except: pass
            if t not in ticker_prec:
                azione = "ACQUISTA"
            else:
                prev = next((p for p in comp_precedente if p["ticker"] == t), None)
                ds = c["score"] - (prev["score"] if prev else c["score"])
                azione = "RAFFORZA" if ds >= 8 else "MANTIENI"
            c["azione"] = azione
            sc_dict = {k: c.get(k) for k in ["mom6m","mom3m","mom1m","er","kama","kama_dir","mult_er","mult_kama"]}
            c["commento"] = genera_commento(t, sc_dict, azione, giorni)

        # ── Rendimento dal periodo precedente ─────────────────────────────
        if idx > 0 and comp_precedente and rebal_dates[idx-1] < rdate:
            prev_date = rebal_dates[idx - 1]
            ptf_ret = 0.0
            for pos in comp_precedente:
                t = pos["ticker"]
                d = etf_data.get(t)
                if not d: continue
                n = min(len(d["closes"]), len(d["dates"]))
                p_prev = next((d["closes"][i] for i in range(n-1,-1,-1) if d["dates"][i] <= prev_date), None)
                p_now  = next((d["closes"][i] for i in range(n-1,-1,-1) if d["dates"][i] <= rdate), None)
                if p_prev and p_now and p_prev > 0:
                    ptf_ret += (p_now - p_prev) / p_prev * pos["peso"] / 100
            capitale_corrente = round(capitale_corrente * (1 + ptf_ret), 2)
            rendimenti[rdate] = round(ptf_ret * 100, 4)

        for c in composizione_finale:
            c["importo"] = round(capitale_corrente * c["peso"] / 100, 2)

        comp_precedente      = composizione_finale
        composizione_attuale = composizione_finale

        versioni.append({
            "data":         rdate,
            "n_segnali":    n_seg,
            "segnali":      dettaglio_seg,
            "quota_az":     round(qa * 100, 0),
            "composizione": composizione_finale,
            "capitale":     round(capitale_corrente, 2),
        })

    # ── Metriche finali ────────────────────────────────────────────────────
    perf_tot = round((capitale_corrente - CAPITALE) / CAPITALE * 100, 2)

    # Equity mensile
    equity_mensile = []
    cap_tmp = float(CAPITALE)
    months_seen = set()
    for rd, ret in sorted(rendimenti.items()):
        cap_tmp = round(cap_tmp * (1 + ret / 100), 2)
        month = rd[:7]
        if month not in months_seen:
            equity_mensile.append({"mese": month, "valore": cap_tmp})
            months_seen.add(month)

    # MDD
    cap_series = [float(CAPITALE)] + [v["capitale"] for v in versioni]
    peak = cap_series[0]; mdd = 0
    for c in cap_series:
        if c > peak: peak = c
        dd = (c - peak) / peak * 100
        if dd < mdd: mdd = dd
    mdd = round(mdd, 2)

    # Sharpe
    def sharpe_n(rl, n, rf=0.03/52):
        if len(rl) < n: return None
        w = rl[-n:]
        mu = sum(w) / len(w) - rf
        var = sum((r - sum(w)/len(w))**2 for r in w) / (len(w)-1) if len(w) > 1 else 0
        std = math.sqrt(var) if var > 0 else 0
        return round(mu / std * math.sqrt(52), 2) if std > 0 else None

    rl = [rendimenti[d] for d in sorted(rendimenti)]
    sh6  = sharpe_n(rl, 26)
    sh12 = sharpe_n(rl, 52)

    # Rolling Sharpe 13W
    rolling_sh = []
    dates_s = sorted(rendimenti.keys())
    for i in range(13, len(rl) + 1):
        w = rl[i-13:i]
        mu = sum(w)/len(w) - 0.03/52
        var = sum((r - sum(w)/len(w))**2 for r in w) / (len(w)-1) if len(w) > 1 else 0
        std = math.sqrt(var) if var > 0 else 0
        sh = round(mu / std * math.sqrt(52), 3) if std > 0 else 0
        rolling_sh.append({"data": dates_s[i-1], "sharpe": sh})

    # Drawdown series
    cap2 = [float(CAPITALE)]
    for rd in sorted(rendimenti.keys()):
        cap2.append(cap2[-1] * (1 + rendimenti[rd]/100))
    peak = cap2[0]; dd_series = []
    for i, v in enumerate(cap2[1:]):
        if v > peak: peak = v
        dd_series.append({"data": dates_s[i] if i < len(dates_s) else "", "dd": round((v-peak)/peak*100, 3)})

    # Rendimenti mensili
    rend_per_anno = defaultdict(dict)
    prev_val = float(CAPITALE)
    for e in equity_mensile:
        anno, mese = e["mese"].split("-")
        ret = round((e["valore"] - prev_val) / prev_val * 100, 2)
        rend_per_anno[anno][mese] = ret
        prev_val = e["valore"]
    rend_annuo = {}
    for anno, mesi in rend_per_anno.items():
        cum = 1.0
        for r in mesi.values(): cum *= (1 + r/100)
        rend_annuo[anno] = round((cum-1)*100, 2)

    # Benchmark mensili
    def rend_mensili_bm(ticker):
        d = etf_data.get(ticker)
        if not d: return {}, {}
        n = min(len(d["closes"]), len(d["dates"]))
        pairs = [(d["dates"][i], d["closes"][i]) for i in range(n) if d["dates"][i] >= backtest_start]
        if not pairs: return {}, {}
        mc = defaultdict(list)
        for dt, cl in pairs: mc[dt[:7]].append(cl)
        mesi_ord = sorted(mc.keys())
        rpa = defaultdict(dict); ra = {}
        prev = mc[mesi_ord[0]][0]
        for mese in mesi_ord:
            last = mc[mese][-1]
            ret = round((last - prev) / prev * 100, 2) if prev else 0
            anno, m = mese.split("-")
            rpa[anno][m] = ret
            prev = last
        for anno, mesi in rpa.items():
            cum = 1.0
            for r in mesi.values(): cum *= (1 + r/100)
            ra[anno] = round((cum-1)*100, 2)
        return dict(rpa), ra

    rend_iwmo_mese, rend_iwmo_anno = rend_mensili_bm(BENCHMARK)
    rend_vwce_mese, rend_vwce_anno = rend_mensili_bm(BENCHMARK2)

    # Turnover
    turnovers = []
    for i in range(1, len(versioni)):
        pc = set(p["ticker"] for p in versioni[i-1]["composizione"])
        cc = set(p["ticker"] for p in versioni[i]["composizione"])
        ch = len(pc.symmetric_difference(cc))
        tot = max(len(pc), len(cc))
        if tot > 0: turnovers.append(ch / tot * 100)
    turnover_medio = round(sum(turnovers)/len(turnovers), 1) if turnovers else 0

    # Statistiche per n_segnali
    perf_per_step = defaultdict(list)
    for v in versioni:
        ns = v["n_segnali"]
        if v["data"] in rendimenti:
            perf_per_step[ns].append(rendimenti[v["data"]])
    perf_step_summary = {
        str(ns): {
            "media_sett": round(sum(rl)/len(rl), 3),
            "n": len(rl),
            "label": ["100% momentum","70% mom + 30% XEON","30% mom + 70% XEON","100% XEON"][min(ns,3)],
        }
        for ns, rl in perf_per_step.items()
    }

    return {
        "performance_totale_pct": perf_tot,
        "performance_totale_eur": round(capitale_corrente - CAPITALE, 2),
        "capitale_attuale":       round(capitale_corrente, 2),
        "max_drawdown":           mdd,
        "sharpe_6m":              sh6,
        "sharpe_12m":             sh12,
        "rolling_sharpe":         rolling_sh,
        "drawdown_series":        dd_series,
        "rend_per_anno":          dict(rend_per_anno),
        "rend_annuo":             rend_annuo,
        "rend_iwmo_mese":         rend_iwmo_mese,
        "rend_iwmo_anno":         rend_iwmo_anno,
        "rend_vwce_mese":         rend_vwce_mese,
        "rend_vwce_anno":         rend_vwce_anno,
        "turnover_medio":         turnover_medio,
        "perf_per_step":          perf_step_summary,
        "versioni":               versioni,
        "composizione_corrente":  composizione_attuale,
        "rendimenti":             rendimenti,
        "equity_mensile":         equity_mensile,
        "storia_segnali":         storia_segnali[-30:],
        "n_rebalancing":          len(versioni),
        "data_ingresso_map":      data_ingresso_map,
    }

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    oggi = datetime.date.today().isoformat()
    print(f"COMPASS ETP v3.0 IWMO+ — {oggi}")
    print(f"Universo: {len(UNIVERSE)} ETF momentum puri | Benchmark: {BENCHMARK}")

    # Run number
    run_number = 1
    if OUT_FILE.exists():
        try:
            ex = json.loads(OUT_FILE.read_text())
            run_number = ex.get("run_number", 0) + 1
        except: pass
    print(f"Run: {run_number}")

    # ── Download ETF universo + XEON + benchmark ───────────────────────────
    tickers = list({e["t"] for e in UNIVERSE}) + [XEON["t"], BENCHMARK, BENCHMARK2]
    tickers = list(set(tickers))
    print(f"\n[1/3] Download {len(tickers)} ticker (900gg)...")
    etf_data = {}
    ok = err = 0
    for i, ticker in enumerate(sorted(tickers), 1):
        d = fetch_yahoo(ticker, days=900)
        if d:
            etf_data[ticker] = d
            cl = closes_at(etf_data, ticker, oggi)
            sc = calc_score(cl)
            score_str = f"score={sc['score']:.0f} mom6M={sc['mom6m']:+.1f}%" if sc else "score=n.d."
            print(f"  [{i}/{len(tickers)}] {ticker}... OK {score_str}")
            ok += 1
        else:
            print(f"  [{i}/{len(tickers)}] {ticker}... ERR")
            err += 1
        time.sleep(0.3)
    print(f"  Download: {ok} OK, {err} ERR")

    # Segnali IWMO oggi
    cl_iwmo = closes_at(etf_data, "IWMO.MI", oggi)
    n_seg_oggi, dettaglio_seg_oggi = calc_segnali_iwmo(cl_iwmo)
    qa_oggi = quota_azionario(n_seg_oggi)
    print(f"\n  Segnali IWMO oggi: {n_seg_oggi}/3 → quota azionario {qa_oggi*100:.0f}%")
    print(f"  {dettaglio_seg_oggi['descrizione']}")

    # ── Backtest ───────────────────────────────────────────────────────────
    print(f"\n[2/3] Backtest IWMO+ (da {BACKTEST_START}, rebalancing ogni {REBAL_DAYS}gg)...")
    risultato = run_backtest(etf_data, BACKTEST_START, oggi)
    print(f"  Performance: {risultato['performance_totale_pct']:+.1f}% | "
          f"MDD: {risultato['max_drawdown']:.1f}% | "
          f"Turnover: {risultato['turnover_medio']:.0f}%")
    print(f"  Sharpe 6M: {risultato['sharpe_6m']} | Sharpe 12M: {risultato['sharpe_12m']}")
    print(f"  Rebalancing: {risultato['n_rebalancing']}")

    # ── Benchmark ──────────────────────────────────────────────────────────
    print(f"\n[3/3] Benchmark {BENCHMARK} + {BENCHMARK2}...")
    def bm_perf(ticker):
        cl = closes_at(etf_data, ticker, oggi)
        d  = etf_data.get(ticker)
        if not d or not cl: return None
        p_start = get_price_on_date(etf_data, ticker, BACKTEST_START)
        return round((cl[-1] - p_start) / p_start * 100, 2) if p_start else None

    bm1 = bm_perf(BENCHMARK)
    bm2 = bm_perf(BENCHMARK2)
    outperf1 = round(risultato["performance_totale_pct"] - bm1, 2) if bm1 else None
    outperf2 = round(risultato["performance_totale_pct"] - bm2, 2) if bm2 else None
    if bm1: print(f"  {BENCHMARK}: {bm1:+.1f}% | Outperf: {outperf1:+.1f}pp")
    if bm2: print(f"  {BENCHMARK2}: {bm2:+.1f}% | Outperf: {outperf2:+.1f}pp")

    # ── Output JSON ────────────────────────────────────────────────────────
    output = {
        "generated":      datetime.datetime.utcnow().isoformat(),
        "version":        "etp_3.0",
        "run_number":     run_number,
        "strategy":       "COMPASS ETP v3.0 — IWMO+ Momentum Puro",
        "backtest_start": BACKTEST_START,
        "benchmark":      BENCHMARK,
        "benchmark2":     BENCHMARK2,
        "n_etf_universo": len(UNIVERSE),
        "segnali_oggi":   {
            "n_segnali":    n_seg_oggi,
            "quota_az_pct": round(qa_oggi * 100, 0),
            **dettaglio_seg_oggi,
        },
        "benchmark_perf":   bm1,
        "benchmark2_perf":  bm2,
        "outperformance":   outperf1,
        "outperformance2":  outperf2,
        "batte_benchmark":  (risultato["performance_totale_pct"] > bm1) if bm1 else None,
        "config": {
            "n_etf_min": N_ETF_MIN,
            "n_etf_max": N_ETF_MAX,
            "soglia_rotazione": SOGLIA_ROTAZIONE,
            "iwmo_cap_pct": IWMO_CAP,
            "rebal_days": REBAL_DAYS,
            "score": "mom6M×0.40 + mom3M×0.35 + mom1M×0.25 × ER × KAMA",
            "uscita": "S1=mom1M<0 | S2=prezzo<KAMA↓ | S3=sotto max60gg>10%",
        },
        **risultato,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size = OUT_FILE.stat().st_size / 1024
    print(f"\n✅ Done → {OUT_FILE} ({size:.0f} KB)")
    print(f"\n   Portafoglio corrente (segnali={n_seg_oggi}, quota az={qa_oggi*100:.0f}%):")
    for pos in risultato["composizione_corrente"]:
        print(f"   {pos['ticker']:<14} {pos['peso']:>5.1f}% | "
              f"{pos.get('azione','—'):<10} | "
              f"mom6M={pos.get('mom6m',0):+.1f}% "
              f"mom3M={pos.get('mom3m',0):+.1f}% "
              f"er={pos.get('er',0):.2f}")

if __name__ == "__main__":
    main()

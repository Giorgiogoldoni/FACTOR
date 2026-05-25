"""
FASE 2 — PATCH PER compass_3linee.py v1.0
==========================================
Aggiunge la logica di rotation del capitale tra le 3 linee.

ISTRUZIONI DI INTEGRAZIONE (4 punti):

1. Incolla BLOCCO_COSTANTI subito dopo RANGE_REGIME (riga ~78)
2. Incolla BLOCCO_FUNZIONE subito dopo calc_sharpe() e prima di calc_total_return()
3. Nel main(), aggiungi BLOCCO_CHIAMATA dopo il blocco "# Outperformance"
4. Nel dict "output = {...}" aggiungi:  "fase2": risultato_fase2,
"""

# ══════════════════════════════════════════════════════════════════════
# BLOCCO_COSTANTI
# ══════════════════════════════════════════════════════════════════════

FASE2_ALLOC_NORMALE = {
    "euforia":      {"M":  5, "O": 10, "A": 85},
    "goldilocks":   {"M":  5, "O": 20, "A": 75},
    "neutro":       {"M":  5, "O": 40, "A": 55},
    "reflazione":   {"M":  5, "O": 45, "A": 50},
    "stagflazione": {"M":  5, "O": 65, "A": 30},
}

FASE2_REGIMI_CRISI = {
    "risk_off", "recessione", "pandemic", "financial", "war", "sovereign"
}

# score_crisi = regime_crisis_pct * 0.6 + drawdown_A * 0.4
# (s_min, s_max, livello, M%, O%, A%)
# None su O/A = usa FASE2_ALLOC_NORMALE per regime corrente
FASE2_SOGLIE_CRISI = [
    (  0,  30, "normale",   5,  None, None),
    ( 30,  55, "lieve",    20,    60,   20),
    ( 55,  75, "piena",    50,    30,   20),
    ( 75, 100, "totale",  100,     0,    0),
]

# Rientro graduale dopo fine crisi
# (sett_da, sett_a, nome, M%, O%, A%)
# None su O/A = usa FASE2_ALLOC_NORMALE per regime corrente (rientro completato)
FASE2_RIENTRO = [
    (0, 2,  "rientro_1", 70,   15,   15),
    (2, 4,  "rientro_2", 30,   30,   40),
    (4, 99, "rientro_3",  5, None, None),
]

FASE2_SOGLIA_RIBILANCIO_PCT = 3.0  # non muovere se delta < 3% del totale


# ══════════════════════════════════════════════════════════════════════
# BLOCCO_FUNZIONE
# ══════════════════════════════════════════════════════════════════════

def calcola_fase2(portafogli, regime_corrente, stato_precedente=None):
    """
    Calcola l'allocazione ottimale tra le 3 linee (Fase 2 — rotation tattica).

    Logica:
    - M = 5% fisso salvo crisi sistemica (può arrivare a 100%)
    - La rotation normale avviene SOLO tra O e A
    - Crisi = regime_crisis_pct * 0.6 + drawdown_A * 0.4
    - Rientro dalla crisi: graduale in 3 step (sett 1, 3, 5)

    Args:
        portafogli:        dict con risultati backtest {"M":..., "O":..., "A":...}
        regime_corrente:   string dal classificatore (euforia, goldilocks, ...)
        stato_precedente:  dict _stato salvato nel JSON del run precedente

    Returns:
        dict completo con allocazione, capitali target, movimenti, stato
    """
    import datetime

    oggi = datetime.date.today().isoformat()
    stato_prev = stato_precedente or {}

    # ── 1. regime_crisis_pct ──────────────────────────────────────────
    regime_crisis_pct = 100.0 if regime_corrente in FASE2_REGIMI_CRISI else 0.0

    # ── 2. drawdown corrente Linea A ──────────────────────────────────
    drawdown_A = 0.0
    ptf_A = portafogli.get("A", {})
    if ptf_A:
        cap_att = ptf_A.get("capitale_attuale", 0)
        storia  = ptf_A.get("storia", [])
        picco   = max(
            (v.get("capitale_attuale", 0) for v in storia),
            default=cap_att
        )
        picco = max(picco, float(CAPITALE))
        if picco > 0 and cap_att < picco:
            drawdown_A = round((picco - cap_att) / picco * 100, 2)

    # ── 3. score crisi ────────────────────────────────────────────────
    score_crisi = round(regime_crisis_pct * 0.6 + drawdown_A * 0.4, 1)

    # ── 4. livello crisi ──────────────────────────────────────────────
    livello_crisi = "normale"
    m_pct = o_pct = a_pct = None
    for s_min, s_max, livello, m, o, a in FASE2_SOGLIE_CRISI:
        if s_min <= score_crisi < s_max:
            livello_crisi, m_pct, o_pct, a_pct = livello, m, o, a
            break

    # ── 5. stato rientro ──────────────────────────────────────────────
    in_rientro      = stato_prev.get("in_rientro", False)
    data_fine_crisi = stato_prev.get("data_fine_crisi")
    step_rientro    = stato_prev.get("step_rientro", 0)
    livello_prev    = stato_prev.get("livello_crisi", "normale")

    crisi_prev = livello_prev not in ("normale",)
    crisi_now  = livello_crisi not in ("normale",)

    # Fine crisi → avvia rientro graduale
    if crisi_prev and not crisi_now and not in_rientro:
        in_rientro      = True
        data_fine_crisi = oggi
        step_rientro    = 0

    # Score risale in rientro → blocca e torna a crisi
    if in_rientro and crisi_now:
        in_rientro      = False
        data_fine_crisi = None
        step_rientro    = 0

    # Settimane trascorse dalla fine crisi
    settimane_rientro = 0
    if in_rientro and data_fine_crisi:
        try:
            delta = (datetime.date.fromisoformat(oggi) -
                     datetime.date.fromisoformat(data_fine_crisi))
            settimane_rientro = delta.days // 7
        except Exception:
            settimane_rientro = 0

    # ── 6. allocazione finale ─────────────────────────────────────────
    motivo = ""

    if crisi_now:
        motivo = (f"Crisi {livello_crisi} — score {score_crisi:.0f} "
                  f"(regime_crisis {regime_crisis_pct:.0f}% + dd_A {drawdown_A:.1f}%)")

    elif in_rientro:
        step_trovato = False
        for idx, (s_da, s_a, step_nome, m_r, o_r, a_r) in enumerate(FASE2_RIENTRO):
            if s_da <= settimane_rientro < s_a:
                step_rientro = idx
                m_pct, o_pct, a_pct = m_r, o_r, a_r
                # Step finale (None = usa allocazione normale)
                if o_pct is None or a_pct is None:
                    alloc  = FASE2_ALLOC_NORMALE.get(regime_corrente,
                                                      FASE2_ALLOC_NORMALE["neutro"])
                    m_pct  = alloc["M"]
                    o_pct  = alloc["O"]
                    a_pct  = alloc["A"]
                    in_rientro = False
                    motivo = f"Rientro completato — regime {regime_corrente}"
                else:
                    motivo = f"Rientro {step_nome} — sett {settimane_rientro}"
                step_trovato = True
                break
        if not step_trovato:
            # Oltre tutti gli step → rientro completato
            in_rientro = False
            alloc  = FASE2_ALLOC_NORMALE.get(regime_corrente, FASE2_ALLOC_NORMALE["neutro"])
            m_pct  = alloc["M"]
            o_pct  = alloc["O"]
            a_pct  = alloc["A"]
            motivo = f"Rientro completato — regime {regime_corrente}"

    else:
        alloc  = FASE2_ALLOC_NORMALE.get(regime_corrente, FASE2_ALLOC_NORMALE["neutro"])
        m_pct  = alloc["M"]
        o_pct  = alloc["O"]
        a_pct  = alloc["A"]
        motivo = f"Regime {regime_corrente} — allocazione normale"

    # ── 7. normalizza a 100 ───────────────────────────────────────────
    if m_pct is not None and o_pct is not None and a_pct is not None:
        tot = m_pct + o_pct + a_pct
        if abs(tot - 100) > 0.5:
            residuo = 100.0 - m_pct
            if (o_pct + a_pct) > 0:
                f = residuo / (o_pct + a_pct)
                o_pct = round(o_pct * f, 1)
                a_pct = round(100.0 - m_pct - o_pct, 1)

    # ── 8. capitali e movimenti ───────────────────────────────────────
    cap_totale = sum(
        portafogli.get(lid, {}).get("capitale_attuale", float(CAPITALE))
        for lid in ["M", "O", "A"]
    )

    cap_M_tgt = round(cap_totale * m_pct / 100, 2)
    cap_O_tgt = round(cap_totale * o_pct / 100, 2)
    cap_A_tgt = round(cap_totale * a_pct / 100, 2)

    cap_M_now = portafogli.get("M", {}).get("capitale_attuale", float(CAPITALE))
    cap_O_now = portafogli.get("O", {}).get("capitale_attuale", float(CAPITALE))
    cap_A_now = portafogli.get("A", {}).get("capitale_attuale", float(CAPITALE))

    delta_M = round(cap_M_tgt - cap_M_now, 2)
    delta_O = round(cap_O_tgt - cap_O_now, 2)
    delta_A = round(cap_A_tgt - cap_A_now, 2)

    ribilancio_necessario = any(
        abs(d) / cap_totale * 100 > FASE2_SOGLIA_RIBILANCIO_PCT
        for d in [delta_M, delta_O, delta_A]
        if cap_totale > 0
    )

    # ── 9. stato persistente per prossimo run ─────────────────────────
    stato_nuovo = {
        "data":             oggi,
        "livello_crisi":    livello_crisi,
        "score_crisi":      score_crisi,
        "in_rientro":       in_rientro,
        "data_fine_crisi":  data_fine_crisi if in_rientro else None,
        "step_rientro":     step_rientro,
        "settimane_rientro": settimane_rientro,
    }

    # ── 10. output ────────────────────────────────────────────────────
    return {
        "data":               oggi,
        "regime":             regime_corrente,
        "livello_crisi":      livello_crisi,
        "score_crisi":        score_crisi,
        "regime_crisis_pct":  regime_crisis_pct,
        "drawdown_A_pct":     drawdown_A,
        "allocazione_target": {"M": m_pct, "O": o_pct, "A": a_pct},
        "capitali_target":    {
            "M": cap_M_tgt, "O": cap_O_tgt, "A": cap_A_tgt,
            "totale": round(cap_totale, 2),
        },
        "movimenti":          {"M": delta_M, "O": delta_O, "A": delta_A},
        "ribilancio_necessario":  ribilancio_necessario,
        "soglia_ribilancio_pct":  FASE2_SOGLIA_RIBILANCIO_PCT,
        "motivo":             motivo,
        "in_rientro":         in_rientro,
        "data_fine_crisi":    data_fine_crisi if in_rientro else None,
        "settimane_rientro":  settimane_rientro,
        "_stato":             stato_nuovo,   # salvato nel JSON, riletto al prossimo run
    }


# ══════════════════════════════════════════════════════════════════════
# BLOCCO_CHIAMATA  — da incollare nel main() dopo "# Outperformance"
# ══════════════════════════════════════════════════════════════════════
#
#     # ── Fase 2 ───────────────────────────────────────────────────────
#     print(f"\n[5/5] Fase 2 — Rotation capitale...")
#     stato_fase2_prev = existing.get("fase2", {}).get("_stato")
#     risultato_fase2  = calcola_fase2(
#         portafogli        = portafogli,
#         regime_corrente   = sc_oggi,
#         stato_precedente  = stato_fase2_prev,
#     )
#     alloc = risultato_fase2["allocazione_target"]
#     mov   = risultato_fase2["movimenti"]
#     rib   = risultato_fase2["ribilancio_necessario"]
#     print(f"  Livello crisi : {risultato_fase2['livello_crisi']} "
#           f"(score {risultato_fase2['score_crisi']:.0f})")
#     print(f"  Allocaz target: M={alloc['M']}%  O={alloc['O']}%  A={alloc['A']}%")
#     if rib:
#         print(f"  ⚡ RIBILANCIO: M {mov['M']:+,.0f}€ | "
#               f"O {mov['O']:+,.0f}€ | A {mov['A']:+,.0f}€")
#     else:
#         print(f"  ✓ Nessun ribilancio (delta < {risultato_fase2['soglia_ribilancio_pct']}%)")
#
# ══════════════════════════════════════════════════════════════════════
# Nel dict output = {...} aggiungere:
#     "fase2": risultato_fase2,
# ══════════════════════════════════════════════════════════════════════

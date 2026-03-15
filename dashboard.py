"""
╔══════════════════════════════════════════════════════════════╗
║         XAU/USD TRADE LOG — Dashboard Streamlit             ║
║         Se met à jour automatiquement toutes les 30s        ║
╚══════════════════════════════════════════════════════════════╝

LANCEMENT LOCAL :
  streamlit run dashboard.py

HÉBERGEMENT :
  Push sur GitHub → connecter à streamlit.io/cloud
"""

import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# ── Config page ─────────────────────────────────────────────
st.set_page_config(
    page_title="XAU/USD Trade Log",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

STATE_FILE  = "state.json"
TRADES_FILE = "trades.json"

# ── CSS personnalisé ─────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-box {
        background: #1a1d27;
        border-radius: 10px;
        padding: 16px 20px;
        border: 1px solid #2a2d3a;
        text-align: center;
    }
    .metric-label { color: #8b8fa8; font-size: 12px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; }
    .metric-value { font-size: 28px; font-weight: 700; margin-top: 4px; }
    .buy-color  { color: #00d084; }
    .sell-color { color: #ff4d6d; }
    .neutral-color { color: #8b8fa8; }
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
    }
    .badge-buy   { background: #003d21; color: #00d084; }
    .badge-sell  { background: #3d001a; color: #ff4d6d; }
    .badge-wait  { background: #2a2d3a; color: #8b8fa8; }
    .badge-encours { background: #1a2a3a; color: #4da6ff; }
    .zone-box {
        background: #1a1d27;
        border-left: 3px solid;
        padding: 8px 14px;
        border-radius: 0 8px 8px 0;
        margin: 4px 0;
        font-size: 13px;
    }
    .zone-buy  { border-color: #00d084; }
    .zone-sell { border-color: #ff4d6d; }
    .score-bar-bg { background: #2a2d3a; border-radius: 6px; height: 8px; margin-top: 6px; }
    .score-bar-fill { height: 8px; border-radius: 6px; }
    .section-title {
        color: #8b8fa8;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin: 20px 0 10px 0;
        border-bottom: 1px solid #2a2d3a;
        padding-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)


# ── Chargement données ───────────────────────────────────────
def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE) as f:
            data = json.load(f)
        return list(reversed(data))  # Plus récent en premier
    except Exception:
        return []


# ── Helpers ──────────────────────────────────────────────────
def score_color(score, seuil=60):
    if score >= seuil:   return "#00d084"
    if score >= seuil-15: return "#ffb84d"
    return "#ff4d6d"


def bias_badge(bias):
    if bias == "BUY":    return '<span class="badge badge-buy">▲ BUY</span>'
    if bias == "SELL":   return '<span class="badge badge-sell">▼ SELL</span>'
    return '<span class="badge badge-wait">— NEUTRE</span>'


def statut_badge(statut):
    if statut == "EN COURS":   return '<span class="badge badge-encours">⟳ EN COURS</span>'
    if statut == "TP ATTEINT": return '<span class="badge badge-buy">✓ TP</span>'
    if statut == "SL TOUCHÉ":  return '<span class="badge badge-sell">✗ SL</span>'
    return f'<span class="badge badge-wait">{statut}</span>'


def dow_icon(dow):
    return {"BULL": "▲ BULL", "BEAR": "▼ BEAR"}.get(dow, "— NEUT")


# ══════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ══════════════════════════════════════════════════════════════

# Header
st.markdown("## 📊 XAU/USD — Smart Money Analyzer")

# Auto-refresh
refresh = st.empty()

state  = load_state()
trades = load_trades()

# ── ÉTAT EN TEMPS RÉEL ───────────────────────────────────────
if state:
    ts   = state.get("timestamp", "")
    prix = state.get("prix", 0)
    bias = state.get("bias", "NEUTRE")
    score_actif = state.get("score_actif", 0)
    seuil       = state.get("seuil", 60)
    amd_phase   = state.get("amd_phase", "?")
    amd_trade   = state.get("amd_trade", False)
    signal_fort = state.get("signal_fort", False)

    # Timestamp
    try:
        dt = datetime.fromisoformat(ts)
        ts_str = dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        ts_str = ts

    st.markdown(f"<small style='color:#5a5f7a'>Dernière mise à jour : {ts_str}</small>", unsafe_allow_html=True)

    # ── LIGNE 1 — Métriques principales ─────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)

    color_prix = "#00d084" if bias == "BUY" else ("#ff4d6d" if bias == "SELL" else "#ffffff")
    with c1:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">XAU/USD</div>
            <div class="metric-value" style="color:{color_prix}">{prix:.2f}</div>
        </div>""", unsafe_allow_html=True)

    bias_color = "#00d084" if bias == "BUY" else ("#ff4d6d" if bias == "SELL" else "#8b8fa8")
    bias_arrow = "▲" if bias == "BUY" else ("▼" if bias == "SELL" else "—")
    with c2:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">Biais</div>
            <div class="metric-value" style="color:{bias_color}">{bias_arrow} {bias}</div>
        </div>""", unsafe_allow_html=True)

    sc_color = score_color(score_actif, seuil)
    with c3:
        bar_pct = int(score_actif)
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">Score</div>
            <div class="metric-value" style="color:{sc_color}">{score_actif}<small style="font-size:14px;color:#5a5f7a">/100</small></div>
            <div class="score-bar-bg">
                <div class="score-bar-fill" style="width:{bar_pct}%;background:{sc_color}"></div>
            </div>
        </div>""", unsafe_allow_html=True)

    amd_color = "#00d084" if amd_trade else "#ffb84d"
    with c4:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">AMD</div>
            <div class="metric-value" style="color:{amd_color};font-size:18px">{amd_phase}</div>
        </div>""", unsafe_allow_html=True)

    sig_color = "#00d084" if signal_fort else "#5a5f7a"
    sig_text  = "SIGNAL ✓" if signal_fort else "EN ATTENTE"
    with c5:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">Statut</div>
            <div class="metric-value" style="color:{sig_color};font-size:18px">{sig_text}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── LIGNE 2 — Détails ────────────────────────────────────
    col_left, col_mid, col_right = st.columns([1, 1, 1])

    with col_left:
        st.markdown('<div class="section-title">Structure Multi-TF</div>', unsafe_allow_html=True)
        tfs = [
            ("H4",  state.get("h4_dow",  "?")),
            ("H1",  state.get("h1_dow",  "?")),
            ("M15", state.get("m15_dow", "?")),
            ("M5",  state.get("m5_dow",  "?")),
        ]
        for tf, dow in tfs:
            dcolor = "#00d084" if dow == "BULL" else ("#ff4d6d" if dow == "BEAR" else "#8b8fa8")
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1d27">
                <span style="color:#8b8fa8;font-size:13px">{tf}</span>
                <span style="color:{dcolor};font-size:13px;font-weight:700">{dow_icon(dow)}</span>
            </div>""", unsafe_allow_html=True)

        # Momentum
        st.markdown('<div class="section-title" style="margin-top:16px">Momentum M5</div>', unsafe_allow_html=True)
        rsi = state.get("rsi", 0)
        macd_bull = state.get("macd_bull", False)
        macd_bear = state.get("macd_bear", False)
        macd_ok   = (bias == "BUY" and macd_bull) or (bias == "SELL" and macd_bear)
        rsi_ok    = (bias == "BUY" and 50 <= rsi <= 70) or (bias == "SELL" and 30 <= rsi <= 50)
        st.markdown(f"""
        <div style="padding:6px 0">
            <span style="color:{'#00d084' if macd_ok else '#5a5f7a'}">{'✅' if macd_ok else '⏳'} MACD</span>
            &nbsp;&nbsp;
            <span style="color:{'#00d084' if rsi_ok else '#5a5f7a'}">{'✅' if rsi_ok else '⏳'} RSI {rsi:.0f}</span>
        </div>""", unsafe_allow_html=True)

    with col_mid:
        st.markdown('<div class="section-title">Plan de Trade</div>', unsafe_allow_html=True)
        entree = state.get("entree", "—")
        sl     = state.get("sl", "—")
        tps    = state.get("tps", [])

        rows = [
            ("Entrée", entree, "#ffffff"),
            ("Stop Loss", sl, "#ff4d6d"),
        ]
        for i, tp in enumerate(tps[:3], 1):
            rows.append((f"TP{i}", f"{tp[0]:.2f}  ← {tp[1]} [{tp[2]}]", "#00d084"))

        for label, val, color in rows:
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #1a1d27">
                <span style="color:#8b8fa8;font-size:13px">{label}</span>
                <span style="color:{color};font-size:13px;font-weight:700">{val}</span>
            </div>""", unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="section-title">Zones Actives</div>', unsafe_allow_html=True)
        zones = state.get("zones_sell" if bias == "SELL" else "zones_buy", [])
        icons = {"OB": "🔲", "FVG": "⬜", "BREAKER": "💥"}
        zone_color = "zone-sell" if bias == "SELL" else "zone-buy"
        if zones:
            for z in zones[:4]:
                prio, tf_z, type_z, bas_z, mid_z, haut_z, statut_z = z
                icon = icons.get(type_z, "▪")
                st.markdown(f"""
                <div class="zone-box {zone_color}">
                    {icon} <b>{type_z}</b> [{tf_z}]
                    <span style="color:#8b8fa8;font-size:12px"> {bas_z:.2f} – {haut_z:.2f}</span>
                    <span style="float:right;font-size:11px;color:#5a5f7a">{statut_z}</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#5a5f7a;font-size:13px">Aucune zone dans le sens du biais</span>',
                        unsafe_allow_html=True)

        # Scores BUY vs SELL
        st.markdown('<div class="section-title" style="margin-top:16px">BUY vs SELL</div>',
                    unsafe_allow_html=True)
        sb = state.get("score_buy", 0)
        ss = state.get("score_sell", 0)
        for label, score, color in [("BUY", sb, "#00d084"), ("SELL", ss, "#ff4d6d")]:
            st.markdown(f"""
            <div style="margin:6px 0">
                <div style="display:flex;justify-content:space-between;margin-bottom:3px">
                    <span style="color:{color};font-size:12px;font-weight:700">{label}</span>
                    <span style="color:{color};font-size:12px">{score}/100</span>
                </div>
                <div class="score-bar-bg">
                    <div class="score-bar-fill" style="width:{score}%;background:{color}"></div>
                </div>
            </div>""", unsafe_allow_html=True)

else:
    st.warning("⏳ En attente des données... Lance le bot d'abord : `python bot_xauusd_v5.py`")


# ══════════════════════════════════════════════════════════════
# TRADE LOG
# ══════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 📋 Trade Log — Historique des Signaux")

if trades:
    # Stats rapides
    total = len(trades)
    buys  = sum(1 for t in trades if t.get("bias") == "BUY")
    sells = total - buys
    tp_ok = sum(1 for t in trades if t.get("statut") == "TP ATTEINT")
    sl_ok = sum(1 for t in trades if t.get("statut") == "SL TOUCHÉ")
    en_cours = sum(1 for t in trades if t.get("statut") == "EN COURS")

    m1, m2, m3, m4, m5 = st.columns(5)
    for col, label, val, color in [
        (m1, "Total Signaux", total, "#ffffff"),
        (m2, "BUY",  buys,  "#00d084"),
        (m3, "SELL", sells, "#ff4d6d"),
        (m4, "TP ✓", tp_ok, "#00d084"),
        (m5, "En cours", en_cours, "#4da6ff"),
    ]:
        with col:
            st.markdown(f"""
            <div class="metric-box">
                <div class="metric-label">{label}</div>
                <div class="metric-value" style="color:{color};font-size:24px">{val}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")

    # Tableau
    df = pd.DataFrame(trades)

    # Colonnes à afficher
    cols_affichage = {
        "date"    : "Date",
        "bias"    : "Biais",
        "score"   : "Score",
        "style"   : "Style",
        "prix"    : "Prix",
        "entree"  : "Entrée",
        "sl"      : "SL",
        "tp1"     : "TP1",
        "tp2"     : "TP2",
        "zone"    : "Zone",
        "amd"     : "AMD",
        "statut"  : "Statut",
        "pips"    : "Pips",
    }

    available = [c for c in cols_affichage if c in df.columns]
    df_display = df[available].rename(columns=cols_affichage)

    # Coloriser
    def color_bias(val):
        if val == "BUY":  return "color: #00d084; font-weight: bold"
        if val == "SELL": return "color: #ff4d6d; font-weight: bold"
        return ""

    def color_statut(val):
        if val == "TP ATTEINT": return "color: #00d084"
        if val == "SL TOUCHÉ":  return "color: #ff4d6d"
        if val == "EN COURS":   return "color: #4da6ff"
        return ""

    def color_score(val):
        try:
            v = int(val)
            if v >= 60: return "color: #00d084"
            if v >= 50: return "color: #ffb84d"
            return "color: #ff4d6d"
        except Exception:
            return ""

    styled = df_display.style \
        .applymap(color_bias,    subset=["Biais"]  if "Biais"  in df_display.columns else []) \
        .applymap(color_statut,  subset=["Statut"] if "Statut" in df_display.columns else []) \
        .applymap(color_score,   subset=["Score"]  if "Score"  in df_display.columns else []) \
        .set_properties(**{"background-color": "#1a1d27", "color": "#e0e0e0",
                           "border": "1px solid #2a2d3a", "font-size": "13px"}) \
        .set_table_styles([{
            "selector": "th",
            "props": [("background-color", "#13151f"), ("color", "#8b8fa8"),
                      ("font-size", "11px"), ("letter-spacing", "1px"),
                      ("text-transform", "uppercase"), ("border", "1px solid #2a2d3a")]
        }])

    st.dataframe(df_display, use_container_width=True, height=400)

    # Export CSV
    csv = df_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ Exporter CSV",
        data=csv,
        file_name=f"trades_xauusd_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

else:
    st.info("📭 Aucun signal enregistré — les signaux forts apparaîtront ici automatiquement.")

# ── Auto-refresh toutes les 30s ──────────────────────────────
st.markdown("---")
st.markdown(
    "<small style='color:#3a3d4a'>Dashboard auto-refresh toutes les 30s · "
    "XAU/USD SMC Analyzer V5.0</small>",
    unsafe_allow_html=True
)

# Refresh automatique
st.markdown("""
<script>
setTimeout(function() { window.location.reload(); }, 30000);
</script>
""", unsafe_allow_html=True)

"""
╔══════════════════════════════════════════════════════════════╗
║         XAU/USD SMART MONEY ANALYZER  —  V5.1               ║
║         + Telegram 3 niveaux d'alerte                        ║
║           → Signal fort    : immédiat                        ║
║           → Alerte zone    : prix dans zone                  ║
║           → Rapport 15min  : toujours, même si AMD bloque    ║
║         + Export JSON pour dashboard Streamlit               ║
║         Intervalle : 5 minutes                               ║
╚══════════════════════════════════════════════════════════════╝

INSTALLATION :
  pip install twelvedata yfinance pandas numpy requests python-dotenv

LANCEMENT :
  python bot_xauusd_v5.py
"""

import os
import json
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

TWELVE_API_KEY  = os.getenv("TWELVE_API_KEY", "180a175c29ee4fcfa29420d02acb2cc0")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID")
SYMBOL_TD       = "XAU/USD"
SYMBOL_YF       = "GC=F"
SLEEP_SECONDS   = 300   # 5 minutes

STATE_FILE      = "state.json"
TRADES_FILE     = "trades.json"

# ── Alertes Telegram ──────────────────────────────────────────
RAPPORT_INTERVAL = 900   # rapport toutes les 15 minutes (15 * 60)
_last_rapport    = 0     # timestamp dernier rapport
_last_signal     = ""    # dernier signal envoyé (évite doublons)

TF_MAP = {
    "H4" : {"td": "4h",    "yf": "4h",  "yf_period": "60d", "nb": 200},
    "H1" : {"td": "1h",    "yf": "1h",  "yf_period": "30d", "nb": 200},
    "M15": {"td": "15min", "yf": "15m", "yf_period": "8d",  "nb": 200},
    "M5" : {"td": "5min",  "yf": "5m",  "yf_period": "5d",  "nb": 200},
    "M1" : {"td": "1min",  "yf": "1m",  "yf_period": "1d",  "nb": 100},
}

SCORE_INTRADAY = 60
SCORE_SCALP    = 50

SCORES = {
    "h4_dow"    : 10,
    "h1_dow"    :  8,
    "amd"       :  7,
    "mss"       : 10,
    "ob"        :  8,
    "fvg"       :  8,
    "breaker"   :  7,
    "liquidity" :  7,
    "macd"      :  8,
    "rsi"       :  7,
    "ema"       :  5,
    "candle"    :  8,
    "m1_confirm":  7,
}


# ══════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  [TG] Token ou chat_id manquant dans .env")
        return False
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            print("  [TG] ✅ Message envoyé")
            return True
        else:
            print(f"  [TG] ✗ Erreur {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"  [TG] Exception : {e}")
        return False


# ── NIVEAU 1 : Signal fort ────────────────────────────────────
def format_signal_fort(analysis, bias_dir, score_buy, score_sell,
                       style, seuil, score_actif,
                       zones_buy, zones_sell, entree, sl, tps):
    ts    = datetime.now().strftime("%d/%m %H:%M")
    prix  = (analysis.get("M5") or {}).get("close", 0)
    amd   = analysis.get("amd", {})
    arrow = "🟢 BUY" if bias_dir == "BUY" else "🔴 SELL"

    filled = int(score_actif / 10)
    bar    = "█" * filled + "░" * (10 - filled)

    lines = [
        f"🚀 <b>SIGNAL FORT — {arrow}</b> | {ts}",
        f"💰 Prix : <b>{prix:.2f}</b>",
        f"",
        f"⏰ AMD : {amd.get('phase','?')} — {amd.get('conseil','')}",
        f"📊 H4 : {(analysis.get('H4') or {}).get('dow','?')}  |  H1 : {(analysis.get('H1') or {}).get('dow','?')}",
        f"",
        f"🎯 <b>BIAIS : {arrow}</b>",
        f"📈 Score : <b>{score_actif}/100</b>  [{bar}]",
        f"🏷 Style : {style}  (seuil {seuil}pts)",
        f"",
    ]

    zones = zones_sell if bias_dir == "SELL" else zones_buy
    if zones:
        lines.append("📍 <b>Zones actives :</b>")
        for z in zones[:3]:
            prio, tf_z, type_z, bas_z, mid_z, haut_z, statut_z = z
            lines.append(f"  • {type_z} [{tf_z}]  {bas_z:.2f}–{haut_z:.2f}  <i>{statut_z}</i>")
        lines.append("")

    m5  = analysis.get("M5") or {}
    mom = m5.get("momentum", {})
    cn, cd = m5.get("candle", (None, None))
    macd_ok   = (bias_dir == "BUY" and mom.get("macd_bull")) or (bias_dir == "SELL" and mom.get("macd_bear"))
    rsi_ok    = (bias_dir == "BUY" and mom.get("rsi_bull"))  or (bias_dir == "SELL" and mom.get("rsi_bear"))
    candle_ok = bool(cn and cd == bias_dir)

    lines += [
        f"⚡ <b>Momentum M5 :</b>",
        f"  {'✅' if macd_ok else '❌'} MACD  {'✅' if rsi_ok else '❌'} RSI {mom.get('rsi',0):.0f}  {'✅' if candle_ok else '❌'} {cn or '—'}",
        f"",
        f"🎯 <b>PLAN DE TRADE :</b>",
        f"  Entrée : <b>{entree}</b>",
        f"  SL     : {sl}",
    ]

    if tps:
        a = "▼" if bias_dir == "SELL" else "▲"
        for i, (tp_p, tp_type, tp_tf) in enumerate(tps[:3], 1):
            gain = round(abs(float(entree) - tp_p) * 10, 0)
            lines.append(f"  TP{i} {a} {tp_p:.2f}  +{gain:.0f} pips  ← {tp_type} [{tp_tf}]")

    nb_ok = sum([macd_ok, rsi_ok, candle_ok])
    lines += [
        f"",
        f"{'✅ PRÊT À ENTRER' if nb_ok >= 2 else '⏳ Attendre chandelier M5'}  ({nb_ok}/3)",
    ]
    return "\n".join(lines)


# ── NIVEAU 2 : Alerte zone ────────────────────────────────────
def format_alerte_zone(analysis, bias_dir, score_actif, prix, zone):
    ts    = datetime.now().strftime("%d/%m %H:%M")
    prio, tf_z, type_z, bas_z, mid_z, haut_z, statut_z = zone
    arrow = "🟢 BUY" if bias_dir == "BUY" else "🔴 SELL"
    amd   = analysis.get("amd", {})

    m5  = analysis.get("M5") or {}
    mom = m5.get("momentum", {})
    cn, cd = m5.get("candle", (None, None))
    macd_ok   = (bias_dir == "BUY" and mom.get("macd_bull")) or (bias_dir == "SELL" and mom.get("macd_bear"))
    rsi_ok    = (bias_dir == "BUY" and mom.get("rsi_bull"))  or (bias_dir == "SELL" and mom.get("rsi_bear"))
    candle_ok = bool(cn and cd == bias_dir)
    nb_ok     = sum([macd_ok, rsi_ok, candle_ok])
    etat      = "✅ ENTRER" if nb_ok >= 2 else ("⏳ PRESQUE" if nb_ok == 1 else "⏸ ATTENDRE")

    lines = [
        f"⚡ <b>ALERTE ZONE — {type_z} [{tf_z}]</b> | {ts}",
        f"💰 Prix : <b>{prix:.2f}</b>  —  Zone : {bas_z:.2f}–{haut_z:.2f}  ({statut_z})",
        f"",
        f"🎯 Direction : {arrow}  |  Score : {score_actif}/100",
        f"⏰ AMD : {amd.get('phase','?')} — {amd.get('conseil','')}",
        f"",
        f"⚡ Momentum M5 :",
        f"  {'✅' if macd_ok else '❌'} MACD  {'✅' if rsi_ok else '❌'} RSI {mom.get('rsi',0):.0f}  {'✅' if candle_ok else '❌'} {cn or '—'}",
        f"",
        f"<b>{etat}</b>  ({nb_ok}/3 conditions)",
    ]
    if not amd.get("trade"):
        lines.append(f"⚠ AMD {amd.get('phase','?')} — hors DISTRIBUTION, prudence")
    return "\n".join(lines)


# ── NIVEAU 3 : Rapport 15 minutes ────────────────────────────
def format_rapport_15min(analysis, bias_dir, score_buy, score_sell,
                         score_actif, seuil, style, amd, prix,
                         zones_buy, zones_sell, entree, sl):
    ts    = datetime.now().strftime("%d/%m %H:%M")
    arrow = "🟢 BUY" if bias_dir == "BUY" else ("🔴 SELL" if bias_dir == "SELL" else "⚪ NEUTRE")
    trade_ok = amd.get("trade", False)

    filled_b = int(score_buy  / 10)
    filled_s = int(score_sell / 10)
    bar_b    = "█" * filled_b + "░" * (10 - filled_b)
    bar_s    = "█" * filled_s + "░" * (10 - filled_s)

    h4_dow  = (analysis.get("H4")  or {}).get("dow", "?")
    h1_dow  = (analysis.get("H1")  or {}).get("dow", "?")
    m15_dow = (analysis.get("M15") or {}).get("dow", "?")
    m5_dow  = (analysis.get("M5")  or {}).get("dow", "?")

    m5  = analysis.get("M5") or {}
    mom = m5.get("momentum", {})
    cn, cd = m5.get("candle", (None, None))

    # Prochaines zones à surveiller
    zones = zones_sell if bias_dir == "SELL" else zones_buy

    lines = [
        f"📊 <b>XAU/USD — Rapport 15min</b> | {ts}",
        f"💰 Prix : <b>{prix:.2f}</b>",
        f"",
        f"🕯 H4:{h4_dow}  H1:{h1_dow}  M15:{m15_dow}  M5:{m5_dow}",
        f"⏰ AMD : <b>{amd.get('phase','?')}</b>  {'✅ tradeable' if trade_ok else '⏸ attendre'}",
        f"",
        f"🎯 Biais : {arrow}",
        f"📈 BUY  {score_buy:3d}/100  [{bar_b}]",
        f"📉 SELL {score_sell:3d}/100  [{bar_s}]",
        f"",
    ]

    # Statut signal
    if score_actif >= seuil and trade_ok:
        lines.append(f"✅ <b>SIGNAL VALIDE</b> — {style}  Score:{score_actif}/100")
        if entree != "—":
            lines.append(f"   Entrée:{entree}  SL:{sl}")
    elif score_actif >= seuil and not trade_ok:
        lines.append(f"⏳ Score OK ({score_actif}pts) — AMD bloque")
        lines.append(f"   Attendre DISTRIBUTION (13h–21h Maroc)")
        if entree != "—":
            lines.append(f"   Zone en attente : entrée {entree} | SL {sl}")
    else:
        manque = seuil - score_actif
        lines.append(f"⏸ Signal faible — manque {manque}pts")

    # Momentum M5
    macd_str = f"MACD {'✅' if (bias_dir=='BUY' and mom.get('macd_bull')) or (bias_dir=='SELL' and mom.get('macd_bear')) else '❌'}"
    rsi_str  = f"RSI {mom.get('rsi',0):.0f} {'✅' if (bias_dir=='BUY' and mom.get('rsi_bull')) or (bias_dir=='SELL' and mom.get('rsi_bear')) else '❌'}"
    lines += [
        f"",
        f"⚡ M5 : {macd_str}  {rsi_str}  {cn or '—'}",
    ]

    # Zones prioritaires
    if zones:
        lines.append(f"")
        lines.append(f"📍 Zones à surveiller ({('SELL' if bias_dir=='SELL' else 'BUY')}) :")
        for z in zones[:3]:
            prio, tf_z, type_z, bas_z, mid_z, haut_z, statut_z = z
            dist = round(abs(prix - mid_z), 1)
            dir_str = "↑" if mid_z > prix else "↓"
            lines.append(f"  {dir_str} {type_z}[{tf_z}] mid:{mid_z:.2f}  {dist}pts  {statut_z}")

    lines += ["", f"🔄 Prochain rapport dans 15min"]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# PERSISTANCE JSON
# ══════════════════════════════════════════════════════════════

def save_state(state_data):
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f, indent=2, default=str)


def save_trade(trade_data):
    trades = []
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE) as f:
                trades = json.load(f)
        except Exception:
            trades = []
    trades.append(trade_data)
    trades = trades[-200:]
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def push_to_github():
    try:
        os.system("git add state.json trades.json")
        os.system('git commit -m "update state"')
        os.system("git push")
        print("  [GIT] ✅ Pushed to GitHub")
    except Exception as e:
        print(f"  [GIT] Erreur : {e}")


# ══════════════════════════════════════════════════════════════
# DOUBLE SOURCE — TWELVE DATA + YFINANCE
# ══════════════════════════════════════════════════════════════

_source_status = {"active": None}


def fetch_twelvedata(tf_name):
    cfg = TF_MAP[tf_name]
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol"    : SYMBOL_TD,
        "interval"  : cfg["td"],
        "outputsize": cfg["nb"],
        "apikey"    : TWELVE_API_KEY,
        "format"    : "JSON",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "error":
            return None
        values = data.get("values", [])
        if not values:
            return None
        df = pd.DataFrame(values)
        df = df.rename(columns={"datetime": "time"})
        df["time"] = pd.to_datetime(df["time"])
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        if "volume" in df.columns:
            df["volume"] = df["volume"].astype(float)
        df = df.sort_values("time").reset_index(drop=True)
        return df
    except Exception:
        return None


def fetch_yfinance(tf_name):
    try:
        import yfinance as yf
        cfg    = TF_MAP[tf_name]
        ticker = yf.Ticker(SYMBOL_YF)
        df     = ticker.history(period=cfg["yf_period"], interval=cfg["yf"])
        if df is None or len(df) < 20:
            return None
        df = df.reset_index()
        df = df.rename(columns={
            "Datetime": "time", "Date": "time",
            "Open": "open", "High": "high",
            "Low": "low", "Close": "close",
            "Volume": "volume"
        })
        df["time"] = pd.to_datetime(df["time"])
        df = df[["time", "open", "high", "low", "close"]].copy()
        df = df.sort_values("time").reset_index(drop=True)
        nb = cfg["nb"]
        if len(df) > nb:
            df = df.tail(nb).reset_index(drop=True)
        return df
    except Exception:
        return None


def get_data(tf_name):
    df = fetch_twelvedata(tf_name)
    if df is not None and len(df) >= 50:
        _source_status["active"] = "TD"
        return df, "TD"
    print(f"  ⚡ {tf_name} : Twelve Data → bascule yfinance")
    df = fetch_yfinance(tf_name)
    if df is not None and len(df) >= 50:
        _source_status["active"] = "YF"
        return df, "YF"
    return None, None


# ══════════════════════════════════════════════════════════════
# INDICATEURS
# ══════════════════════════════════════════════════════════════

def calculate_indicators(df):
    df = df.copy()
    df["ema_fast"]   = df["close"].ewm(span=9,  adjust=False).mean()
    df["ema_slow"]   = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_trend"]  = df["close"].ewm(span=50, adjust=False).mean()
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    df["rsi"]        = 100 - (100 / (1 + gain / (loss + 1e-10)))
    ema_f            = df["close"].ewm(span=12, adjust=False).mean()
    ema_s            = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"]       = ema_f - ema_s
    df["macd_sig"]   = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]  = df["macd"] - df["macd_sig"]
    df["tr"]         = np.maximum(
        df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift()),
                   abs(df["low"]  - df["close"].shift()))
    )
    df["atr"]        = df["tr"].ewm(span=14, adjust=False).mean()
    df["body"]       = abs(df["close"] - df["open"])
    df["upper_wick"] = df["high"] - df[["close", "open"]].max(axis=1)
    df["lower_wick"] = df[["close", "open"]].min(axis=1) - df["low"]
    df["total_size"] = df["high"] - df["low"]
    df["is_bull"]    = df["close"] > df["open"]
    df["is_bear"]    = df["close"] < df["open"]
    return df


# ══════════════════════════════════════════════════════════════
# DÉTECTIONS SMC
# ══════════════════════════════════════════════════════════════

def dow_theory(df):
    highs = df["high"].values
    lows  = df["low"].values
    swing_highs, swing_lows = [], []
    for i in range(2, min(20, len(df) - 2)):
        idx = -i
        if highs[idx] > highs[idx-1] and highs[idx] > highs[idx+1]:
            swing_highs.append(highs[idx])
        if lows[idx] < lows[idx-1] and lows[idx] < lows[idx+1]:
            swing_lows.append(lows[idx])
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        if swing_highs[0] > swing_highs[1] and swing_lows[0] > swing_lows[1]:
            return "BULL"
        if swing_highs[0] < swing_highs[1] and swing_lows[0] < swing_lows[1]:
            return "BEAR"
    last = df.iloc[-1]
    if last["close"] > last["ema_trend"]: return "BULL"
    if last["close"] < last["ema_trend"]: return "BEAR"
    return "NEUTRAL"


def detect_amd_phase():
    h = datetime.now(timezone.utc).hour
    if 0 <= h < 7:
        return {"phase": "ACCUMULATION", "code": "A", "trade": False,
                "conseil": "Range asiatique — institutions accumulent"}
    if 7 <= h < 12:
        return {"phase": "MANIPULATION", "code": "M", "trade": False,
                "conseil": "London open — faux spike probable"}
    if 12 <= h < 20:
        return {"phase": "DISTRIBUTION", "code": "D", "trade": True,
                "conseil": "New York actif — vrai mouvement directionnel"}
    return {"phase": "TRANSITION", "code": "T", "trade": True,
            "conseil": "Fin NY — volume en baisse, prudence"}


def detect_mss(df):
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    swing_high = max(highs[-20:-3])
    swing_low  = min(lows[-20:-3])
    if closes[-2] <= swing_high and closes[-1] > swing_high:
        force = min(3, int((closes[-1] - swing_high) / swing_high * 1000) + 1)
        return {"dir": "BULL", "force": force, "niveau": round(swing_high, 2)}
    if closes[-2] >= swing_low and closes[-1] < swing_low:
        force = min(3, int((swing_low - closes[-1]) / swing_low * 1000) + 1)
        return {"dir": "BEAR", "force": force, "niveau": round(swing_low, 2)}
    return None


def detect_order_block(df):
    lc       = df["close"].iloc[-1]
    avg_body = df["body"].iloc[-20:].mean()
    for i in range(5, 25):
        c  = df.iloc[-i]
        n1 = df.iloc[-i + 1]
        n2 = df.iloc[-i + 2]
        impulse = abs(n2["close"] - n1["open"])
        if c["is_bear"] and n1["is_bull"] and impulse > avg_body * 1.5:
            top, bottom = round(c["high"], 2), round(c["low"], 2)
            mid    = round((top + bottom) / 2, 2)
            inside = bottom <= lc <= top
            proche = not inside and abs(lc - mid) / mid < 0.005
            return {"dir": "BULL", "top": top, "mid": mid, "bottom": bottom,
                    "inside": inside, "proche": proche, "dist": round(abs(lc - mid), 2)}
        if c["is_bull"] and n1["is_bear"] and impulse > avg_body * 1.5:
            top, bottom = round(c["high"], 2), round(c["low"], 2)
            mid    = round((top + bottom) / 2, 2)
            inside = bottom <= lc <= top
            proche = not inside and abs(lc - mid) / mid < 0.005
            return {"dir": "BEAR", "top": top, "mid": mid, "bottom": bottom,
                    "inside": inside, "proche": proche, "dist": round(abs(lc - mid), 2)}
    return None


def detect_fvg(df):
    b1, b3 = df.iloc[-3], df.iloc[-1]
    lc = b3["close"]
    if b1["high"] < b3["low"]:
        bas, haut = round(b1["high"], 2), round(b3["low"], 2)
        taille    = round(haut - bas, 2)
        milieu    = round((bas + haut) / 2, 2)
        comble    = round(min(100, max(0, (lc - bas) / (taille + 1e-5) * 100)), 1)
        return {"dir": "BULL", "bas": bas, "milieu": milieu, "haut": haut,
                "taille": taille, "in_zone": bas <= lc <= haut, "comble": comble}
    if b1["low"] > b3["high"]:
        bas, haut = round(b3["high"], 2), round(b1["low"], 2)
        taille    = round(haut - bas, 2)
        milieu    = round((bas + haut) / 2, 2)
        comble    = round(min(100, max(0, (haut - lc) / (taille + 1e-5) * 100)), 1)
        return {"dir": "BEAR", "bas": bas, "milieu": milieu, "haut": haut,
                "taille": taille, "in_zone": bas <= lc <= haut, "comble": comble}
    return None


def detect_breaker(df):
    lc       = df["close"].iloc[-1]
    avg_body = df["body"].iloc[-20:].mean()
    for i in range(8, 30):
        c  = df.iloc[-i]
        n1 = df.iloc[-i + 1]
        n2 = df.iloc[-i + 2]
        impulse = abs(n2["close"] - n1["open"])
        if c["is_bull"] and n1["is_bear"] and impulse > avg_body * 1.5:
            ob_top, ob_bottom = c["high"], c["low"]
            prices_after = df["close"].iloc[-i+3:-1]
            if len(prices_after) > 0 and prices_after.min() < ob_bottom:
                mid    = round((ob_top + ob_bottom) / 2, 2)
                proche = abs(lc - ob_top) / ob_top < 0.003
                return {"dir": "BULL", "top": round(ob_top, 2),
                        "bottom": round(ob_bottom, 2), "milieu": mid, "proche": proche}
        if c["is_bear"] and n1["is_bull"] and impulse > avg_body * 1.5:
            ob_top, ob_bottom = c["high"], c["low"]
            prices_after = df["close"].iloc[-i+3:-1]
            if len(prices_after) > 0 and prices_after.max() > ob_top:
                mid    = round((ob_top + ob_bottom) / 2, 2)
                proche = abs(lc - ob_bottom) / ob_bottom < 0.003
                return {"dir": "BEAR", "top": round(ob_top, 2),
                        "bottom": round(ob_bottom, 2), "milieu": mid, "proche": proche}
    return None


def detect_liquidity(df):
    highs = df["high"].values[-30:]
    lows  = df["low"].values[-30:]
    lc    = df["close"].iloc[-1]
    tol   = 0.0005
    eq_highs, eq_lows = [], []
    for i in range(len(highs) - 1):
        for j in range(i + 1, len(highs)):
            if abs(highs[i] - highs[j]) / (highs[i] + 1e-10) < tol:
                eq_highs.append(round((highs[i] + highs[j]) / 2, 2))
    for i in range(len(lows) - 1):
        for j in range(i + 1, len(lows)):
            if abs(lows[i] - lows[j]) / (lows[i] + 1e-10) < tol:
                eq_lows.append(round((lows[i] + lows[j]) / 2, 2))
    result = {}
    if eq_highs:
        n = max(set(eq_highs), key=eq_highs.count)
        result["equal_highs"] = {"niveau": n, "distance": round(abs(lc - n), 2), "au_dessus": lc < n}
    if eq_lows:
        n = max(set(eq_lows), key=eq_lows.count)
        result["equal_lows"]  = {"niveau": n, "distance": round(abs(lc - n), 2), "en_dessous": lc > n}
    return result if result else None


def get_momentum(df):
    last, prev = df.iloc[-1], df.iloc[-2]
    mh  = last["macd_hist"]
    rsi = last["rsi"]
    return {
        "macd_hist": round(mh, 3),
        "macd_bull": mh > 0 and mh > prev["macd_hist"],
        "macd_bear": mh < 0 and mh < prev["macd_hist"],
        "rsi"      : round(rsi, 1),
        "rsi_bull" : (50 <= rsi <= 70) or rsi < 30,
        "rsi_bear" : (30 <= rsi <= 50) or rsi > 70,
        "ema_bull" : last["ema_fast"] > last["ema_slow"] and last["ema_fast"] > last["ema_trend"],
        "ema_bear" : last["ema_fast"] < last["ema_slow"] and last["ema_fast"] < last["ema_trend"],
    }


def detect_candle(df):
    if len(df) < 3:
        return None, None
    c, p1, p2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    avg = df["close"].iloc[-20:].mean()
    cb  = abs(c["close"] - c["open"])
    ct  = c["high"] - c["low"]
    cuw = c["high"] - max(c["close"], c["open"])
    clw = min(c["close"], c["open"]) - c["low"]
    pb  = abs(p1["close"] - p1["open"])
    p2b = abs(p2["close"] - p2["open"])
    p2t = p2["high"] - p2["low"]
    pt  = p1["high"] - p1["low"]
    if cb < ct * 0.1:                                                          return "Doji",             "NEUTRAL"
    if clw >= 2*cb and cuw <= cb*0.5 and cb > 0 and c["close"] < avg:         return "Marteau",          "BUY"
    if clw >= 2*cb and cuw <= cb*0.5 and cb > 0 and c["close"] > avg:         return "Pendu",            "SELL"
    if cuw >= 2*cb and clw <= cb*0.5 and cb > 0 and c["close"] < avg:         return "Marteau Inverse",  "BUY"
    if cuw >= 2*cb and clw <= cb*0.5 and cb > 0 and c["close"] > avg:         return "Etoile Filante",   "SELL"
    if p1["is_bear"] and c["is_bull"] and c["open"] <= p1["close"] and c["close"] >= p1["open"] and cb > pb:
        return "Avalement Haussier", "BUY"
    if p1["is_bull"] and c["is_bear"] and c["open"] >= p1["close"] and c["close"] <= p1["open"] and cb > pb:
        return "Avalement Baissier", "SELL"
    if (p2["is_bear"] and p2b > p2t*0.5 and pb < pt*0.3 and
            c["is_bull"] and cb > ct*0.5 and c["close"] > (p2["open"]+p2["close"])/2):
        return "Etoile du Matin", "BUY"
    if (p2["is_bull"] and p2b > p2t*0.5 and pb < pt*0.3 and
            c["is_bear"] and cb > ct*0.5 and c["close"] < (p2["open"]+p2["close"])/2):
        return "Etoile du Soir", "SELL"
    return None, None


# ══════════════════════════════════════════════════════════════
# ANALYSE COMPLÈTE
# ══════════════════════════════════════════════════════════════

def analyze_all():
    analysis = {}
    sources  = {}
    for tf_name in ["H4", "H1", "M15", "M5", "M1"]:
        df, src = get_data(tf_name)
        if df is None:
            analysis[tf_name] = None
            continue
        df = calculate_indicators(df)
        sources[tf_name] = src
        last = df.iloc[-1]
        data = {
            "close"   : round(last["close"], 2),
            "atr"     : round(last["atr"], 2),
            "source"  : src,
            "dow"     : dow_theory(df),
            "momentum": get_momentum(df),
            "candle"  : detect_candle(df),
        }
        if tf_name in ("H1", "M15", "M5"):
            data["mss"]     = detect_mss(df)
            data["ob"]      = detect_order_block(df)
            data["fvg"]     = detect_fvg(df)
            data["breaker"] = detect_breaker(df)
            data["liq"]     = detect_liquidity(df)
        analysis[tf_name] = data
    analysis["amd"]     = detect_amd_phase()
    analysis["sources"] = sources
    return analysis


# ══════════════════════════════════════════════════════════════
# SCORING
# ══════════════════════════════════════════════════════════════

def calculate_score(analysis, direction):
    is_buy   = direction == "BUY"
    bull_dir = "BULL" if is_buy else "BEAR"
    blocs    = {"A": 0, "B": 0, "C": 0, "D": 0}
    details  = []

    h4 = analysis.get("H4")
    if h4 and h4["dow"] == bull_dir:
        blocs["A"] += SCORES["h4_dow"]
        details.append(("A", f"H4 Dow {bull_dir}", f"+{SCORES['h4_dow']}pts", True))
    elif h4:
        details.append(("A", f"H4 Dow {h4['dow']}", "contre direction", False))

    h1 = analysis.get("H1")
    if h1 and h1["dow"] == bull_dir:
        blocs["A"] += SCORES["h1_dow"]
        details.append(("A", f"H1 Dow {bull_dir}", f"+{SCORES['h1_dow']}pts", True))
    elif h1:
        details.append(("A", f"H1 Dow {h1['dow']}", "contre direction", False))

    amd = analysis.get("amd", {})
    if amd.get("trade"):
        blocs["A"] += SCORES["amd"]
        details.append(("A", f"AMD {amd['phase']}", f"+{SCORES['amd']}pts", True))
    else:
        details.append(("A", f"AMD {amd.get('phase','?')}", "phase défavorable", False))

    sw = {"H1": 1.0, "M15": 0.8, "M5": 0.6}
    for tf_name, w in sw.items():
        tf = analysis.get(tf_name)
        if not tf:
            continue
        mss = tf.get("mss")
        if mss and mss["dir"] == bull_dir:
            pts = round(SCORES["mss"] * w * (mss["force"] / 3))
            blocs["B"] += pts
            details.append(("B", f"MSS {bull_dir} [{tf_name}]", f"+{pts}pts force {mss['force']}/3", True))
        ob = tf.get("ob")
        if ob and ob["dir"] == bull_dir:
            mult = 1.0 if ob["inside"] else (0.7 if ob["proche"] else 0.4)
            pts  = round(SCORES["ob"] * w * mult)
            if pts > 0:
                statut = "DEDANS" if ob["inside"] else ("PROCHE" if ob["proche"] else "zone")
                blocs["B"] += pts
                details.append(("B", f"OB {bull_dir} [{tf_name}]", f"+{pts}pts {statut}", True))
        fvg = tf.get("fvg")
        if fvg and fvg["dir"] == bull_dir:
            mult = 1.0 if fvg["in_zone"] else 0.5
            pts  = round(SCORES["fvg"] * w * mult)
            if pts > 0:
                blocs["B"] += pts
                details.append(("B", f"FVG {bull_dir} [{tf_name}]", f"+{pts}pts gap:{fvg['taille']}pts", True))
        bb = tf.get("breaker")
        if bb and bb["dir"] == bull_dir:
            mult = 1.0 if bb["proche"] else 0.5
            pts  = round(SCORES["breaker"] * w * mult)
            if pts > 0:
                blocs["B"] += pts
                details.append(("B", f"Breaker {bull_dir} [{tf_name}]", f"+{pts}pts", True))
        liq = tf.get("liq")
        if liq:
            if is_buy and "equal_lows" in liq and liq["equal_lows"]["en_dessous"]:
                pts = round(SCORES["liquidity"] * w)
                blocs["B"] += pts
                details.append(("B", f"Liq EqLows [{tf_name}]", f"+{pts}pts", True))
            if not is_buy and "equal_highs" in liq and liq["equal_highs"]["au_dessus"]:
                pts = round(SCORES["liquidity"] * w)
                blocs["B"] += pts
                details.append(("B", f"Liq EqHighs [{tf_name}]", f"+{pts}pts", True))
    blocs["B"] = min(40, blocs["B"])

    mw = {"M15": 0.5, "M5": 0.5}
    for tf_name, w in mw.items():
        tf = analysis.get(tf_name)
        if not tf:
            continue
        mom = tf["momentum"]
        if (is_buy and mom["macd_bull"]) or (not is_buy and mom["macd_bear"]):
            pts = round(SCORES["macd"] * w)
            blocs["C"] += pts
            arrow = "↑" if is_buy else "↓"
            details.append(("C", f"MACD {arrow} [{tf_name}]", f"+{pts}pts", True))
        if (is_buy and mom["rsi_bull"]) or (not is_buy and mom["rsi_bear"]):
            pts = round(SCORES["rsi"] * w)
            blocs["C"] += pts
            details.append(("C", f"RSI [{tf_name}]", f"+{pts}pts val:{mom['rsi']}", True))
        if (is_buy and mom["ema_bull"]) or (not is_buy and mom["ema_bear"]):
            pts = round(SCORES["ema"] * w)
            blocs["C"] += pts
            details.append(("C", f"EMA [{tf_name}]", f"+{pts}pts aligné", True))

    m5 = analysis.get("M5")
    if m5:
        cn, cd = m5["candle"]
        if cn and cd == direction:
            blocs["D"] += SCORES["candle"]
            details.append(("D", f"{cn} [M5]", f"+{SCORES['candle']}pts", True))
    m1 = analysis.get("M1")
    if m1:
        mom1  = m1["momentum"]
        m1_ok = ((is_buy and mom1["macd_bull"]) or (not is_buy and mom1["macd_bear"])) and m1["dow"] == bull_dir
        if m1_ok:
            blocs["D"] += SCORES["m1_confirm"]
            details.append(("D", "M1 confirm", f"+{SCORES['m1_confirm']}pts", True))

    score = min(100, max(0, blocs["A"] + blocs["B"] + blocs["C"] + blocs["D"]))
    return score, blocs, details


def get_bias(analysis):
    h4_dow = (analysis.get("H4") or {}).get("dow", "NEUTRAL")
    h1_dow = (analysis.get("H1") or {}).get("dow", "NEUTRAL")
    if h4_dow == "BULL" and h1_dow == "BULL":    return "BUY",  "H4 BULL + H1 BULL"
    if h4_dow == "BEAR" and h1_dow == "BEAR":    return "SELL", "H4 BEAR + H1 BEAR"
    if h4_dow == "BULL" and h1_dow == "NEUTRAL": return "BUY",  "H4 BULL + H1 NEUTRAL (faible)"
    if h4_dow == "BEAR" and h1_dow == "NEUTRAL": return "SELL", "H4 BEAR + H1 NEUTRAL (faible)"
    return None, f"Conflit H4:{h4_dow} / H1:{h1_dow}"


def get_style(analysis, direction):
    bull_dir = "BULL" if direction == "BUY" else "BEAR"
    m15, m5  = analysis.get("M15") or {}, analysis.get("M5") or {}
    m15_active = (
        (m15.get("ob")  and m15["ob"]["dir"]  == bull_dir and (m15["ob"]["inside"] or m15["ob"]["proche"])) or
        (m15.get("fvg") and m15["fvg"]["dir"] == bull_dir and m15["fvg"]["in_zone"]) or
        (m15.get("mss") and m15["mss"]["dir"] == bull_dir)
    )
    m5_active = (
        (m5.get("ob")  and m5["ob"]["dir"]  == bull_dir and (m5["ob"]["inside"] or m5["ob"]["proche"])) or
        (m5.get("fvg") and m5["fvg"]["dir"] == bull_dir and m5["fvg"]["in_zone"])
    )
    if m15_active: return "INTRADAY", SCORE_INTRADAY
    if m5_active:  return "SCALP",    SCORE_SCALP
    return "INTRADAY", SCORE_INTRADAY


def collect_zones(analysis):
    zones_buy, zones_sell = [], []
    for tf_name in ["H1", "M15", "M5"]:
        tf    = analysis.get(tf_name) or {}
        poids = {"H1": 3, "M15": 2, "M5": 1}[tf_name]
        ob = tf.get("ob")
        if ob:
            statut = "DEDANS" if ob["inside"] else ("PROCHE" if ob["proche"] else "zone")
            bonus  = 3 if ob["inside"] else (2 if ob["proche"] else 0)
            entry  = (poids + bonus, tf_name, "OB", ob["bottom"], ob["mid"], ob["top"], statut)
            if ob["dir"] == "BULL": zones_buy.append(entry)
            else:                   zones_sell.append(entry)
        fvg = tf.get("fvg")
        if fvg:
            statut = "DEDANS" if fvg["in_zone"] else "attente"
            bonus  = 3 if fvg["in_zone"] else 0
            entry  = (poids + bonus, tf_name, "FVG", fvg["bas"], fvg["milieu"], fvg["haut"], statut)
            if fvg["dir"] == "BULL": zones_buy.append(entry)
            else:                    zones_sell.append(entry)
        bb = tf.get("breaker")
        if bb:
            statut = "PROCHE" if bb["proche"] else "zone"
            bonus  = 2 if bb["proche"] else 0
            entry  = (poids + bonus, tf_name, "BREAKER", bb["bottom"], bb["milieu"], bb["top"], statut)
            if bb["dir"] == "BULL": zones_buy.append(entry)
            else:                   zones_sell.append(entry)
        liq = tf.get("liq")
        if liq:
            if "equal_highs" in liq:
                eq = liq["equal_highs"]
                zones_sell.append((poids, tf_name, "LIQ EqHighs",
                                   eq["niveau"]-1, eq["niveau"], eq["niveau"]+1,
                                   "AU DESSUS" if eq["au_dessus"] else "ATTEINT"))
            if "equal_lows" in liq:
                eq = liq["equal_lows"]
                zones_buy.append((poids, tf_name, "LIQ EqLows",
                                  eq["niveau"]-1, eq["niveau"], eq["niveau"]+1,
                                  "EN DESSOUS" if eq["en_dessous"] else "ATTEINT"))
    zones_buy.sort(key=lambda x: -x[0])
    zones_sell.sort(key=lambda x: -x[0])
    return zones_buy, zones_sell


def build_trade_plan(analysis, bias_dir, zones_buy, zones_sell, score_actif, seuil):
    prix   = (analysis.get("M5") or {}).get("close", 0)
    entree = "—"
    sl     = "—"
    tps    = []

    if score_actif < seuil:
        return entree, sl, tps

    zones_actives = zones_sell if bias_dir == "SELL" else zones_buy
    zones_contre  = zones_buy  if bias_dir == "SELL" else zones_sell

    zone_entree = None
    for z in zones_actives:
        if z[6] in ("DEDANS", "PROCHE"):
            zone_entree = z
            break
    if not zone_entree and zones_actives:
        zone_entree = zones_actives[0]

    if zone_entree:
        prio, tf_z, type_z, bas_z, mid_z, haut_z, statut_z = zone_entree
        entree = str(mid_z)
        if bias_dir == "SELL":
            sl = str(round(haut_z + 1.5, 2))
            for z in zones_contre:
                if z[4] < prix:
                    tps.append((z[4], z[2], z[1]))
        else:
            sl = str(round(bas_z - 1.5, 2))
            for z in zones_contre:
                if z[4] > prix:
                    tps.append((z[4], z[2], z[1]))
        tps = sorted(set(tps), key=lambda x: x[0] if bias_dir == "SELL" else -x[0])[:3]

    return entree, sl, tps


# ══════════════════════════════════════════════════════════════
# CYCLE PRINCIPAL
# ══════════════════════════════════════════════════════════════

def run_cycle():
    global _last_rapport, _last_signal

    ts  = datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{ts}] Analyse en cours...")

    analysis = analyze_all()

    score_buy,  blocs_buy,  details_buy  = calculate_score(analysis, "BUY")
    score_sell, blocs_sell, details_sell = calculate_score(analysis, "SELL")

    bias_dir, bias_reason = get_bias(analysis)
    amd      = analysis.get("amd", {})
    trade_ok = amd.get("trade", False)
    prix     = (analysis.get("M5") or {}).get("close", 0)

    if bias_dir:
        style, seuil = get_style(analysis, bias_dir)
        score_actif  = score_buy if bias_dir == "BUY" else score_sell
    else:
        style, seuil, score_actif = "—", 60, 0

    zones_buy, zones_sell = collect_zones(analysis)
    entree, sl, tps = build_trade_plan(
        analysis, bias_dir or "BUY",
        zones_buy, zones_sell, score_actif, seuil
    )

    # ── Affichage terminal ───────────────────────────────────
    arrow = "▲ BUY" if bias_dir == "BUY" else ("▼ SELL" if bias_dir == "SELL" else "— NEUTRE")
    print(f"  Prix    : {prix:.2f}")
    print(f"  Biais   : {arrow}  |  Score : {score_actif}/100  |  Seuil : {seuil}")
    print(f"  AMD     : {amd.get('phase','?')}  {'✅ TRADE' if trade_ok else '⏸ WAIT'}")
    if entree != "—":
        print(f"  Entrée  : {entree}  |  SL : {sl}")

    # ── State JSON ───────────────────────────────────────────
    m5  = analysis.get("M5") or {}
    mom = m5.get("momentum", {})

    state = {
        "timestamp"   : datetime.now().isoformat(),
        "prix"        : prix,
        "bias"        : bias_dir or "NEUTRE",
        "bias_reason" : bias_reason,
        "score_buy"   : score_buy,
        "score_sell"  : score_sell,
        "score_actif" : score_actif,
        "seuil"       : seuil,
        "style"       : style,
        "amd_phase"   : amd.get("phase", "?"),
        "amd_trade"   : trade_ok,
        "amd_conseil" : amd.get("conseil", ""),
        "h4_dow"      : (analysis.get("H4")  or {}).get("dow", "?"),
        "h1_dow"      : (analysis.get("H1")  or {}).get("dow", "?"),
        "m15_dow"     : (analysis.get("M15") or {}).get("dow", "?"),
        "m5_dow"      : (analysis.get("M5")  or {}).get("dow", "?"),
        "macd_bull"   : mom.get("macd_bull", False),
        "macd_bear"   : mom.get("macd_bear", False),
        "rsi"         : mom.get("rsi", 0),
        "entree"      : entree,
        "sl"          : sl,
        "tps"         : [[t[0], t[1], t[2]] for t in tps],
        "zones_buy"   : [[z[0], z[1], z[2], z[3], z[4], z[5], z[6]] for z in zones_buy[:5]],
        "zones_sell"  : [[z[0], z[1], z[2], z[3], z[4], z[5], z[6]] for z in zones_sell[:5]],
        "signal_fort" : (bias_dir is not None and score_actif >= seuil and trade_ok),
    }
    save_state(state)

    # ══ TELEGRAM — 3 NIVEAUX ═══════════════════════════════
    now_ts = time.time()

    # ─── NIVEAU 1 : Signal fort (AMD + score + biais) ────────
    signal_key = f"{bias_dir}_{entree}_{score_actif}"
    if state["signal_fort"] and entree != "—" and signal_key != _last_signal:
        print("  🚀 NIVEAU 1 — Signal fort → Telegram")
        msg = format_signal_fort(
            analysis, bias_dir, score_buy, score_sell,
            style, seuil, score_actif,
            zones_buy, zones_sell, entree, sl, tps
        )
        if send_telegram(msg):
            _last_signal = signal_key

        trade = {
            "date"     : datetime.now().strftime("%d/%m/%Y %H:%M"),
            "timestamp": datetime.now().isoformat(),
            "bias"     : bias_dir,
            "score"    : score_actif,
            "style"    : style,
            "prix"     : prix,
            "entree"   : entree,
            "sl"       : sl,
            "tp1"      : tps[0][0] if len(tps) > 0 else "—",
            "tp2"      : tps[1][0] if len(tps) > 1 else "—",
            "tp3"      : tps[2][0] if len(tps) > 2 else "—",
            "zone"     : (zones_sell if bias_dir == "SELL" else zones_buy)[0][2]
                         if (zones_sell if bias_dir == "SELL" else zones_buy) else "—",
            "amd"      : amd.get("phase", "?"),
            "h4"       : (analysis.get("H4") or {}).get("dow", "?"),
            "h1"       : (analysis.get("H1") or {}).get("dow", "?"),
            "statut"   : "EN COURS",
            "resultat" : "",
            "pips"     : "",
        }
        save_trade(trade)
        print(f"  📝 Trade loggé dans {TRADES_FILE}")

    # ─── NIVEAU 2 : Alerte zone (prix entré dans zone) ────────
    elif bias_dir:
        zones_actives = zones_sell if bias_dir == "SELL" else zones_buy
        for z in zones_actives[:3]:
            prio, tf_z, type_z, bas_z, mid_z, haut_z, statut_z = z
            if statut_z in ("DEDANS", "PROCHE"):
                zone_key = f"zone_{tf_z}_{type_z}_{mid_z}"
                if zone_key != _last_signal:
                    print(f"  ⚡ NIVEAU 2 — Zone atteinte {type_z}[{tf_z}] → Telegram")
                    msg = format_alerte_zone(analysis, bias_dir, score_actif, prix, z)
                    if send_telegram(msg):
                        _last_signal = zone_key
                break

    # ─── NIVEAU 3 : Rapport toutes les 15 minutes ─────────────
    if now_ts - _last_rapport >= RAPPORT_INTERVAL:
        print("  🕐 NIVEAU 3 — Rapport 15min → Telegram")
        msg = format_rapport_15min(
            analysis, bias_dir, score_buy, score_sell,
            score_actif, seuil, style, amd, prix,
            zones_buy, zones_sell, entree, sl
        )
        if send_telegram(msg):
            _last_rapport = now_ts

    # ── Statut terminal ──────────────────────────────────────
    if not state["signal_fort"]:
        reason = "Score insuffisant"   if score_actif < seuil else \
                 "Phase AMD défavorable" if not trade_ok       else \
                 "Pas de biais clair"
        print(f"  ⏸ Pas de signal fort — {reason}")

    push_to_github()
    return state


# ══════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def run():
    print("\n" + "═" * 64)
    print("  XAU/USD  SMART MONEY ANALYZER  V5.1")
    print("  Telegram : 3 niveaux d'alerte")
    print(f"  Rapport  : toutes les {RAPPORT_INTERVAL//60} minutes")
    print(f"  Intervalle analyse : {SLEEP_SECONDS//60} minutes")
    print("  Ctrl+C pour arrêter")
    print("═" * 64 + "\n")

    if not TELEGRAM_TOKEN:
        print("  ⚠  TELEGRAM_TOKEN manquant dans .env — alertes désactivées\n")

    while True:
        try:
            now     = datetime.now(timezone.utc)
            weekday = now.weekday()
            h       = now.hour

            if weekday == 4 and h >= 21:
                print(f"  [{datetime.now().strftime('%H:%M')}] Weekend — marché fermé.")
                time.sleep(300)
                continue
            if weekday == 5:
                print(f"  [{datetime.now().strftime('%H:%M')}] Samedi — marché fermé.")
                time.sleep(300)
                continue
            if weekday == 6 and h < 21:
                print(f"  [{datetime.now().strftime('%H:%M')}] Dimanche — marché fermé.")
                time.sleep(300)
                continue

            run_cycle()

        except KeyboardInterrupt:
            print("\n  Arrêt du bot.")
            break
        except Exception as e:
            print(f"  Erreur : {e}")
            import traceback
            traceback.print_exc()

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    run()

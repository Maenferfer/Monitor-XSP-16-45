import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz
import streamlit as st
import time as sleep_timer

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="The Oracle v7.0", layout="wide")

# --- SEGURIDAD Y CONSTANTES ---
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'

def check_noticias_pro(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS", "TARIFF", "TRADE WAR", "RETAIL SALES", "EARNINGS"]
    hoy = str(date.today())
    url = f"https://finnhub.io{hoy}&to={hoy}&token={api_key}"
    estado = {"bloqueo": False, "eventos": []}
    try:
        r = requests.get(url, timeout=5).json().get('economicCalendar', [])
        for ev in r:
            if ev.get('country') == 'US' and str(ev.get('impact', '')).lower() in ['high', '3', '4']:
                nombre = ev['event'].upper()
                if any(k in nombre for k in eventos_prohibidos):
                    h_utc = datetime.strptime(ev['time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                    h_es = h_utc.astimezone(ZONA_HORARIA).time()
                    estado["eventos"].append(f"{ev['event']} ({h_es.strftime('%H:%M')})")
                    if time(14, 00) <= h_es <= time(21, 00): estado["bloqueo"] = True
        return estado
    except: return estado

def calcular_streak_dias(df_diario):
    closes = df_diario['Close'].tail(10).values
    if len(closes) < 2: return 0
    streak = 0
    direction = 1 if closes[-1] > closes[-2] else -1
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] - closes[i-1]) * direction > 0: streak += direction
        else: break
    return streak

def obtener_datos_maestros():
    try:
        tickers = {"XSP": "^XSP", "SPY": "SPY", "RSP": "RSP", "VIX": "^VIX", "VIX9D": "^VIX9D", "SKEW": "^SKEW", "TNX": "^TNX", "PCCE": "PCCE"}
        raw_data = {}
        for k, v in tickers.items():
            t = yf.Ticker(v)
            df = t.history(period="7d", interval="1m")
            if df.empty: df = t.history(period="7d", interval="1d")
            raw_data[k] = df
        
        df_x = raw_data["XSP"] if not raw_data["XSP"].empty else raw_data["SPY"]
        factor = 10 if "SPY" in str(df_x) else 1
        
        actual = float(df_x['Close'].iloc[-1]) * factor
        apertura = float(df_x['Open'].iloc[-1]) * factor
        prev_close = float(df_x['Close'].iloc[-2]) * factor

        def calc_rsi(series, p):
            delta = series.diff()
            g = (delta.where(delta > 0, 0)).rolling(window=p).mean()
            l = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
            return 100 - (100 / (1 + (g / l.replace(0, np.nan)))).iloc[-1]

        df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
        if df_diario.empty: df_diario = yf.Ticker("SPY").history(period="30d", interval="1d")
        
        atr14 = (df_diario['High'] - df_diario['Low']).tail(14).mean() * factor
        streak = calcular_streak_dias(df_diario)
        cierre_diario = df_diario['Close'] * factor
        std_20 = cierre_diario.tail(20).std()
        z_score = (cierre_diario.iloc[-1] - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0
        
        inside_day = (df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and df_diario['Low'].iloc[-1] > df_diario['Low'].iloc[-2]) if len(df_diario) >= 2 else False

        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d.empty and d['Close'].iloc[-1] > d['Open'].iloc[-1]: votos += 1

        return {
            "actual": actual, "apertura": apertura, "prev": prev_close,
            "ma5": df_x['Close'].tail(5).mean() * factor,
            "rsi_14": calc_rsi(df_x['Close'], 14),
            "vol_rel": df_x['Volume'].iloc[-1] / df_x['Volume'].tail(30).mean() if df_x['Volume'].tail(30).mean() > 0 else 1.0,
            "vix": float(raw_data["VIX"]['Close'].iloc[-1]),
            "vix9d": float(raw_data["VIX9D"]['Close'].iloc[-1]),
            "tnx": float(raw_data["TNX"]['Close'].iloc[-1]),
            "tnx_prev": float(raw_data["TNX"]['Close'].iloc[-2]),
            "pc_ratio": float(raw_data["PCCE"]['Close'].iloc[-1]) if not raw_data["PCCE"].empty else 0.8,
            "rsp_bull": float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]),
            "atr14": atr14, "streak": streak, "z_score": z_score, "inside_day": inside_day,
            "gap_pct": (apertura - prev_close) / prev_close * 100,
            "vix_speed": (float(raw_data["VIX"]['Close'].iloc[-1]) / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "votos_tech": votos, "cambio_15m": (actual - df_x['Close'].iloc[-15] * factor) if len(df_x) > 15 else 0,
            "std_dev": df_x['Close'].std() * factor, "caida_flash": (actual / (df_x['Close'].iloc[-5] * factor) - 1) * 100 if len(df_x) > 5 else 0
        }
    except Exception as e:
        st.error(f"Error obteniendo datos: {e}")
        return None

# --- UI PRINCIPAL ---
st.title("📈 XSP 0DTE Institutional v7.0")
cap = st.sidebar.number_input("Capital Cuenta (€)", value=26000.0, step=1000.0)
lotes_base = int((cap / 25000) * 10)

placeholder = st.empty()

while True:
    with placeholder.container():
        d = obtener_datos_maestros()
        noticias = check_noticias_pro(FINNHUB_API_KEY)
        ahora = datetime.now(ZONA_HORARIA)
        ahora_time = ahora.time()
        
        if d:
            # Lógica de Filtros
            vix_peligro = d["vix"] > d["vix9d"]
            vix_extremo = d["vix"] > 35
            pico_bonos = d["tnx"] > (d["tnx_prev"] * 1.02)
            vix_panico = d["vix_speed"] > 3.5
            divergencia_bonos = (d["tnx"] > d["tnx_prev"]) and (d["actual"] > d["apertura"])
            
            # Cálculo de BIAS
            bias = (d["actual"] > d["prev"] and d["votos_tech"] >= 2 and d["rsp_bull"] and not vix_peligro and not noticias["bloqueo"] and not divergencia_bonos)
            if d["z_score"] > 2.2: bias = False
            if d["z_score"] < -2.2: bias = True

            # Lotes y Strike
            lotes = 0 if (vix_extremo or pico_bonos or vix_panico) else (max(1, lotes_base // 2) if d["vix"] > 25 else (lotes_base + 1 if d["vix"] < 15 else lotes_base))
            if d["inside_day"] and not vix_peligro: lotes = int(lotes * 1.2)

            dist_atr = d["atr14"] * (0.95 if ahora_time >= time(16, 45) else 1.0)
            dist_sigma = d["actual"] * ((d["vix"] / 100) / (252**0.5)) * 1.3
            dist = max(dist_atr, dist_sigma)
            vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)

            # Dashboard
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("XSP Actual", f"{d['actual']:.2f}", f"{d['cambio_15m']:.2f}")
            col2.metric("VIX", f"{d['vix']:.2f}", f"{d['vix_speed']:.2f}%")
            col3.metric("Z-Score", f"{d['z_score']:.2f}")
            col4.metric("Tech Score", f"{d['votos_tech']}/3")

            st.subheader(f"ESTRATEGIA: :blue[{'BULL PUT' if bias else 'BEAR CALL'}]")
            st.info(f"**VENDER STRIKE:** {vender} | **LOTES:** {lotes} | **STOP:** {vender}")
            
            if noticias["bloqueo"]: st.warning(f"⚠️ BLOQUEO POR NOTICIAS: {noticias['eventos']}")
            if vix_extremo: st.error("❌ VIX EXTREMO - NO OPERAR")

        st.write(f"Actualizado: {ahora.strftime('%H:%M:%S')}")
        sleep_timer.sleep(30)
        st.rerun()

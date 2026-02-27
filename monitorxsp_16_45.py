import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz
import time as sleep_timer
import logging

# --- CONFIGURACIÓN ---
warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'

st.set_page_config(page_title="XSP Oracle v8.4", layout="wide")

def check_noticias_pro(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS",
"TARIFF", "TRADE WAR", "RETAIL SALES", "EARNINGS"]
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
        cierre_diario = df_diario['Close'] * factor
        std_20 = cierre_diario.tail(20).std()
        z_score = (actual - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0
        
        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d.empty and d['Close'].iloc[-1] > d['Open'].iloc[-1]: votos += 1

        return {
            "actual": actual, "apertura": apertura, "prev": prev_close, "ma5": df_x['Close'].tail(5).mean() * factor,
            "rsi_14": calc_rsi(df_x['Close'], 14), "std_dev": df_x['Close'].std() * factor, "vol_rel": df_x['Volume'].iloc[-1] / df_x['Volume'].tail(30).mean() if df_x['Volume'].tail(30).mean() > 0 else 1,
            "vix": float(raw_data["VIX"]['Close'].iloc[-1]), "vix9d": float(raw_data["VIX9D"]['Close'].iloc[-1]),
            "skew": float(raw_data["SKEW"]['Close'].iloc[-1]), "tnx": float(raw_data["TNX"]['Close'].iloc[-1]),
            "tnx_prev": float(raw_data["TNX"]['Close'].iloc[-2]), "pc_ratio": float(raw_data["PCCE"]['Close'].iloc[-1]) if not raw_data["PCCE"].empty else 0.8,
            "rsp_bull": float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]),
            "atr14": atr14, "streak": calcular_streak_dias(df_diario), "z_score": z_score, "votos_tech": votos,
            "inside_day": (df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and df_diario['Low'].iloc[-1] > df_diario['Low'].iloc[-2]) if len(df_diario) >= 2 else False,
            "gap_pct": (apertura - prev_close) / prev_close * 100,
            "vix_speed": (float(raw_data["VIX"]['Close'].iloc[-1]) / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "caida_flash": (actual / (df_x['Close'].iloc[-5] * factor) - 1) * 100 if len(df_x) > 5 else 0,
            "cambio_15m": (actual - df_x['Close'].iloc[-15] * factor) if len(df_x) > 15 else 0
        }
    except Exception as e:
        st.error(f"Error: {e}")
        return None

# --- UI STREAMLIT ---
st.title("🏛️ THE ORACLE v8.4 Cloud")
cap = st.sidebar.number_input("Capital Cuenta (€)", value=25000.0)
placeholder = st.empty()

while True:
    d = obtener_datos_maestros()
    noticias = check_noticias_pro(FINNHUB_API_KEY)
    ahora = datetime.now(ZONA_HORARIA)
    
    if d:
        with placeholder.container():
            # Lógica v8.4
            mercado_asentado = ahora.time() >= time(16, 45)
            vix_peligro = d["vix"] > d["vix9d"]
            divergencia_bonos = (d["tnx"] > d["tnx_prev"]) and (d["actual"] > d["apertura"])
            bias = (d["actual"] > d["prev"]) and (d["votos_tech"] >= 2) and d["rsp_bull"] and not vix_peligro and not noticias["bloqueo"] and not divergencia_bonos
            
            if d["z_score"] > 2.2: bias = False
            if d["z_score"] < -2.2: bias = True

            mult = 0.95 if mercado_asentado else 1.0
            dist = max(d["atr14"] * mult, d["actual"] * ((d["vix"] / 100) / (252**0.5)) * 1.3)
            vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)
            if vender % 5 == 0: vender = vender - 1 if bias else vender + 1
            
            # Lotes y Spread Dinámicos
            lotes_base = int((cap / 25000) * 10)
            lotes = int(lotes_base * 1.5) if d["vix"] < 18 else (max(1, lotes_base // 2) if d["vix"] > 25 else lotes_base)
            if abs(d["actual"] - vender) > 5 and d["vix"] < 20: lotes = max(lotes, 15)
            
            ancho = 2 if d["vix"] < 18 else (5 if d["vix"] > 25 else 3)
            comprar = vender - ancho if bias else vender + ancho

            # Display de Datos
            st.markdown(f"### ⏱️ {ahora.strftime('%H:%M:%S')} | **XSP: {d['actual']:.2f}** | **VIX: {d['vix']:.2f}**")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("ATR14", f"{d['atr14']:.2f}")
            c2.metric("Z-Score", f"{d['z_score']:.2f}")
            c3.metric("Bono 10Y", f"{d['tnx']:.2f}")
            c4.metric("Votos Tech", f"{d['votos_tech']}/3")

            if noticias["bloqueo"]: st.error(f"🚫 BLOQUEO NOTICIAS: {noticias['eventos']}")
            elif d["vix_speed"] > 3.5: st.error("⚠️ PÁNICO VIX DETECTADO")
            
            if not mercado_asentado:
                st.warning("⏳ MODO PRE-CHECK (Bloqueo hasta 16:45h)")
                st.info(f"**PRE-ESTRATEGIA:** {'BULL PUT' if bias else 'BEAR CALL'} | **VENDER:** {vender} | **COMPRAR:** {comprar}")
            else:
                st.success(f"🚀 ESTRATEGIA ACTIVA: {'BULL PUT' if bias else 'BEAR CALL'}")
                st.write(f"### VENDER: **{vender}** | COMPRAR: **{comprar}** (Lotes: {lotes}, Spread {ancho})")
                if abs(d["caida_flash"]) > 0.40: st.error("🚨 ALERTA FLASH: EVALUAR CIERRE")

    sleep_timer.sleep(30)
    st.rerun()

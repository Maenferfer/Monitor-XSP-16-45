import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz
import time as sleep_timer

# --- CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="THE ORACLE v9.3 PRO", layout="wide")
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'

# --- 1. FUNCIONES DE APOYO (Página 1 y 2 del PDF) ---
def enviar_telegram(mensaje):
    token = "8730360984:AAGJCvvnQKbZJFnAIQnfnC4bmrq1lCk9MEo"
    chat_id = "7121107501"
    url = f"https://api.telegram.org{token}/sendMessage?chat_id={chat_id}&text={mensaje}"
    try: requests.get(url, timeout=5)
    except: pass

def calcular_streak_dias(df_diario):
    closes = df_diario['Close'].tail(10).values
    if len(closes) < 2: return 0
    streak = 0
    direction = 1 if closes[-1] > closes[-2] else -1
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] - closes[i-1]) * direction > 0: streak += direction
        else: break
    return streak

# --- 2. OBTENCIÓN DE DATOS MAESTROS (Página 2 y 3 del PDF) ---
def obtener_datos_maestros():
    try:
        tickers = {"XSP": "^XSP", "VIX": "^VIX", "VIX9D": "^VIX9D", "TNX": "^TNX", "PCCE": "PCCE", "RSP": "RSP"}
        raw_data = {}
        for k, v in tickers.items():
            t = yf.Ticker(v)
            df = t.history(period="7d", interval="1m")
            if df.empty: df = t.history(period="7d", interval="1d")
            raw_data[k] = df
        
        df_x = raw_data["XSP"]
        actual = float(df_x['Close'].iloc[-1])
        apertura = float(df_x['Open'].iloc[-1])
        prev_close = float(df_x['Close'].iloc[-2])
        
        df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
        atr14 = (df_diario['High'] - df_diario['Low']).tail(14).mean()
        
        # Z-Score y Streak
        std_20 = df_diario['Close'].tail(20).std()
        z_score = (actual - df_diario['Close'].tail(20).mean()) / std_20 if std_20 > 0 else 0
        streak = calcular_streak_dias(df_diario)
        
        # VIX Speed y Caída Flash (Página 3)
        vix_speed = (float(raw_data["VIX"]['Close'].iloc[-1]) / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0
        caida_flash = (actual / (df_x['Close'].iloc[-5]) - 1) * 100 if len(df_x) > 5 else 0

        # Tech Votos (Página 3)
        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d_tk = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d_tk.empty and d_tk['Close'].iloc[-1] > d_tk['Open'].iloc[-1]: votos += 1

        return {
            "actual": actual, "apertura": apertura, "prev": prev_close,
            "vix": float(raw_data["VIX"]['Close'].iloc[-1]), "vix9d": float(raw_data["VIX9D"]['Close'].iloc[-1]),
            "atr14": atr14, "z_score": z_score, "votos_tech": votos, "streak": streak,
            "tnx": float(raw_data["TNX"]['Close'].iloc[-1]), "tnx_prev": float(raw_data["TNX"]['Close'].iloc[-2]),
            "gap_pct": (apertura - prev_close) / prev_close * 100,
            "rsp_bull": float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]),
            "vix_speed": vix_speed, "caida_flash": caida_flash,
            "vol_rel": float(df_x['Volume'].iloc[-1] / df_x['Volume'].tail(30).mean()) if not df_x['Volume'].empty else 1.0
        }
    except: return None

# --- 3. LÓGICA DE TRADING (Página 4 y 5 del PDF) ---
st.title("🏛️ THE ORACLE v9.3 PRO | Institutional Monitor")
cap = st.sidebar.number_input("Capital Cuenta (€)", value=25000)
placeholder = st.empty()

while True:
    d = obtener_datos_maestros()
    if d:
        with placeholder.container():
            # Filtros Críticos (Página 3 y 4)
            vix_panico = d["vix_speed"] > 3.5
            pico_bonos = d["tnx"] > (d["tnx_prev"] * 1.02)
            vix_peligro = d["vix"] > d["vix9d"]
            divergencia_bonos = (d["tnx"] > d["tnx_prev"]) and (d["actual"] > d["apertura"])
            
            # BIAS ESTADÍSTICO v8.0
            bias = (d["actual"] > d["prev"] and d["votos_tech"] >= 2 and d["rsp_bull"] 
                    and not vix_peligro and not divergencia_bonos)
            
            if d["z_score"] > 2.2: bias = False
            if d["z_score"] < -2.2: bias = True

            # CÁLCULO STRIKE v9.2 REALISTA (Ajuste que hicimos)
            m_seg = 0.85 if d["vix"] < 15 else (1.0 if d["vix"] < 22 else 1.3)
            m_atr = 0.85
            dist = max(d["atr14"] * m_atr, d["actual"] * ((d["vix"]/100)/15.87) * m_seg)
            
            vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)
            if vender % 5 == 0: vender = vender - 1 if bias else vender + 1
            
            # GESTIÓN DE LOTES (Página 5)
            lotes_base = int((cap / 25000) * 10)
            if d["vix"] > 35 or pico_bonos or vix_panico: lotes = 0
            else:
                if d["vix"] < 18: lotes = int(lotes_base * 1.5)
                elif d["vix"] < 25: lotes = lotes_base
                else: lotes = max(1, lotes_base // 2)

            # --- DISPLAY PROFESIONAL ---
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("XSP Price", f"{d['actual']:.2f}")
            c2.metric("VIX", f"{d['vix']:.2f}", f"{(d['vix']-d['vix9d']):+.2f}", delta_color="inverse")
            c3.metric("Z-Score", f"{d['z_score']:.2f}")
            c4.metric("ATR 14", f"{d['atr14']:.2f}")
            c5.metric("Streak", f"{d['streak']:+d}d")

            st.divider()
            
            # Panel de Estrategia
            st.subheader(f"🎯 Estrategia: :blue[{'BULL PUT' if bias else 'BEAR CALL'}]")
            r1, r2, r3 = st.columns(3)
            r1.info(f"**VENDER:** {vender}")
            r2.warning(f"**LOTES:** {lotes}")
            ancho = 2 if d["vix"] < 18 else (3 if d["vix"] < 25 else 5)
            r3.success(f"**COMPRAR:** {vender - ancho if bias else vender + ancho} (Spread {ancho})")

            # Alertas de Bloqueo
            if lotes == 0:
                st.error(f"❌ OPERACIÓN BLOQUEADA: {'VIX Speed' if vix_panico else 'Bono 10Y' if pico_bonos else 'VIX Extremo'}")

            st.caption(f"Actualizado: {datetime.now(ZONA_HORARIA).strftime('%H:%M:%S')}")

    sleep_timer.sleep(30)

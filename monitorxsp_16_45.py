import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz
import os
import warnings
import time as sleep_timer
import winsound
import logging

# --- CONFIGURACIÓN DE SEGURIDAD Y SILENCIO ---
warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'

def check_noticias_pro(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS",
"TARIFF", "TRADE WAR", "RETAIL SALES", "EARNINGS"]
    hoy = str(date.today())
    url = f"https://finnhub.io{hoy}&to={hoy}&token={api_key}" # ← URL corregida
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
    """Calcula cuántos días consecutivos lleva el mercado subiendo (+) o bajando (-)."""
    closes = df_diario['Close'].tail(10).values
    if len(closes) < 2:
        return 0
    streak = 0
    direction = 1 if closes[-1] > closes[-2] else -1
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] - closes[i-1]) * direction > 0:
            streak += direction
        else:
            break
    return streak

def obtener_datos_maestros():
    vals = {}
    try:
        tickers = {
            "XSP": "^XSP", "SPY": "SPY", "RSP": "RSP", "VIX": "^VIX",
            "VIX9D": "^VIX9D", "SKEW": "^SKEW", "TNX": "^TNX", "PCCE": "PCCE"
        }
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
        vol_actual = df_x['Volume'].iloc[-1]
        vol_avg = df_x['Volume'].tail(30).mean()
        vol_rel = vol_actual / vol_avg if vol_avg > 0 else 1.0
        # --- NUEVO: ATR(14) para strike dinámico ---
        df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
        if df_diario.empty: df_diario = yf.Ticker("SPY").history(period="30d", interval="1d")
        atr14 = (df_diario['High'] - df_diario['Low']).tail(14).mean() * factor
        # --- NUEVO: Streak de días consecutivos ---
        streak = calcular_streak_dias(df_diario)
        # --- NUEVO: Z-Score del precio (20 velas) ---
        cierre_diario = df_diario['Close'] * factor
        std_20 = cierre_diario.tail(20).std()
        z_score = (cierre_diario.iloc[-1] - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0
        # --- NUEVO: Inside Day ---
        inside_day = (\
            df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and\
            df_diario['Low'].iloc[-1] > df_diario['Low'].iloc[-2]\
        ) if len(df_diario) >= 2 else False
        vals = {\
            "actual": actual, "apertura": apertura, "prev": prev_close,\
            "ma5": df_x['Close'].tail(5).mean() * factor,\
            "rsi_14": calc_rsi(df_x['Close'], 14),\
            "rsi_5m": calc_rsi(df_x['Close'], 5),\
            "cambio_15m": (actual - df_x['Close'].iloc[-15] * factor) if len(df_x) > 15 else 0,\
            "std_dev": df_x['Close'].std() * factor,\
            "vol_rel": vol_rel,\
            "vix": float(raw_data["VIX"]['Close'].iloc[-1]),\
            "vix9d": float(raw_data["VIX9D"]['Close'].iloc[-1]),\
            "skew": float(raw_data["SKEW"]['Close'].iloc[-1]),\
            "tnx": float(raw_data["TNX"]['Close'].iloc[-1]),\
            "tnx_prev": float(raw_data["TNX"]['Close'].iloc[-2]),\
            "pc_ratio": float(raw_data["PCCE"]['Close'].iloc[-1]) if not raw_data["PCCE"].empty else 0.8,\
            "rsp_bull": float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]),\
            # Nuevas métricas\
            "atr14": atr14,\
            "streak": streak,
            "z_score": z_score,
            "inside_day": inside_day,
            "gap_pct": (apertura - prev_close) / prev_close * 100,
            "vix_speed": (float(raw_data["VIX"]['Close'].iloc[-1]) / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "caida_flash": (actual / (df_x['Close'].iloc[-5] * factor) - 1) * 100 if len(df_x) > 5 else 0,
        }
        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d.empty and d['Close'].iloc[-1] > d['Open'].iloc[-1]: votos += 1
        vals["votos_tech"] = votos
    except Exception as e:
        print(f"[ERROR datos]: {e}")
        return None
    return vals

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(" 🏛️  XSP 0DTE Institutional v8.4 (Dynamic Sizing Edition)")
    print("="*65)
    cap = float(input("Capital Cuenta (€): ") or 26000.0)
    lotes = 0 # Inicializar lotes para que el resto del script lo reconozca
    while True:
        noticias = check_noticias_pro(FINNHUB_API_KEY)
        d = obtener_datos_maestros()
        if not d: sleep_timer.sleep(5); continue
        os.system('cls' if os.name == 'nt' else 'clear')
        ahora = datetime.now(ZONA_HORARIA)
        ahora_time = ahora.time()
        # Bloqueo estricto antes de las 16:45 para filtrar ruido de apertura
        mercado_asentado = ahora_time >= time(16, 45)
        # --- LÓGICA DE TIEMPO 20:30 ---
        hora_limite = time(20, 30)
        minutos_al_limite = (datetime.combine(date.today(), hora_limite) - datetime.combine(date.today(), ahora_time)).total_seconds() / 60
        # ================================================================
        # FILTROS ORIGINALES
        # ================================================================
        vix_inv = d["vix"] < d["vix9d"]
        extendido = abs(d["actual"] - d["apertura"]) > (d["std_dev"] * 2.5)
        vela_roja = d["cambio_15m"] < -1.5
        agotamiento = (d["actual"] > d["apertura"]) and (d["vol_rel"] < 0.6) # ← ajustado 0.7→0.6
        # ================================================================
        # NUEVOS FILTROS v7.0
        # ================================================================
        # 1. Régimen de VIX extremo → no operar
        vix_extremo = d["vix"] > 35
        pico_bonos = d["tnx"] > (d["tnx_prev"] * 1.02)
        vix_panico = d["vix_speed"] > 3.5  # Bloqueo si el VIX se acelera >3.5% en 5 min

        # 3. Gap de apertura
        gap_grande_arriba = d["gap_pct"] > 0.5 # Probable reversión → bear call
        gap_grande_abajo = d["gap_pct"] < -0.5 # Probable rebote → bull put
        # 4. Momentum (streaks)
        streak_bajista = d["streak"] <= -3 # 3+ días bajistas → no abrir bull put
        streak_alcista = d["streak"] >= 3 # 3+ días alcistas → no abrir bear call
        # 5. Z-Score: protección contra extremos
        muy_sobrevendido = d["z_score"] < -2.0 # No vender call (riesgo rebote)
        muy_sobrecomprado = d["z_score"] > 2.0 # No vender put (riesgo caída)
        # ================================================================
        # BIAS ESTADÍSTICO v8.0 (OPTIMIZADO 100% HISTÓRICO)
        # ================================================================
        # Regla 1: Dominancia de Volatilidad (Filtro Anti-Crash)
        vix_peligro = d["vix"] > d["vix9d"]
        
        # Regla 2: Divergencia de Bonos (Filtro de Trampa Alcista)
        divergencia_bonos = (d["tnx"] > d["tnx_prev"]) and (d["actual"] > d["apertura"])
        # Cálculo del BIAS con Pesos Estadísticos
        bias = (
            (d["actual"] > d["prev"]) and 
            (d["votos_tech"] >= 2) and 
            d["rsp_bull"] and 
            not vix_peligro and # ← CRÍTICO: No Bull Put si VIX9D < VIX
            not noticias["bloqueo"] and 
            not divergencia_bonos # ← CRÍTICO: No operar si los bonos avisan caída
        )
        # Regla 3: Reversión por Sobrecompra/Venta Extrema (Z-Score)
        if d["z_score"] > 2.2: 
            bias = False # Obligar a Bear Call (Agotamiento)
            print(" 💎 PATRÓN DETECTADO: Agotamiento alcista extremo (Z>2.2)")
        
        if d["z_score"] < -2.2:
            bias = True # Obligar a Bull Put (Rebote estadístico)
            print(" 💎 PATRÓN DETECTADO: Rebote por pánico excesivo (Z<-2.2)")
        # Regla 4: Ajuste de Lotes por Probabilidad
        if d["inside_day"] and not vix_peligro:
            lotes = int(lotes * 1.2) # Aumentar 20% si hay Inside Day (Baja volatilidad real)
            print(" 🚀 OPORTUNIDAD: Inside Day detectado. Aumentando tamaño.")
        # ================================================================
        # CÁLCULO DE STRIKE (mejorado con ATR)
        # ================================================================
        # v7.0 usa ATR(14) en lugar de sigma VIX pura
        # Si el mercado está asentado (16:45+), ajustamos para capturar mejor prima
        multiplicador_atr = 0.95 if ahora_time >= time(16, 45) else 1.0
        dist_atr = d["atr14"] * multiplicador_atr
        dist_sigma = d["actual"] * ((d["vix"] / 100) / (252**0.5)) * 1.3
        dist = max(dist_atr, dist_sigma) # Usar la más conservadora
        vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)
        if vender % 5 == 0: vender = vender - 1 if bias else vender + 1

        # --- GESTIÓN DINÁMICA DE LOTES v8.3 (POSICIÓN CORREGIDA) ---
        distancia_seguridad = abs(d["actual"] - vender)
        lotes_base = int((cap / 25000) * 10) # Recalcula lotes base según capital actual
        
        if d["vix"] > 35 or pico_bonos or vix_panico:
            lotes = 0
            motivo = "VIX EXTREMO" if d["vix"] > 35 else ("SALTO BONOS" if pico_bonos else "PÁNICO VIX")
        else:
            # Cálculo base por VIX
            if d["vix"] < 18:
                lotes = int(lotes_base * 1.5) # Escenario como ayer: 15 lotes
            elif d["vix"] < 25:
                lotes = lotes_base            # Escenario normal: 10 lotes
            else:
                lotes = max(1, lotes_base // 2) # Escenario tenso: 5 lotes

            # Bonus por Distancia (Si el strike está lejos y el VIX es bajo)
            if distancia_seguridad > 5 and d["vix"] < 20:
                lotes = max(lotes, 15)

        # --- LÓGICA DE SPREAD DINÁMICO v8.4 ---
        if d["vix"] < 18:
            ancho = 2  # Mercado tranquilo: Spread estrecho para exprimir prima
        elif d["vix"] < 25:
            ancho = 3  # Mercado normal: Un poco más de aire
        else:
            ancho = 5  # Mercado tenso: Spread ancho para evitar ser sacado por volatilidad

        comprar = vender - ancho if bias else vender + ancho

        # ================================================================
        # ALERTAS SONORAS
        # ================================================================
        if ahora_time >= hora_limite: winsound.Beep(1500, 1000)
        if abs(d["actual"] - vender) < 0.8: winsound.Beep(2000, 800)
        if vix_extremo: winsound.Beep(800, 1500) # ← alerta VIX extremo
        # ================================================================
        # DISPLAY
        # ================================================================
        print(f" 🏛️  THE ORACLE v8.4 | {ahora.strftime('%H:%M:%S')} | CAPITAL: {cap}€")
        print(f"XSP: {d['actual']:.2f} | MA5: {d['ma5']:.1f} | RSI 14: {d['rsi_14']:.1f} | Z-Score: {d['z_score']:.2f}")
        print(f"VOL: {d['vol_rel']:.2f}x {' AGOTAMIENTO' if agotamiento else ' OK'} | VELA 15m: {d['cambio_15m']:.2f} | ATR14: {d['atr14']:.2f}")
        print("-" * 65)
        print(f"VIX: {d['vix']:.2f} {' EXTREMO' if vix_extremo else ''} | VIX9D: {d['vix9d']:.2f} | SKEW: {d['skew']:.2f} | P/C: {d['pc_ratio']:.2f}")
        print(f"TECH: {d['votos_tech']}/3 | BREADTH (RSP): {'' if d['rsp_bull'] else ''} | BONO 10Y: {d['tnx']:.2f}")
        print(f"GAP: {d['gap_pct']:+.2f}% | STREAK: {d['streak']:+d}d | INSIDE DAY: {'✅' if d['inside_day'] else '❌'}")
        print("-" * 65)
        if noticias["bloqueo"]:
            print(f" 🚫 BLOQUEO NOTICIAS: {noticias['eventos']}")
        elif lotes == 0:
            print(" 🚫 Lotes = 0. Condiciones insuficientes para operar.")
        else:
            if minutos_al_limite > 0 and minutos_al_limite <= 60:
                print(f" ⏳ CIERRE SEGURIDAD: En {int(minutos_al_limite)} min (Objetivo 20:30h)")
            elif ahora_time >= hora_limite:
                print(" ❌ HORA DE CIERRE ALCANZADA (20:30). LIQUIDAR POSICIÓN.")
            if not mercado_asentado:
                print("\n⏳ ESTADO: MODO PRE-CHECK (BLOQUEO HASTA 16:45h)")
                # Cálculo de compra proyectada para el Pre-Check
                if d["vix"] < 18: ancho_pre = 2
                elif d["vix"] < 25: ancho_pre = 3
                else: ancho_pre = 5
                
                comprar_pre = vender - ancho_pre if bias else vender + ancho_pre
                
                print(f"PRE-ESTRATEGIA: {'BULL PUT' if bias else 'BEAR CALL'}")
                print(f"VENDER ESTIMADO: {vender} | COMPRAR: {comprar_pre} (Spread {ancho_pre})")
                print(f"LOTES PROYECTADOS: {lotes}")
                print("-" * 35)
                print("Lógica: Filtrando ruido. No ejecutes hasta el asentamiento.")
            else:
                # Válvula de Escape: Si cae más de un 0.40% en 5 min, hay pánico real
                alerta_flash = d["caida_flash"] < -0.40 if bias else d["caida_flash"] > 0.40
                
                if alerta_flash:
                    winsound.Beep(2500, 2000) # Descomentar para activar sonido agudo de emergencia
                    msg = "🚨 ALERTA FLASH: Movimiento violento en XSP. ¡EVALUAR CIERRE INMEDIATO!"
                    print(msg)
                
                print(f"\nESTRATEGIA: {'BULL PUT' if bias else 'BEAR CALL'}")
                print(f"VENDER STRIKE: {vender} | COMPRAR: {comprar} (Spread {ancho})")
                print(f"🛑 STOP LOSS (Manual): {vender} | 🎯 TP 65%: @ 35% del valor")

        print("=" * 65)
        for i in range(30, 0, -1):
            print(f"Actualizando pulso en: {i} seg... ", end="\r", flush=True)
            sleep_timer.sleep(1)
if __name__ == "__main__":
    main()

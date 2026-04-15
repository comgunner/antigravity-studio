#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coin_summary.py — Multi-asset Technical Summary (Crypto + Forex/Indices/Metals).
Source: Binance Futures (Crypto) and Yahoo Finance (Traditional Assets).
Calculates Price, EMA 3, 9, 21, 50, and 200.
"""

import json
import urllib.request
import urllib.parse
import datetime as dt
import subprocess
import sys
from typing import List, Dict, Any, Optional

# YAHOO MAPPING (Top 10 & Stable Tickers)
YAHOO_MAP = {
    # Metals
    "XAU": "GC=F",      # Gold Futures (Stable replacement for XAUUSD=X)
    "GOLD": "GC=F",
    "XAG": "SI=F",      # Silver Futures
    "SILVER": "SI=F",
    
    # Forex
    "EUR": "EURUSD=X",
    "EURUSD": "EURUSD=X",
    "GBP": "GBPUSD=X",
    "GBPUSD": "GBPUSD=X",
    "JPY": "JPY=X",
    "MXN": "MXN=X",
    "USDMXN": "MXN=X",
    
    # Commodities
    "CL": "CL=F",      # Crude Oil WTI
    "OIL": "CL=F",
    
    # Indices
    "GSPC": "^GSPC",   # S&P 500
    "SP500": "^GSPC",
    "IXIC": "^IXIC",   # Nasdaq Composite
    "NASDAQ": "^IXIC",
    "DJI": "^DJI",     # Dow Jones
    "DXY": "DX-Y.NYB",  # Dollar Index
    
    # ETFs
    "SPY": "SPY",
    "SQQQ": "SQQQ",
}

def get_yfinance_data(symbol: str, interval: str) -> List[float]:
    """Fetch data from Yahoo Finance and return closes."""
    import yfinance as yf
    import pandas as pd
    
    ticker = YAHOO_MAP.get(symbol.upper(), symbol.upper())
    
    # Map intervals and periods
    yf_interval = interval.lower()
    period = "60d" # Sufficient for EMA 200 in most cases
    
    if yf_interval == "1d": period = "2y"
    elif yf_interval == "4h": yf_interval = "1h" # Synthetic 4h requires resampling or 1h base
    
    df = yf.download(tickers=ticker, period=period, interval=yf_interval, progress=False)
    
    if df.empty:
        raise ValueError(f"No data found for Yahoo ticker: {ticker}")
        
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
        
    # Synthetic 4h logic if interval is 4h
    if interval.lower() == "4h":
        df = df.resample('4h').agg({'Close': 'last'}).dropna()

    return df['Close'].tolist()

def get_binance_data(symbol: str, interval: str) -> List[float]:
    """Fetch data from Binance Futures FAPI."""
    url = f"https://fapi.binance.com/fapi/v1/klines"
    symbol_formatted = symbol.strip().upper().replace("_", "")
    if not symbol_formatted.endswith("USDT"):
        symbol_formatted += "USDT"
        
    params = {"symbol": symbol_formatted, "interval": interval, "limit": 450}
    full_url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full_url, headers={"User-Agent": "antigravity-studio/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        klines = json.loads(resp.read().decode("utf-8"))
        return [float(k[4]) for k in klines]

def ema(data: List[float], window: int) -> float:
    """Calculate EMA using SMA as seed."""
    if len(data) < window: return data[-1]
    alpha = 2 / (window + 1)
    ema_val = sum(data[:window]) / window
    for val in data[window:]:
        ema_val = (val * alpha) + (ema_val * (1 - alpha))
    return ema_val

def get_gemini_analysis(summary_data: Dict[str, Any]) -> str:
    """Invoke antigravity_cli.py to analyze technical data using Gemini."""
    prompt = (
        f"Analyze this {summary_data['symbol']} {summary_data['interval']} data (Source: {summary_data['source']}): "
        f"Price ${summary_data['price']}, Change {summary_data['change_pct']}%, "
        f"EMA3 {summary_data['ema_3']}, EMA9 {summary_data['ema_9']}, "
        f"EMA21 {summary_data['ema_21']}, EMA50 {summary_data['ema_50']}, EMA200 {summary_data['ema_200']}. "
        "Provide a very brief (2-3 lines) technical sentiment (bullish/bearish/neutral) "
        "and key levels to watch. No financial advice. Response MUST be in English."
    )
    
    try:
        result = subprocess.run(
            ["python3", "antigravity_cli.py", "chat", prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"AI Analysis Error: {e}"

def run_summary(symbol: str, interval: str):
    sym_upper = symbol.upper().strip()
    print(f"--- Generating {sym_upper} {interval} Summary with Gemini ---")
    
    try:
        # Source Selection: Specific Yahoo tickers vs Crypto (Binance)
        if sym_upper in YAHOO_MAP or any(x in sym_upper for x in ["=X", "=F", "^", ".NYB"]):
            source = "Yahoo Finance"
            closes = get_yfinance_data(sym_upper, interval)
        else:
            source = "Binance Futures"
            closes = get_binance_data(sym_upper, interval)
        
        curr_price = closes[-1]
        prev_price = closes[-2]
        change_pct = ((curr_price - prev_price) / prev_price) * 100

        summary = {
            "symbol": sym_upper,
            "interval": interval,
            "source": source,
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "price": round(curr_price, 4 if curr_price < 1 else 2),
            "change_pct": round(change_pct, 2),
            "ema_3": round(ema(closes, 3), 4 if curr_price < 1 else 2),
            "ema_9": round(ema(closes, 9), 4 if curr_price < 1 else 2),
            "ema_21": round(ema(closes, 21), 4 if curr_price < 1 else 2),
            "ema_50": round(ema(closes, 50), 4 if curr_price < 1 else 2),
            "ema_200": round(ema(closes, 200), 4 if curr_price < 1 else 2),
        }
        
        print(f"Consulting Gemini AI (Source: {source}) for {sym_upper}...")
        summary["ai_analysis"] = get_gemini_analysis(summary)

        # Terminal Output
        print(f"\nCURRENT STATUS: {summary['symbol']} ({interval}) | SOURCE: {source}")
        print(f"Price: ${summary['price']:,} ({summary['change_pct']}%)")
        print(f"EMA 3:   {summary['ema_3']} | EMA 9:   {summary['ema_9']}")
        print(f"EMA 21:  {summary['ema_21']} | EMA 50:  {summary['ema_50']} | EMA 200: {summary['ema_200']}")
        print(f"\n--- AI TECHNICAL VIEW (GEMINI) ---")
        print(summary["ai_analysis"])
        print(f"\nUpdated at: {summary['timestamp']}")

        # Save to JSON
        filename = f"summary_{sym_upper.lower()}_{interval}.json"
        with open(filename, "w") as f:
            json.dump(summary, f, indent=4)
        print(f"\n[✓] Data saved to {filename}")

    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    tf = sys.argv[2] if len(sys.argv) > 2 else "4h"
    run_summary(sym, tf)

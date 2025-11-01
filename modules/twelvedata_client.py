import requests
import pandas as pd
import time

BASE_URL = "https://api.twelvedata.com"

def fetch_forex_klines(symbol="EUR/USD", interval="1min", outputsize=300, api_key=None, retries=3):
    url = f"{BASE_URL}/time_series"
    params = {"symbol": symbol, "interval": interval, "outputsize": outputsize, "apikey": api_key}

    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=25)
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")
            js = r.json()
            if not js or "values" not in js:
                msg = js.get("message") if isinstance(js, dict) else "no-data"
                print(f"[WARN] {symbol} returned invalid data: {msg}")
                return pd.DataFrame()

            df = pd.DataFrame(js["values"])
            df = df.rename(columns={"datetime":"close_time"})
            df["close_time"] = pd.to_datetime(df["close_time"])
            for col in ["open","high","low","close","volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            df = df.sort_values("close_time").reset_index(drop=True)
            return df
        except Exception as e:
            print(f"[WARN] retry {i+1}/{retries} for {symbol}: {e}")
            time.sleep(2)

    print(f"[ERROR] {symbol} failed after {retries} retries")
    return pd.DataFrame()

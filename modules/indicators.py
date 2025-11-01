import pandas as pd
import numpy as np

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    s = pd.to_numeric(series, errors='coerce')
    delta = s.diff()
    up = (delta.clip(lower=0)).ewm(alpha=1/length, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/length, adjust=False).mean()
    rs = up / (down + 1e-12)
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    h = pd.to_numeric(df['high'], errors='coerce')
    l = pd.to_numeric(df['low'], errors='coerce')
    c = pd.to_numeric(df['close'], errors='coerce')
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, adjust=False).mean()

def ema(series: pd.Series, length: int) -> pd.Series:
    s = pd.to_numeric(series, errors='coerce')
    return s.ewm(span=length, adjust=False).mean()

def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    h = pd.to_numeric(df['high'], errors='coerce')
    l = pd.to_numeric(df['low'], errors='coerce')
    c = pd.to_numeric(df['close'], errors='coerce')
    up_move = h.diff()
    down_move = -l.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move.clip(lower=0)
    tr = pd.concat([(h - l).abs(), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr_rma = tr.ewm(alpha=1/length, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/length, adjust=False).mean() / (atr_rma + 1e-12))
    minus_di = 100 * (minus_dm.ewm(alpha=1/length, adjust=False).mean() / (atr_rma + 1e-12))
    dx = (100 * (plus_di - minus_di).abs() / ((plus_di + minus_di) + 1e-12)).fillna(0)
    adx_val = dx.ewm(alpha=1/length, adjust=False).mean()
    return adx_val.clip(lower=0, upper=100)

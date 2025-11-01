import pandas as pd
import numpy as np

def detect_swings(df: pd.DataFrame, sensitivity: int = 3) -> pd.DataFrame:
    d = df.copy()
    d['swing'] = 0
    n = len(d)
    if n < 2*sensitivity+1:
        return d
    highs = d['high'].values
    lows = d['low'].values
    for i in range(sensitivity, n - sensitivity):
        if highs[i] == max(highs[i-sensitivity:i+sensitivity+1]):
            d.iat[i, d.columns.get_loc('swing')] = 1
        elif lows[i] == min(lows[i-sensitivity:i+sensitivity+1]):
            d.iat[i, d.columns.get_loc('swing')] = -1
    return d

def _pivots(d: pd.DataFrame):
    piv = []
    for i, s in enumerate(d['swing'].values):
        if s == 1:
            piv.append((i, 'H', float(d['high'].iloc[i])))
        elif s == -1:
            piv.append((i, 'L', float(d['low'].iloc[i])))
    cleaned = []
    for p in piv:
        if not cleaned:
            cleaned.append(p); continue
        if cleaned[-1][1] == p[1]:
            if p[1] == 'H':
                if p[2] >= cleaned[-1][2]:
                    cleaned[-1] = p
            else:
                if p[2] <= cleaned[-1][2]:
                    cleaned[-1] = p
        else:
            cleaned.append(p)
    return cleaned

def current_wave_label(df: pd.DataFrame, sensitivity: int = 3):
    if df is None or df.empty:
        return None, None
    d = detect_swings(df, sensitivity=sensitivity)
    piv = _pivots(d)
    if len(piv) < 3:
        return None, None
    highs = [p for p in piv if p[1]=='H']
    lows = [p for p in piv if p[1]=='L']
    up = 0
    for i in range(1, len(highs)):
        up += 1 if highs[i][2] > highs[i-1][2] else -1
    for i in range(1, len(lows)):
        up += 1 if lows[i][2] > lows[i-1][2] else -1
    leg_count = len(piv)
    if up >= 0:
        label = min(5, max(1, leg_count))
        return label, 'Impulse'
    else:
        if leg_count <= 2: return 'A', 'Correction'
        elif leg_count in (3,4): return 'B', 'Correction'
        else: return 'C', 'Correction'

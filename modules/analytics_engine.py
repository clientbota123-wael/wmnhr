import pandas as pd
import numpy as np
from modules.indicators import rsi as rsi_fn, atr as atr_fn

def _base_dir_conf_last5(df):
    if df is None or len(df) < 5:
        return None, None
    d = df.tail(5).copy()
    ups = (d['close'] > d['open']).sum()
    downs = (d['close'] < d['open']).sum()
    if ups == downs:
        base_dir = 1 if d['close'].iloc[-1] > d['open'].iloc[-1] else 0
    else:
        base_dir = 1 if ups > downs else 0
    last_body = float(abs(d['close'].iloc[-1] - d['open'].iloc[-1]))
    avg_body = float(abs(d['close'] - d['open']).mean()) or 1e-6
    base_conf = max(0.0, min(1.0, last_body / avg_body))
    return int(base_dir), float(base_conf)

def _volume_strength(df, window=20):
    v = pd.to_numeric(df['volume'], errors='coerce')
    if len(v) < 5:
        return 0.0
    m = v.rolling(window, min_periods=max(5, window//2)).mean()
    s = v.rolling(window, min_periods=max(5, window//2)).std()
    m_last = float(m.iloc[-1]) if pd.notna(m.iloc[-1]) else 0.0
    s_last = float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else 1e-6
    z = float((v.iloc[-1] - m_last) / (s_last if s_last != 0 else 1e-6))
    z_norm = (max(-3.0, min(3.0, z)) + 3.0) / 6.0
    return max(0.0, min(1.0, z_norm))

def rsi_filter_factor(df, rsi_len=14):
    try:
        rs = rsi_fn(df['close'], rsi_len)
        last = float(rs.iloc[-1])
        if last >= 70 or last <= 30:
            return 0.85, last
        elif 60 <= last < 70 or 30 < last <= 40:
            return 0.93, last
        else:
            return 1.0, last
    except Exception:
        return 1.0, None

def atr_target_pct(df, atr_len=14, mult=0.5):
    try:
        a = atr_fn(df, atr_len)
        atr_last = float(a.iloc[-1])
        price = float(df['close'].iloc[-1])
        tp_pct = (atr_last / (price + 1e-9)) * (mult * 100.0)
        return max(0.01, tp_pct), atr_last
    except Exception:
        return None, None

def buy_sell_pressure(df, lookback=5):
    if df is None or len(df) < lookback+1:
        return 0.0
    d = df.tail(lookback+1).copy()
    price_dir = np.sign(d['close'].diff().fillna(0)).sum()
    vol_change = (d['volume'].pct_change().fillna(0)).sum()
    if price_dir > 0 and vol_change > 0:
        return +1.0
    elif price_dir < 0 and vol_change > 0:
        return -1.0
    return 0.0

def direction_conf_quant(df, book=None, depth_liq_bias=None, pressure=0.0,
                         rsi_len=14, atr_len=14, atr_mult=0.5):
    base_dir, base_conf = _base_dir_conf_last5(df)
    if base_dir is None:
        return None, None, {}
    vol_str = _volume_strength(df)
    base_signed = (+base_conf) if base_dir == 1 else (-base_conf)
    vol_signed = (vol_str * 0.6 + 0.4*base_conf) * (+1 if base_dir == 1 else -1)
    liq_signed = (depth_liq_bias or 0.0)
    final_score = (0.60*base_signed) + (0.20*vol_signed) + (0.20*(0.5*liq_signed + 0.5*pressure))
    final_score = max(-1.0, min(1.0, final_score))
    dir_out = 1 if final_score >= 0 else 0
    conf_out = abs(final_score)
    rsi_factor, rsi_last = rsi_filter_factor(df, rsi_len=rsi_len)
    conf_out = max(0.0, min(1.0, conf_out * rsi_factor))
    tp_pct, atr_last = atr_target_pct(df, atr_len=atr_len, mult=atr_mult)
    extras = {'rsi': rsi_last, 'atr': atr_last, 'tp_pct': tp_pct}
    return int(dir_out), float(conf_out), extras

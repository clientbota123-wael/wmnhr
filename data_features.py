import pandas as pd
import numpy as np
from modules.indicators import rsi as rsi_fn, atr as atr_fn, ema as ema_fn, adx as adx_fn

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

def _micro_from_orderbook(bid, ask, bid_qty, ask_qty, depth_liq_bias=None):
    try:
        bid = float(bid); ask = float(ask)
        bq = float(bid_qty or 0.0); aq = float(ask_qty or 0.0)
    except Exception:
        return None, None, None, None

    if bid <= 0 or ask <= 0 or ask <= bid:
        return None, None, None, None

    mid = 0.5 * (bid + ask)
    rel_spread = (ask - bid) / (mid + 1e-9)
    imbalance = (bq - aq) / ((bq + aq) + 1e-9)

    if depth_liq_bias is not None:
        imbalance = 0.5*imbalance + 0.5*depth_liq_bias

    micro_dir = 1 if imbalance > 0 else 0
    tightness = 1.0 - max(0.0, min(1.0, rel_spread / 0.001))
    micro_conf = (abs(imbalance) * 0.7) + (tightness * 0.3)
    micro_conf = max(0.0, min(1.0, micro_conf))
    return int(micro_dir), float(micro_conf), float(rel_spread), float(imbalance)

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

def detect_trend_phase(df, adx_len=14, volume_boom_mult=1.3):
    if df is None or df.empty or len(df) < adx_len + 5:
        return "Neutral", "gray", 0.0

    adx_series = adx_fn(df, adx_len)
    adx_now = float(adx_series.iloc[-1])
    adx_prev = float(adx_series.iloc[-2]) if len(adx_series) > 2 else adx_now
    from modules.indicators import rsi as _rsi, ema as _ema
    rsi_now = float(_rsi(df['close'], 14).iloc[-1])
    v_now = float(df['volume'].iloc[-1])
    v_avg = float(df['volume'].rolling(20).mean().iloc[-1] or 0.0)

    ema20 = float(_ema(df['close'], 20).iloc[-1])
    ema50 = float(_ema(df['close'], 50).iloc[-1])
    ema100 = float(_ema(df['close'], 100).iloc[-1])

    if adx_prev < 20 and adx_now > 20 and (v_avg > 0 and v_now > volume_boom_mult * v_avg):
        return "Start", "yellow", min(1.0, (adx_now/50.0))

    if (ema20 > ema50 > ema100 and 25 < adx_now <= 45 and 55 <= rsi_now <= 70) or        (ema20 < ema50 < ema100 and 25 < adx_now <= 45 and 30 <= rsi_now <= 45):
        return "In Progress", "green", min(1.0, (adx_now/50.0))

    if adx_now < adx_prev and (rsi_now > 70 or rsi_now < 30):
        return "End", "red", min(1.0, (adx_now/50.0))

    return "Neutral", "gray", min(1.0, (adx_now/50.0))

def buy_sell_pressure(df, lookback=5):
    if df is None or len(df) < lookback+1:
        return 0.0
    d = df.tail(lookback+1).copy()
    price_dir = np.sign(d['close'].diff().fillna(0)).sum()
    vol_change = (d['volume'].pct_change().fillna(0)).sum()
    press = 0.0
    if price_dir > 0 and vol_change > 0:
        press = +1.0
    elif price_dir < 0 and vol_change > 0:
        press = -1.0
    elif abs(price_dir) <= 1:
        press = 0.0
    return press

def direction_conf_quant(df, book=None, rsi_len=14, atr_len=14, atr_mult=0.5,
                         depth_liq_bias=None, pressure=0.0):
    base_dir, base_conf = _base_dir_conf_last5(df)
    if base_dir is None:
        return None, None, {}

    vol_str = _volume_strength(df)

    micro_dir, micro_conf, rel_spread, imbalance = (None, None, None, None)
    if book:
        micro_dir, micro_conf, rel_spread, imbalance = _micro_from_orderbook(
            book.get('bid'), book.get('ask'), book.get('bid_qty'), book.get('ask_qty'),
            depth_liq_bias=depth_liq_bias
        )

    base_signed = (+base_conf) if base_dir == 1 else (-base_conf)
    micro_signed = 0.0
    if micro_dir is not None and micro_conf is not None:
        micro_signed = (+micro_conf) if micro_dir == 1 else (-micro_conf)
    vol_signed = (vol_str * 0.6 + 0.4*base_conf) * (+1 if base_dir == 1 else -1)

    liq_signed = (depth_liq_bias or 0.0)
    press_signed = pressure

    final_score = (0.50 * base_signed) + (0.15 * micro_signed) + (0.20 * vol_signed) + (0.15 * (0.5*liq_signed + 0.5*press_signed))
    final_score = max(-1.0, min(1.0, final_score))

    dir_out = 1 if final_score >= 0 else 0
    conf_out = abs(final_score)

    rsi_factor, rsi_last = rsi_filter_factor(df, rsi_len=rsi_len)
    conf_out = max(0.0, min(1.0, conf_out * rsi_factor))

    tp_pct, atr_last = atr_target_pct(df, atr_len=atr_len, mult=atr_mult)
    phase, phase_color, phase_strength = detect_trend_phase(df)

    extras = {
        'spread': rel_spread,
        'imbalance': imbalance,
        'rsi': rsi_last,
        'atr': atr_last,
        'tp_pct': tp_pct,
        'trend_phase': phase,
        'trend_color': phase_color,
        'trend_strength': phase_strength,
        'liq_bias': depth_liq_bias,
        'pressure': press_signed
    }

    return int(dir_out), float(conf_out), extras

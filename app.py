import os, time, threading, datetime
from collections import defaultdict

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_socketio import SocketIO
from binance.spot import Spot

from data_features import direction_conf_quant, buy_sell_pressure
from modules.elliott_wave import current_wave_label
from modules.temporal_predictor import ReversalTimer
from modules.indicators import rsi as rsi_fn, atr as atr_fn

load_dotenv()

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "3"))
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "10"))
LOOKBACK_1M = int(os.getenv("LOOKBACK_1M", "900"))
TOP_N = int(os.getenv("TOP_N", "15"))
RSI_LEN = int(os.getenv("RSI_LEN", "14"))
ATR_LEN = int(os.getenv("ATR_LEN", "14"))
ATR_TP_MULT = float(os.getenv("ATR_TP_MULT", "0.5"))
ML_LOOKBACK = int(os.getenv("ML_LOOKBACK", "300"))
ML_MIN_SAMPLES = int(os.getenv("ML_MIN_SAMPLES", "120"))
REC_CONF_THRESHOLD = float(os.getenv("REC_CONF_THRESHOLD", "0.65"))
REC_MIN_MINUTES = int(os.getenv("REC_MIN_MINUTES", "3"))
REC_MAX_MINUTES = int(os.getenv("REC_MAX_MINUTES", "20"))
ADX_LEN = int(os.getenv("ADX_LEN", "14"))
VOLUME_BOOM_MULT = float(os.getenv("VOLUME_BOOM_MULT", "1.3"))
DEPTH_LIMIT = int(os.getenv("DEPTH_LIMIT", "20"))
REV_MAX_FWD = int(os.getenv("REV_MAX_FWD", "30"))

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

client = Spot(timeout=TIMEOUT_SECONDS)

symbols = []
symbol_display_name = {}
timer_cache = defaultdict(lambda: ReversalTimer(max_forward=REV_MAX_FWD, min_rows=ML_MIN_SAMPLES))

ASSET_NAMES = {
    "BTC":"Bitcoin", "ETH":"Ethereum", "BNB":"BNB", "SOL":"Solana", "XRP":"XRP",
    "ADA":"Cardano", "DOGE":"Dogecoin", "TRX":"TRON", "TON":"Toncoin", "DOT":"Polkadot",
    "MATIC":"Polygon", "LTC":"Litecoin", "SHIB":"Shiba Inu", "ZEC":"Zcash",
    "TAO":"Bittensor", "FDUSD":"First Digital USD", "USDE":"Ethena USDe",
    "USDC":"USD Coin", "USDT":"Tether", "BCH":"Bitcoin Cash", "UNI":"Uniswap",
    "ATOM":"Cosmos", "LINK":"Chainlink", "APT":"Aptos"
}

def safe_fetch(func, *args, retries=3, delay=0.5, **kwargs):
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if i == retries-1:
                print(f"[WARN] {func.__name__} failed after {retries} tries: {e}")
                return None
            time.sleep(delay)

def build_name_cache():
    global symbol_display_name
    info = safe_fetch(client.exchange_info)
    if not info or 'symbols' not in info:
        print('[WARN] exchange_info not available, using basic labels only')
        symbol_display_name = {}
        return
    out = {}
    for s in info.get('symbols', []):
        try:
            sym = s.get('symbol','')
            base = s.get('baseAsset','')
            quote = s.get('quoteAsset','')
            if not sym or not base or not quote:
                continue
            base_name = ASSET_NAMES.get(base, base)
            label = f"{base_name} ({base}/{quote})"
            out[sym] = label
        except Exception:
            continue
    symbol_display_name = out
    print(f"[INFO] name cache size: {len(symbol_display_name)}")

def load_top_symbols():
    global symbols
    data = safe_fetch(client.ticker_24hr)
    if not data:
        print('[WARN] Could not fetch 24hr tickers; keeping old list')
        return
    def valid(sym):
        s = sym.upper()
        if not s.endswith('USDT'): return False
        bad = ('UPUSDT','DOWNUSDT','BULLUSDT','BEARUSDT')
        return s not in bad
    rows = [r for r in data if isinstance(r, dict) and valid(r.get('symbol',''))]
    for r in rows:
        try:
            r['_qvol'] = float(r.get('quoteVolume','0') or 0.0)
        except Exception:
            r['_qvol'] = 0.0
    rows.sort(key=lambda x: x['_qvol'], reverse=True)
    symbols = [r['symbol'] for r in rows[:TOP_N]]
    print(f"[INFO] TOP{TOP_N}: {symbols}")

def fetch_klines(symbol, interval, limit):
    kl = safe_fetch(client.klines, symbol, interval=interval, limit=limit)
    if not kl: return pd.DataFrame()
    try:
        df = pd.DataFrame([{
            'open_time': pd.to_datetime(r[0], unit='ms', utc=True),
            'open': float(r[1]), 'high': float(r[2]), 'low': float(r[3]),
            'close': float(r[4]), 'volume': float(r[5]),
            'close_time': pd.to_datetime(r[6], unit='ms', utc=True),
        } for r in kl])
        df['rsi'] = rsi_fn(df['close'], RSI_LEN)
        from modules.indicators import atr as _atr
        df['atr'] = _atr(df, ATR_LEN)
        return df
    except Exception as e:
        print(f"[WARN] parse klines failed for {symbol} {interval}: {e}")
        return pd.DataFrame()

def build_10m_from_1m(df_1m):
    if df_1m is None or df_1m.empty: return pd.DataFrame()
    d = df_1m.copy().set_index('close_time')
    o = d['open'].resample('10min').first()
    h = d['high'].resample('10min').max()
    l = d['low'].resample('10min').min()
    c = d['close'].resample('10min').last()
    v = d['volume'].resample('10min').sum()
    out = pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
    out = out.dropna().reset_index().rename(columns={'close_time':'close_time'})
    out['rsi'] = rsi_fn(out['close'], RSI_LEN)
    out['atr'] = atr_fn(out, ATR_LEN)
    return out.tail(120)

def fetch_book(symbol):
    bt = safe_fetch(client.book_ticker, symbol)
    if not bt: return None
    try:
        return {'bid': float(bt.get('bidPrice', 0.0) or 0.0),
                'ask': float(bt.get('askPrice', 0.0) or 0.0),
                'bid_qty': float(bt.get('bidQty', 0.0) or 0.0),
                'ask_qty': float(bt.get('askQty', 0.0) or 0.0)}
    except Exception:
        return None

def fetch_depth(symbol, limit=20):
    dp = safe_fetch(client.depth, symbol, limit=limit)
    if not dp: return None
    try:
        bids = sum(float(x[1]) for x in dp.get('bids', [])[:limit])
        asks = sum(float(x[1]) for x in dp.get('asks', [])[:limit])
        if bids + asks <= 0: return {'liq_bias': 0.0}
        liq_bias = (bids - asks) / (bids + asks)
        return {'liq_bias': float(liq_bias), 'bids_vol': float(bids), 'asks_vol': float(asks)}
    except Exception:
        return {'liq_bias': 0.0}

def apply_wave_to_conf(conf, wave, phase):
    if wave in (1,3,5):
        return min(1.0, conf * 1.10), "صاعد"
    if wave in ('A','B','C'):
        return max(0.0, conf * 0.90), "هابط"
    return conf, "غير محدد"

def compute_for_symbol(sym):
    df1 = fetch_klines(sym, '1m', LOOKBACK_1M)
    df5 = fetch_klines(sym, '5m', max(LOOKBACK_1M//5, 200))
    if df1 is None or df1.empty or df5 is None or df5.empty:
        return None

    df10 = build_10m_from_1m(df1)

    book = fetch_book(sym)
    depth = fetch_depth(sym, limit=DEPTH_LIMIT)
    liq_bias = (depth or {}).get('liq_bias', 0.0)

    pressure = buy_sell_pressure(df1, lookback=5)

    out = {}
    rel_spread = None
    imbalance = None
    quote_vol = None
    try:
        quote_vol = float(df1['close'].iloc[-1]) * float(df1['volume'].iloc[-1])
    except Exception:
        quote_vol = None

    pred_minutes = None
    try:
        timer = timer_cache[sym]
        pred_minutes = timer.fit_predict_minutes(df1.tail(ML_LOOKBACK).copy())
    except Exception:
        pred_minutes = None

    for tf, df in [('1m', df1), ('5m', df5), ('10m', df10)]:
        res = direction_conf_quant(df, book=book, rsi_len=RSI_LEN, atr_len=ATR_LEN, atr_mult=ATR_TP_MULT,
                                   depth_liq_bias=liq_bias, pressure=pressure)
        if not res: 
            continue
        dirc, conf, extras = res
        if dirc is None or conf is None or df is None or df.empty:
            continue

        wave, phase = current_wave_label(df[['open','high','low','close','volume','close_time']].copy(), sensitivity=3)
        conf_adj, wave_trend = apply_wave_to_conf(conf, wave, phase)

        if extras:
            rel_spread = extras.get('spread', rel_spread)
            imbalance = extras.get('imbalance', imbalance)

        out[tf] = {
            'dir': int(dirc),
            'conf': float(conf_adj),
            'price': float(df['close'].iloc[-1]),
            'time': df['close_time'].iloc[-1].isoformat(),
            'wave': wave,
            'phase': phase,
            'wave_trend': wave_trend,
            'rsi': extras.get('rsi') if extras else None,
            'atr': extras.get('atr') if extras else None,
            'tp_pct': extras.get('tp_pct') if extras else None,
            'trend_phase': extras.get('trend_phase') if extras else None,
            'trend_color': extras.get('trend_color') if extras else 'gray',
            'trend_strength': extras.get('trend_strength') if extras else 0.0
        }

    extras_out = {
        'spread_pct': (rel_spread * 100.0) if rel_spread is not None else None,
        'imbalance': imbalance,
        'quote_volume_1m': quote_vol,
        'liq_bias_pct': (liq_bias * 100.0) if liq_bias is not None else None,
        'pressure': pressure,
        'pred_minutes': float(pred_minutes) if pred_minutes is not None else None
    }
    return out if out else None, extras_out

def rec_from_payload(tfs: dict, threshold: float=0.65, min_minutes: int=3, max_minutes: int=20, pred_minutes: float | None = None):
    t1 = tfs.get('1m', {})
    t5 = tfs.get('5m', {})
    t10 = tfs.get('10m', {})

    conf5 = t5.get('conf', 0.0)
    conf10 = t10.get('conf', 0.0)
    dir5 = t5.get('dir', 0)
    dir10 = t10.get('dir', 0)

    avg_conf = (conf5 + conf10) / 2.0

    tf_choice = "5m"
    action = "انتظار"
    color = "neutral"

    if dir10 == 1 and dir5 == 1 and avg_conf >= threshold:
        action = "شراء"
        color = "long"
        tf_choice = "5m"
    elif dir10 == 0 and dir5 == 0 and avg_conf >= threshold:
        action = "بيع"
        color = "short"
        tf_choice = "5m"
    else:
        if t1.get('conf', 0) >= threshold and t1.get('dir', 0) in (0,1):
            action = "شراء" if t1['dir']==1 else "بيع"
            color = "long" if t1['dir']==1 else "short"
            tf_choice = "1m"

    if pred_minutes is not None:
        duration = int(max(min_minutes, min(max_minutes, pred_minutes)))
        conf_pct = round(avg_conf * 100.0, 1)
    else:
        tp_pct = t5.get('tp_pct', 0.3) or 0.3
        duration = int(max(min_minutes, min(max_minutes, tp_pct * 20)))
        conf_pct = round(avg_conf * 100.0, 1)

    return {"action": action, "timeframe": tf_choice, "confidence_pct": conf_pct,
            "duration_min": duration, "ts": datetime.datetime.utcnow().isoformat() + "Z"}

def compute_market_summary(payloads: list[dict]) -> dict:
    if not payloads:
        return {}
    n = len(payloads)
    avg_conf = 0.0
    liq = 0.0
    spread = 0.0
    pressure_votes = 0.0
    trend_up_votes = 0
    for p in payloads:
        tfs = p.get('tfs', {})
        # نستخدم 5m كمرجع للسوق
        t5 = tfs.get('5m') or {}
        avg_conf += float(t5.get('conf', 0.0))
        # extras
        ex = p.get('extras', {})
        lb = ex.get('liq_bias_pct', 0.0) or 0.0
        sp = ex.get('spread_pct', 0.0) or 0.0
        pr = ex.get('pressure', 0.0) or 0.0
        liq += lb
        spread += sp
        pressure_votes += pr
        # اتجاه السوق 5m
        if int(t5.get('dir', 0)) == 1:
            trend_up_votes += 1
    avg_conf /= max(1, n)
    liq /= max(1, n)
    spread /= max(1, n)
    trend = "Bullish" if trend_up_votes >= (n - trend_up_votes) else "Bearish"
    pres_label = "Buy Side Dominant" if pressure_votes > 0 else ("Sell Side Dominant" if pressure_votes < 0 else "Neutral")

    return {
        "trend": trend,
        "avg_conf_pct": round(avg_conf*100.0, 1),
        "liq_bias_pct": round(liq, 1),
        "avg_spread_pct": round(spread, 2),
        "pressure_label": pres_label,
        "ts": datetime.datetime.utcnow().isoformat() + "Z"
    }

def poller():
    build_name_cache()
    load_top_symbols()
    while True:
        payloads = []
        if int(time.time()) % 600 < POLL_SECONDS:
            load_top_symbols()
        for sym in symbols:
            computed = compute_for_symbol(sym)
            if not computed:
                continue
            core, extras = computed
            label = symbol_display_name.get(sym, f"{sym.replace('USDT','')} ({sym[:-4]}/USDT)")

            payload = {'symbol': sym, 'name': label, 'tfs': core, 'extras': extras or {}}
            payload['recommendation'] = rec_from_payload(core, threshold=REC_CONF_THRESHOLD,
                                                         min_minutes=REC_MIN_MINUTES, max_minutes=REC_MAX_MINUTES,
                                                         pred_minutes=extras.get('pred_minutes') if extras else None)
            payloads.append(payload)
            socketio.emit('top15_update', payload)

        # بعد إرسال جميع العملات، نرسل ملخص السوق العام مرة واحدة
        summary = compute_market_summary(payloads)
        if summary:
            socketio.emit('market_summary', summary)

        time.sleep(POLL_SECONDS)

from flask import send_from_directory
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/favicon.ico')
def fav():
    return ('',204)

if __name__ == '__main__':
    threading.Thread(target=poller, daemon=True).start()
    port = int(os.environ.get('PORT', 8000))
    socketio.run(app, host='0.0.0.0', port=port)

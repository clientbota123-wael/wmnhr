import pandas as pd
from binance.spot import Spot

def make_client(timeout=10, api_key=None, api_secret=None):
    return Spot(api_key=api_key, api_secret=api_secret, timeout=timeout)

def fetch_klines(client, symbol, interval='1m', limit=900):
    kl = client.klines(symbol, interval=interval, limit=limit)
    df = pd.DataFrame([{
        'open_time': pd.to_datetime(r[0], unit='ms', utc=True),
        'open': float(r[1]), 'high': float(r[2]), 'low': float(r[3]),
        'close': float(r[4]), 'volume': float(r[5]),
        'close_time': pd.to_datetime(r[6], unit='ms', utc=True),
    } for r in kl])
    return df

def fetch_book(client, symbol):
    bt = client.book_ticker(symbol)
    return {'bid': float(bt.get('bidPrice', 0.0) or 0.0),
            'ask': float(bt.get('askPrice', 0.0) or 0.0),
            'bid_qty': float(bt.get('bidQty', 0.0) or 0.0),
            'ask_qty': float(bt.get('askQty', 0.0) or 0.0)}

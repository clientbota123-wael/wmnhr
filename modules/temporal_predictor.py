import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

class ReversalTimer:
    def __init__(self, max_forward: int = 30, min_rows: int = 120):
        self.max_forward = max_forward
        self.min_rows = min_rows
        self.model = GradientBoostingRegressor(random_state=42)
        self.fitted = False

    def _features(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d['ret1'] = d['close'].pct_change()
        d['ret3'] = d['close'].pct_change(3)
        d['ret5'] = d['close'].pct_change(5)
        d['rsi'] = d['rsi']
        d['atrp'] = d['atr'] / (d['close'] + 1e-9)
        d['mom'] = (d['close'] - d['open']) / (d['open'] + 1e-9)
        d['rng'] = (d['high'] - d['low']) / (d['open'] + 1e-9)
        d['volz'] = (d['volume'] / (d['volume'].rolling(20).mean() + 1e-9)).clip(0, 10)
        return d[['ret1','ret3','ret5','rsi','atrp','mom','rng','volz']].fillna(0.0)

    def _labels(self, df: pd.DataFrame) -> pd.Series:
        price = df['close'].values
        mom = np.sign(np.diff(price, prepend=price[0]) + 1e-12)
        n = len(price)
        lbl = np.full(n, self.max_forward, dtype=float)
        for i in range(n-1):
            cur = mom[i]
            for fwd in range(1, self.max_forward+1):
                j = i + fwd
                if j >= n: break
                if np.sign(price[j] - price[i]) != cur:
                    lbl[i] = fwd
                    break
        return pd.Series(lbl, index=df.index)

    def fit_predict_minutes(self, df: pd.DataFrame) -> float | None:
        if df is None or len(df) < self.min_rows:
            return None
        feats = self._features(df)
        y = self._labels(df)
        X = feats.iloc[:-1]
        y_tr = y.iloc[:-1]
        if len(X) < self.min_rows:
            return None
        try:
            self.model.fit(X, y_tr)
            self.fitted = True
            pred = float(self.model.predict(feats.iloc[[-1]])[0])
            return max(1.0, min(self.max_forward, pred))
        except Exception:
            return None

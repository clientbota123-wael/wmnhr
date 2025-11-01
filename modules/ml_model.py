import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression

class MLNextMove:
    def __init__(self, min_samples: int = 100):
        self.min_samples = min_samples
        self.model = LogisticRegression(max_iter=250)
        self.fitted = False

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d['ret1'] = d['close'].pct_change()
        d['ret3'] = d['close'].pct_change(3)
        d['ret5'] = d['close'].pct_change(5)
        d['hl_spread'] = (d['high'] - d['low']) / (d['close'].shift(1).abs() + 1e-9)
        d['body'] = (d['close'] - d['open']) / (d['open'].abs() + 1e-9)
        d['vol_norm'] = (d['volume'] / (d['volume'].rolling(20).mean() + 1e-9)).clip(0, 10)
        feats = d[['ret1','ret3','ret5','hl_spread','body','vol_norm']].fillna(0.0)
        return feats

    def fit_predict_prob(self, df: pd.DataFrame) -> float | None:
        if df is None or len(df) < self.min_samples + 2:
            return None
        feats = self._build_features(df)
        y = (df['close'].shift(-1) > df['close']).astype(int).iloc[:-1]
        X = feats.iloc[:-1]
        if y.sum() == 0 or y.sum() == len(y):
            return 0.5
        try:
            self.model.fit(X, y)
            self.fitted = True
            prob = float(self.model.predict_proba(feats.iloc[[-1]])[0,1])
            return prob
        except Exception:
            return None

"""wwm_sim.delay_head — the Stage-3 DELAY head (learned).

The rollout gives an EMPTY-WORLD finish estimate (traffic-blind). The delay head learns,
from the sim's own diary, how much EXTRA time congestion adds — "legs that looked like this
ran +X late" — so a traffic-AWARE finish = empty_finish + delay_head(features).

Label: delay = actual (assign->deliver) duration − empty-world finish estimate (pred_finish).
Features = the `feat` dict PartAController builds per candidate (order below). Google-Maps-for-
warehouse: route from the map (rollout), delay from history (this head).

Usage matches PartAController: the model is a CALLABLE, `delay_head(feat_dict) -> steps`.
"""
from __future__ import annotations

# order of the feat-dict keys fed to the model
FEATURES = ["pred_finish", "my_arrival", "dock", "picker_eta", "my_wait",
            "n_busy_agv", "n_free_pk", "q_size", "value", "dl_slack"]


def feat_row(feat):
    return [float(feat[k]) for k in FEATURES]


class DelayHead:
    """LightGBM regressor: congestion features -> predicted extra delay (steps).
    Callable so PartAController can do `finish + delay_head(feat)`."""

    def __init__(self, model=None):
        self.model = model

    def train(self, feats, delays):
        import numpy as np
        import lightgbm as lgb
        X = np.asarray([feat_row(f) for f in feats], dtype=float)
        y = np.asarray(delays, dtype=float)
        self.model = lgb.LGBMRegressor(
            n_estimators=300, num_leaves=31, learning_rate=0.05, min_child_samples=20,
            subsample=0.9, colsample_bytree=0.9, verbose=-1)
        self.model.fit(X, y)
        return self

    def __call__(self, feat):
        import numpy as np
        return float(self.model.predict(np.asarray([feat_row(feat)], dtype=float))[0])

    def predict_rows(self, feats):
        import numpy as np
        return self.model.predict(np.asarray([feat_row(f) for f in feats], dtype=float))

    def importances(self):
        return dict(zip(FEATURES, self.model.feature_importances_))

    def save(self, path):
        import pickle
        with open(path, "wb") as f:
            pickle.dump(self.model, f)

    @classmethod
    def load(cls, path):
        import pickle
        with open(path, "rb") as f:
            return cls(pickle.load(f))

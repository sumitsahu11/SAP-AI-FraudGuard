from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from config import IFOREST_CONTAMINATION
from src.utils import LOGGER


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    feats = df.copy()

    feats["Amount"] = feats["Amount"].fillna(0)

    vendor_group = feats.groupby("Vendor")["Amount"]
    feats["VendorAvgAmount"] = vendor_group.transform("mean")
    feats["VendorStdAmount"] = vendor_group.transform("std").fillna(0)
    feats["VendorTxnCount"] = vendor_group.transform("count")

    feats["InvoiceDayOfWeek"] = feats["InvoiceDate"].dt.dayofweek.fillna(-1)

    feature_cols = [
        "Amount",
        "VendorAvgAmount",
        "VendorStdAmount",
        "VendorTxnCount",
        "InvoiceDayOfWeek",
    ]

    return feats[feature_cols]


def run_isolation_forest(df: pd.DataFrame) -> pd.DataFrame:
    
    LOGGER.info("Running Isolation Forest anomaly detection")

    df = df.copy()
    X = _build_features(df)

    X = X.fillna(0)

    model = IsolationForest(
        n_estimators=100,
        contamination=IFOREST_CONTAMINATION,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(X)

    scores = -model.decision_function(X)
    df["ML_AnomalyScore"] = scores

    threshold = np.quantile(scores, 1 - IFOREST_CONTAMINATION)
    df["ML_IsAnomaly"] = df["ML_AnomalyScore"] >= threshold

    return df
from __future__ import annotations
import pandas as pd
from config import (
    RISK_SCORE_HIGH_THRESHOLD,
    RISK_SCORE_MEDIUM_THRESHOLD,
)
from src.utils import LOGGER

def add_risk_scores(df: pd.DataFrame) -> pd.DataFrame:

    LOGGER.info("Combining rules and ML into risk scores")

    df = df.copy()

    def compute_score(row) -> float:
        score = 0.0

        if row.get("Rule_ExactDuplicate", False):
            score += 0.45
        if row.get("Rule_SoftDuplicate", False):
            score += 0.3
        if row.get("Rule_HighAmountForVendor", False):
            score += 0.2
        if row.get("Rule_MissingPO", False):
            score += 0.1
        if row.get("Rule_NegativeOrZeroAmount", False):
            score += 0.1

        if row.get("ML_IsAnomaly", False):
            score += 0.25

        return max(0.0, min(1.0, score))

    df["RiskScore"] = df.apply(compute_score, axis=1)

    def label_level(score: float) -> str:
        if score >= RISK_SCORE_HIGH_THRESHOLD:
            return "HIGH"
        elif score >= RISK_SCORE_MEDIUM_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    df["RiskLevel"] = df["RiskScore"].apply(label_level)

    def build_reason(row) -> str:
        reasons = []

        rule_flags = row.get("Rule_Flags", [])
        if rule_flags:
            reasons.extend(rule_flags)

        if row.get("ML_IsAnomaly", False):
            reasons.append(
                "ML model marked this invoice as anomalous based on historical patterns"
            )

        if not reasons:
            return "No strong risk signals detected."
        return "; ".join(reasons)

    df["RiskReason"] = df.apply(build_reason, axis=1)

    return df
from __future__ import annotations
import pandas as pd
from src.utils import LOGGER

def apply_rule_checks(df: pd.DataFrame) -> pd.DataFrame:

    LOGGER.info("Applying rule-based checks")

    df = df.copy()

    df["Rule_ExactDuplicate"] = df.duplicated(
        subset=["Vendor", "InvoiceNumber"], keep=False
    )
    
    df["Rule_SoftDuplicate"] = df.duplicated(
        subset=["Vendor", "InvoiceDate", "Amount"], keep=False
    )

    df["Rule_MissingPO"] = df["PONumber"].isna() | (df["PONumber"].astype(str).str.strip() == "")

    df["Rule_NegativeOrZeroAmount"] = df["Amount"] <= 0

    vendor_stats = df.groupby("Vendor")["Amount"].agg(["median"])  # Amount much higher than vendor historical median (e.g., > 3x median)
    vendor_stats = vendor_stats.rename(columns={"median": "VendorMedianAmount"})
    df = df.merge(vendor_stats, left_on="Vendor", right_index=True, how="left")

    df["Rule_HighAmountForVendor"] = df["Amount"] > 3 * df["VendorMedianAmount"]

    rule_columns = [
        "Rule_ExactDuplicate",
        "Rule_SoftDuplicate",
        "Rule_HighAmountForVendor",
        "Rule_MissingPO",
        "Rule_NegativeOrZeroAmount",
    ]

    def collect_flags(row) -> list[str]:
        flags = []
        if row["Rule_ExactDuplicate"]:
            flags.append("Exact duplicate (same vendor & invoice number)")
        if row["Rule_SoftDuplicate"]:
            flags.append("Soft duplicate (same vendor, date & amount)")
        if row["Rule_HighAmountForVendor"]:
            flags.append("Amount >> vendor historical median")
        if row["Rule_MissingPO"]:
            flags.append("Missing PO number")
        if row["Rule_NegativeOrZeroAmount"]:
            flags.append("Amount is zero or negative")
        return flags

    df["Rule_Flags"] = df.apply(collect_flags, axis=1)

    return df
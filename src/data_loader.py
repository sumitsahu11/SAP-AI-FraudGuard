from __future__ import annotations

from pathlib import Path
import pandas as pd

from src.utils import LOGGER

REQUIRED_COLUMNS = [
    "Vendor",
    "InvoiceNumber",
    "InvoiceDate",
    "Amount",
    "Currency",
    "PONumber",
]


def _make_unique_columns(columns):
    seen = {}
    new_cols = []

    for col in columns:
        col = str(col).strip()
        if col not in seen:
            seen[col] = 0
            new_cols.append(col)
        else:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
    return new_cols


def load_invoices(file_path: Path) -> pd.DataFrame:
    LOGGER.info(f"Loading invoices from {file_path}")
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(file_path)
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    df.columns = [str(c).strip() for c in df.columns]

    rename_map = {}
    for col in df.columns:
        lower = col.lower()

        if lower in {"vendor", "supplier", "vendor name", "supplier name"}:
            rename_map[col] = "Vendor"
        elif lower in {"invoice number", "invoice no", "invoice_no", "invoicenumber"}:
            rename_map[col] = "InvoiceNumber"
        elif lower in {"invoice date", "invoice_date", "invoicedate", "date"}:
            rename_map[col] = "InvoiceDate"
        elif lower in {"amount", "invoice amount", "gross amount", "net amount"}:
            rename_map[col] = "Amount"
        elif lower in {"currency", "curr"}:
            rename_map[col] = "Currency"
        elif lower in {"po number", "po", "po no", "ponumber"}:
            rename_map[col] = "PONumber"

    df = df.rename(columns=rename_map)
    df.columns = _make_unique_columns(df.columns)

    final_cols = {}
    for req in REQUIRED_COLUMNS:
        matches = [c for c in df.columns if c == req or c.startswith(req + "_")]
        if matches:
            final_cols[req] = matches[0]

    missing = [c for c in REQUIRED_COLUMNS if c not in final_cols]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    clean_df = pd.DataFrame()
    clean_df["Vendor"] = df[final_cols["Vendor"]]
    clean_df["InvoiceNumber"] = df[final_cols["InvoiceNumber"]]
    clean_df["InvoiceDate"] = pd.to_datetime(df[final_cols["InvoiceDate"]], errors="coerce")
    clean_df["Amount"] = pd.to_numeric(df[final_cols["Amount"]], errors="coerce")
    clean_df["Currency"] = df[final_cols["Currency"]]
    clean_df["PONumber"] = df[final_cols["PONumber"]]

    clean_df = clean_df.dropna(subset=["Vendor", "InvoiceNumber", "Amount"])
    clean_df = clean_df.reset_index(drop=True)
    clean_df["InvoiceID"] = clean_df.index.astype(str)

    return clean_df
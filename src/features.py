import pandas as pd

def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Ensure dates
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])

    # Amount-based
    df["LogAmount"] = df["Amount"].apply(lambda x: 0 if x <= 0 else np.log(x))

    # Vendor behavior
    df["VendorInvoiceCount"] = df.groupby("Vendor")["InvoiceNumber"].transform("count")
    df["VendorAvgAmount"] = df.groupby("Vendor")["Amount"].transform("mean")

    # Time-based
    df = df.sort_values(["Vendor", "InvoiceDate"])
    df["DaysSinceLastInvoice"] = (
        df.groupby("Vendor")["InvoiceDate"]
          .diff()
          .dt.days
          .fillna(999)
    )

    # Flags
    df["HasPO"] = df["PONumber"].notna() & (df["PONumber"] != "")
    df["HighValueInvoice"] = df["Amount"] > 3 * df["VendorAvgAmount"]

    return df
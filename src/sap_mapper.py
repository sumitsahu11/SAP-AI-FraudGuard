def map_to_sap_fields(df):
    """
    Maps invoice dataframe columns to SAP BKPF / BSEG concepts
    """
    sap_map = {}

    # BKPF (Header)
    sap_map["BELNR"] = df["InvoiceNumber"]   # Document Number
    sap_map["BUDAT"] = df["InvoiceDate"]     # Posting Date
    sap_map["WAERS"] = df["Currency"]        # Currency

    # BSEG (Line Item)
    sap_map["LIFNR"] = df["Vendor"]           # Vendor
    sap_map["DMBTR"] = df["Amount"]           # Amount
    sap_map["EBELN"] = df["PONumber"]          # PO Number
    sap_map["KOSTL"] = df.get("CostCenter")    # Cost Center

    return sap_map
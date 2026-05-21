from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional, List
import pandas as pd

@dataclass
class ParsedQuery:
    original_query: str
    normalized_query: str
    intent: str
    vendor: Optional[str]
    risk_level: Optional[str]
    month: Optional[str]
    year: Optional[str]
    keywords: List[str]
    expanded_query: str


MONTHS = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}

TEXT_REPLACEMENTS = {
    "pls": "please",
    "plz": "please",
    "po no": "po",
    "purchase order": "po",
    "bill": "invoice",
    "bills": "invoices",
    "payment": "invoice",
    "payments": "invoices",
    "supplier": "vendor",
    "suppliers": "vendors",
    "fraudulent": "fraud",
    "suspiscious": "suspicious",
    "suspecious": "suspicious",
    "anamoly": "anomaly",
    "abnormal": "anomaly",
    "weird": "suspicious",
    "strange": "suspicious",
    "dangerous": "high risk",
    "duplicate bills": "duplicate invoices",
    "same bill": "duplicate invoice",
    "same payment": "duplicate invoice",
    "twice paid": "duplicate",
    "paid twice": "duplicate",
    "double payment": "duplicate",
    "without po": "missing po",
    "no po": "missing po",
    "po missing": "missing po",
    "blank po": "missing po",
    "high amt": "high amount",
    "large amount": "high amount",
    "huge amount": "high amount",
    "overpriced": "high amount",
    "costly": "high amount",
    "expensive": "high amount",
    "dikhao": "show",
    "batao": "tell",
    "mujhe": "me",
    "ka": "",
    "ke": "",
    "ki": "",
    "wala": "",
    "wali": "",
}


INTENT_SYNONYMS = {
    "duplicate": [
        "duplicate", "duplicate invoice", "duplicate invoices", "repeated invoice",
        "repeat invoice", "same invoice", "same invoices", "same vendor same amount",
        "paid twice", "double payment", "same bill", "same payment",
        "invoice repeated", "invoice repeated twice", "same vendor date amount",
        "duplicate case", "duplicate cases", "duplicate payment", "same invoice number",
        "repeat payment", "multiple same invoice", "repeated bill", "duplicate bills",
        "double billed", "same transaction twice", "twice billed"
    ],
    "high_risk": [
        "risky", "risk", "high risk", "medium risk", "suspicious", "fraud",
        "fraud case", "fraud cases", "anomaly", "anomalies", "flagged",
        "danger", "dangerous", "need attention", "needs attention", "problematic",
        "issue invoices", "concerning invoices", "alert invoices", "red flags",
        "suspicious invoices", "risky invoices", "fraudulent invoices",
        "bad invoices", "odd invoices", "weird invoices"
    ],
    "missing_po": [
        "missing po", "without po", "no po", "po missing", "po blank",
        "purchase order missing", "purchase order blank", "missing purchase order",
        "no purchase order", "invoice without po", "invoices without po",
        "po not available", "po empty", "blank po number"
    ],
    "high_amount": [
        "high amount", "very high amount", "large amount", "huge amount",
        "unusual amount", "too much amount", "too expensive", "expensive invoice",
        "overpriced", "costly", "abnormal amount", "amount anomaly", "outlier amount",
        "high value invoices", "big invoices", "large invoices", "too high",
        "vendor historical median", "higher than usual", "above average amount",
        "unusually expensive", "too costly"
    ],
    "vendor_search": [
        "vendor", "vendors", "supplier", "suppliers", "from vendor",
        "from supplier", "for vendor", "for supplier", "vendor invoices",
        "supplier invoices", "vendor related", "particular vendor"
    ],
    "explain": [
        "why", "explain", "reason", "tell reason", "what is reason",
        "why risky", "why suspicious", "why flagged", "why high risk",
        "explain invoice", "explain risk", "what happened", "what is wrong",
        "why marked", "why selected", "how is this risky"
    ],
    "top_vendors": [
        "top vendors", "risky vendors", "vendors with most risk", "which vendor has most risk",
        "most suspicious vendor", "top suspicious vendors", "top risky vendors"
    ],
    "recent": [
        "recent", "latest", "new", "current", "recent invoices", "latest invoices"
    ],
    "count": [
        "how many", "count", "number of", "total number", "how much count"
    ],
}


STOPWORDS = {
    "show", "me", "the", "is", "are", "a", "an", "for", "of", "to", "in",
    "on", "all", "with", "this", "that", "from", "about", "please", "tell",
    "find", "get", "give", "list", "need", "want", "can", "you", "do",
    "we", "there", "any", "which", "what", "who", "where", "when"
}


def normalize_text(text: str) -> str:
    text = text.lower().strip()

    for src, tgt in TEXT_REPLACEMENTS.items():
        text = text.replace(src, tgt)

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_intent(query: str) -> str:
    q = normalize_text(query)

    scores = {intent: 0 for intent in INTENT_SYNONYMS.keys()}

    for intent, phrases in INTENT_SYNONYMS.items():
        for phrase in phrases:
            if phrase in q:
                scores[intent] += 2

            phrase_words = phrase.split()
            for w in phrase_words:
                if w in q.split():
                    scores[intent] += 1

    best_intent = max(scores, key=scores.get)
    if scores[best_intent] == 0:
        return "general"
    return best_intent


def detect_risk_level(query: str) -> Optional[str]:
    q = normalize_text(query)

    if "high risk" in q or "severe" in q:
        return "HIGH"
    if "medium risk" in q or "moderate risk" in q:
        return "MEDIUM"
    if "low risk" in q or "safe" in q:
        return "LOW"
    return None

def detect_month_and_year(query: str) -> tuple[Optional[str], Optional[str]]:
    q = normalize_text(query)

    month = None
    year = None

    for name, num in MONTHS.items():
        if name in q:
            month = num
            break

    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match:
        year = year_match.group(1)

    return month, year


def detect_vendor(query: str, df: pd.DataFrame) -> Optional[str]:
    q = normalize_text(query)

    if "Vendor" not in df.columns:
        return None

    vendors = df["Vendor"].dropna().astype(str).unique().tolist()
    vendors_sorted = sorted(vendors, key=len, reverse=True)

    for vendor in vendors_sorted:
        v = vendor.lower().strip()
        if v and v in q:
            return vendor

    q_words = set(q.split())
    best_vendor = None
    best_score = 0

    for vendor in vendors_sorted:
        parts = set(vendor.lower().split())
        score = len(parts.intersection(q_words))
        if score > best_score and score >= 2:
            best_vendor = vendor
            best_score = score

    return best_vendor


def extract_keywords(query: str) -> List[str]:
    q = normalize_text(query)
    words = re.findall(r"[a-zA-Z0-9]+", q)
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def expand_query(query: str, intent: str) -> str:
    q = normalize_text(query)

    expansion_map = {
        "duplicate": (
            "duplicate repeated same invoice same vendor same amount same date "
            "same invoice number paid twice duplicate payment"
        ),
        "high_risk": (
            "high risk suspicious fraud anomaly flagged invoice red flags concern"
        ),
        "missing_po": (
            "missing po blank po no po purchase order missing purchase order blank"
        ),
        "high_amount": (
            "high amount unusual amount outlier overpriced higher than usual amount anomaly"
        ),
        "vendor_search": (
            "vendor supplier invoice history transactions risk vendor analysis"
        ),
        "explain": (
            "explain why risky suspicious anomaly reason flagged invoice reason"
        ),
        "top_vendors": (
            "top risky vendors suspicious vendors most flagged vendors highest risk vendors"
        ),
        "recent": (
            "recent latest new current invoices recent suspicious invoices"
        ),
        "count": (
            "count total number of invoices count risky suspicious duplicate invoices"
        ),
        "general": (
            "invoice risk fraud anomalies suspicious vendor amount po duplicate invoices"
        ),
    }

    return f"{q} {expansion_map.get(intent, expansion_map['general'])}"


def parse_query(query: str, df: pd.DataFrame) -> ParsedQuery:
    normalized = normalize_text(query)
    intent = detect_intent(normalized)
    vendor = detect_vendor(normalized, df)
    risk_level = detect_risk_level(normalized)
    month, year = detect_month_and_year(normalized)
    keywords = extract_keywords(normalized)
    expanded = expand_query(normalized, intent)

    return ParsedQuery(
        original_query=query,
        normalized_query=normalized,
        intent=intent,
        vendor=vendor,
        risk_level=risk_level,
        month=month,
        year=year,
        keywords=keywords,
        expanded_query=expanded,
    )


def filter_df_by_query(df: pd.DataFrame, parsed: ParsedQuery) -> pd.DataFrame:
    filtered = df.copy()

    if parsed.vendor:
        filtered = filtered[
            filtered["Vendor"].astype(str).str.lower() == parsed.vendor.lower()
        ]

    if parsed.risk_level:
        filtered = filtered[filtered["RiskLevel"] == parsed.risk_level]

    if parsed.month and "InvoiceDate" in filtered.columns:
        filtered = filtered[
            filtered["InvoiceDate"].dt.month.astype(str).str.zfill(2) == parsed.month
        ]

    if parsed.year and "InvoiceDate" in filtered.columns:
        filtered = filtered[
            filtered["InvoiceDate"].dt.year.astype(str) == parsed.year
        ]

    if parsed.intent == "duplicate":
        dup_cols = {"Rule_ExactDuplicate", "Rule_SoftDuplicate"}
        if dup_cols.issubset(filtered.columns):
            filtered = filtered[
                (filtered["Rule_ExactDuplicate"] == True) |
                (filtered["Rule_SoftDuplicate"] == True)
            ]

    elif parsed.intent == "missing_po":
        if "Rule_MissingPO" in filtered.columns:
            filtered = filtered[filtered["Rule_MissingPO"] == True]

    elif parsed.intent == "high_amount":
        if "Rule_HighAmountForVendor" in filtered.columns:
            filtered = filtered[filtered["Rule_HighAmountForVendor"] == True]

    elif parsed.intent == "high_risk":
        filtered = filtered[filtered["RiskLevel"].isin(["HIGH", "MEDIUM"])]

    elif parsed.intent == "recent":
        if "InvoiceDate" in filtered.columns and not filtered.empty:
            filtered = filtered.sort_values("InvoiceDate", ascending=False).head(20)

    elif parsed.intent == "top_vendors":
        if not filtered.empty:
            vendor_counts = (
                filtered[filtered["RiskLevel"].isin(["HIGH", "MEDIUM"])]
                .groupby("Vendor", as_index=False)
                .size()
                .rename(columns={"size": "RiskCount"})
                .sort_values("RiskCount", ascending=False)
            )
            top_vendors = vendor_counts["Vendor"].head(5).tolist()
            filtered = filtered[filtered["Vendor"].isin(top_vendors)]

    return filtered


def build_friendly_answer(parsed: ParsedQuery, rows: pd.DataFrame) -> str:
    if rows.empty:
        return (
            "I could not find matching invoices for that question in the current dataset. "
            "Try asking things like 'show duplicate invoices', 'find missing PO invoices', "
            "'show high-risk invoices for Vendor X', or 'which invoices have unusually high amounts?'."
        )

    lines = []

    if parsed.intent == "duplicate":
        lines.append(f"I found {len(rows)} possible duplicate invoice(s).")
    elif parsed.intent == "missing_po":
        lines.append(f"I found {len(rows)} invoice(s) with missing PO numbers.")
    elif parsed.intent == "high_amount":
        lines.append(f"I found {len(rows)} invoice(s) with unusually high amounts.")
    elif parsed.intent == "high_risk":
        lines.append(f"I found {len(rows)} risky invoice(s) matching your request.")
    elif parsed.intent == "top_vendors":
        lines.append("Here are invoices from the vendors with the highest number of risky cases.")
    elif parsed.intent == "recent":
        lines.append(f"Here are the most recent {len(rows)} invoice(s) matching your request.")
    elif parsed.intent == "count":
        lines.append(f"I found {len(rows)} invoice(s) matching your request.")
    elif parsed.vendor:
        lines.append(f"I found {len(rows)} invoice(s) related to vendor {parsed.vendor}.")
    elif parsed.risk_level:
        lines.append(f"I found {len(rows)} {parsed.risk_level.lower()} risk invoice(s).")
    else:
        lines.append(f"I found {len(rows)} invoice(s) relevant to your question.")

    if parsed.month or parsed.year:
        month_text = parsed.month if parsed.month else "any month"
        year_text = parsed.year if parsed.year else "any year"
        lines.append(f"Time filter applied: month={month_text}, year={year_text}.")

    preview = rows.head(5)

    lines.append("Top matches:")
    for _, row in preview.iterrows():
        amount = row.get("Amount", "")
        currency = row.get("Currency", "INR")
        risk = row.get("RiskLevel", "UNKNOWN")
        reason = row.get("RiskReason", "No reason available")
        inv_date = row.get("InvoiceDate", "")

        lines.append(
            f"- InvoiceID {row['InvoiceID']} | Vendor: {row['Vendor']} | "
            f"Invoice: {row['InvoiceNumber']} | Date: {inv_date} | "
            f"Amount: {amount} {currency} | Risk: {risk} | Reason: {reason}"
        )

    lines.append("")
    lines.append("You can also ask:")
    lines.append("- show duplicate invoices")
    lines.append("- find invoices with missing po")
    lines.append("- show risky invoices for a vendor")
    lines.append("- which invoices have unusually high amounts")
    lines.append("- show high risk invoices in april 2025")

    return "\n".join(lines)
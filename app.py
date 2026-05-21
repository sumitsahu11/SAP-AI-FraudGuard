from __future__ import annotations

import io
import os
import sqlite3
from typing import Optional

import pandas as pd
from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    session,
    flash,
)

from werkzeug.security import generate_password_hash, check_password_hash

from src.doc_indexer import build_doc_index
from src.doc_search import search_docs
from src.doc_summarizer import summarise_documents  # ← NEW

from config import (
    DATA_DIR,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    MAX_CONTENT_LENGTH,
)
from src.data_loader import load_invoices  # loads Excel/CSV into DataFrame
from src.ml_model import run_isolation_forest
from src.rag_engine import RAGEngine
from src.query_engine import parse_query, filter_df_by_query, build_friendly_answer
from src.risk_scoring import add_risk_scores
from src.rules_engine import apply_rule_checks
from src.utils import LOGGER, allowed_file

CURRENT_DF = None
CURRENT_RAG: Optional[RAGEngine] = None
CURRENT_DOC_INDEX = None
CURRENT_DOC_CHUNKS = []
CURRENT_DOC_SOURCES = []

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# -------------------------------------------------------------------
# AUTH / USERS
# -------------------------------------------------------------------

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-change-me")

USERS_DB_PATH = DATA_DIR / "users.db"


def init_user_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(USERS_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()


def get_user_by_username(username: str):
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def create_user(username: str, password: str) -> bool:
    password_hash = generate_password_hash(password)
    try:
        conn = sqlite3.connect(USERS_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # username already exists (UNIQUE constraint)
        return False


# -------------------------------------------------------------------
# ROUTES: AUTH + MAIN
# -------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    # Require login before showing main app
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Please enter both username and password.", "error")
            return render_template("login.html")

        user = get_user_by_username(username)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/signup", methods=["POST"])
def signup():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not username or not password or not confirm:
        flash("All fields are required.", "error")
        return redirect(url_for("login"))

    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("login"))

    created = create_user(username, password)
    if not created:
        flash("Username already exists. Please choose another.", "error")
        return redirect(url_for("login"))

    flash("Signup successful. You can now log in.", "success")
    return redirect(url_for("login"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/health", methods=["GET"])
def health():
    return (
        jsonify(
            {
                "status": "ok",
                "message": "SAP AI FraudGuard backend is running",
                "endpoints": [
                    "/",
                    "/health",
                    "/login",
                    "/signup",
                    "/logout",
                    "/api/process_invoices",
                    "/api/rag/explain",
                    "/api/rag/query",
                    "/api/invoice/<invoice_id>",
                    "/api/docfinder/process",
                    "/api/docfinder/query",
                    "/api/vendor_risk_overview",
                    "/api/ap_control_overview",
                    "/api/ap_control_charts",
                    "/api/what_if_simulator",
                    "/api/fraud_playbook",
                    "/api/summarize_docs",  # ← NEW
                ],
            }
        ),
        200,
    )


# -------------------------------------------------------------------
# INVOICE PIPELINE + RAG
# -------------------------------------------------------------------

@app.route("/api/process_invoices", methods=["POST"])
def process_invoices():
    """
    Upload Excel/CSV, run rules + ML + risk scoring, build RAG index,
    and return summary plus a sample of risky invoices.
    """
    global CURRENT_DF, CURRENT_RAG

    if "file" not in request.files:
        return jsonify({"error": "No file provided. Use form-data with key 'file'."}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    DATA_DIR.mkdir(exist_ok=True)
    save_path = DATA_DIR / file.filename
    file.save(save_path)

    try:
        # 1. Load
        df = load_invoices(save_path)

        # 2. Rule-based checks
        df = apply_rule_checks(df)

        # 3. ML anomaly checks
        df = run_isolation_forest(df)

        # 4. Risk scoring
        df = add_risk_scores(df)

        # 5. Build RAG index
        rag_engine = RAGEngine()
        rag_engine.build_index(df)

        CURRENT_DF = df
        CURRENT_RAG = rag_engine

        total_invoices = int(len(df))
        risky = df[df["RiskLevel"].isin(["HIGH", "MEDIUM"])]
        high_risk = df[df["RiskLevel"] == "HIGH"]

        summary = {
            "total_invoices": total_invoices,
            "risky_invoices": int(len(risky)),
            "high_risk_invoices": int(len(high_risk)),
            "total_risk_amount": float(risky["Amount"].sum()) if not risky.empty else 0.0,
            "high_risk_amount": float(high_risk["Amount"].sum()) if not high_risk.empty else 0.0,
        }

        top_n = 20
        risk_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        risky = risky.copy()
        risky["RiskOrder"] = risky["RiskLevel"].map(risk_order)

        risky_sorted = risky.sort_values(
            by=["RiskOrder", "RiskScore", "Amount"],
            ascending=[False, False, False],
        ).head(top_n)

        risky_records = risky_sorted[
            [
                "InvoiceID",
                "Vendor",
                "InvoiceNumber",
                "InvoiceDate",
                "Amount",
                "Currency",
                "PONumber",
                "RiskLevel",
                "RiskScore",
                "RiskReason",
            ]
        ].copy()

        risky_records["InvoiceDate"] = risky_records["InvoiceDate"].astype(str)

        return (
            jsonify(
                {
                    "summary": summary,
                    "risky_invoices_sample": risky_records.to_dict(orient="records"),
                }
            ),
            200,
        )

    except Exception as e:
        LOGGER.exception("Error while processing invoices")
        return jsonify({"error": str(e)}), 500

    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass


@app.route("/api/invoice/<invoice_id>", methods=["GET"])
def get_invoice(invoice_id: str):
    """
    Return the selected invoice + vendor history table.
    """
    global CURRENT_DF

    if CURRENT_DF is None:
        return (
            jsonify(
                {
                    "error": "No invoices processed yet. Upload a file via /api/process_invoices first."
                }
            ),
            400,
        )

    df = CURRENT_DF

    if "InvoiceID" not in df.columns:
        return jsonify({"error": "InvoiceID column not found in dataset."}), 500

    mask_current = df["InvoiceID"].astype(str) == str(invoice_id)
    if not mask_current.any():
        return jsonify({"error": f"InvoiceID {invoice_id} not found in current dataset."}), 404

    current_row = df.loc[mask_current].iloc[0]

    display_cols = [
        "InvoiceID",
        "Vendor",
        "InvoiceNumber",
        "InvoiceDate",
        "Amount",
        "Currency",
        "PONumber",
        "RiskLevel",
        "RiskScore",
        "RiskReason",
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    record = {col: str(current_row[col]) for col in display_cols}
    sheet_cols = display_cols
    sheet_vals = [record[col] for col in sheet_cols]

    history_rows = []
    history_cols = []
    current_id_str = str(invoice_id)

    vendor_col = "Vendor" if "Vendor" in df.columns else None
    if vendor_col is not None:
        vendor_value = current_row[vendor_col]
        history_df = df[df[vendor_col] == vendor_value].copy()

        if "InvoiceDate" in history_df.columns:
            history_df["__InvoiceDateSort"] = history_df["InvoiceDate"]
            history_df = history_df.sort_values("__InvoiceDateSort")
            history_df = history_df.drop(columns=["__InvoiceDateSort"])

        base_history_cols = [
            "InvoiceID",
            "InvoiceNumber",
            "InvoiceDate",
            "Amount",
            "Currency",
            "PONumber",
            "RiskLevel",
            "RiskScore",
        ]
        history_cols = [c for c in base_history_cols if c in history_df.columns]

        for _, r in history_df.iterrows():
            history_rows.append([str(r[c]) for c in history_cols])

    history_payload = {
        "columns": history_cols,
        "rows": history_rows,
        "current_invoice_id": current_id_str,
    }

    return jsonify(
        {
            "invoice": record,
            "sheet": {
                "columns": sheet_cols,
                "values": sheet_vals,
            },
            "history": history_payload,
        }
    ), 200


@app.route("/api/rag/explain", methods=["POST"])
def rag_explain():
    global CURRENT_DF, CURRENT_RAG

    if CURRENT_DF is None or CURRENT_RAG is None:
        return (
            jsonify(
                {
                    "error": "No invoices processed yet. Call /api/process_invoices first with an Excel/CSV file."
                }
            ),
            400,
        )

    data = request.get_json(silent=True) or {}
    invoice_id = str(data.get("invoice_id", "")).strip()
    question = data.get("question")

    if not invoice_id:
        return jsonify({"error": "Missing 'invoice_id' in request body."}), 400

    explanation = CURRENT_RAG.explain_invoice(
        df=CURRENT_DF,
        invoice_id=invoice_id,
        user_question=question,
    )

    return jsonify(explanation), 200


@app.route("/api/rag/query", methods=["POST"])
def rag_query():
    global CURRENT_DF, CURRENT_RAG

    if CURRENT_DF is None or CURRENT_RAG is None:
        return (
            jsonify(
                {
                    "error": "No invoices processed yet. Call /api/process_invoices first with an Excel/CSV file."
                }
            ),
            400,
        )

    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "Missing or empty 'question'."}), 400

    parsed = parse_query(question, CURRENT_DF)
    filtered_df = filter_df_by_query(CURRENT_DF, parsed)
    sims = CURRENT_RAG.find_similar_invoices(query=parsed.expanded_query)
    answer = build_friendly_answer(parsed, filtered_df)

    return jsonify(
        {
            "question": question,
            "normalized_query": parsed.normalized_query,
            "intent": parsed.intent,
            "detected_vendor": parsed.vendor,
            "detected_risk_level": parsed.risk_level,
            "detected_month": parsed.month,
            "detected_year": parsed.year,
            "keywords": parsed.keywords,
            "answer": answer,
            "similar_invoices": [s.__dict__ for s in sims[:5]],
        }
    ), 200


# -------------------------------------------------------------------
# DOCFINDER
# -------------------------------------------------------------------

@app.route("/api/docfinder/process", methods=["POST"])
def process_docfinder_files():
    global CURRENT_DOC_INDEX, CURRENT_DOC_CHUNKS, CURRENT_DOC_SOURCES

    if "files" not in request.files:
        return jsonify({"error": "No files provided. Use form-data key 'files'."}), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files selected."}), 400

    try:
        index, chunks, sources = build_doc_index(files)

        CURRENT_DOC_INDEX = index
        CURRENT_DOC_CHUNKS = chunks
        CURRENT_DOC_SOURCES = sources

        unique_files = sorted(list(set([s["file_name"] for s in sources])))

        return (
            jsonify(
                {
                    "message": "Document knowledge base created successfully.",
                    "summary": {
                        "total_files": len(unique_files),
                        "total_chunks": len(chunks),
                        "supported_types": ["pdf", "docx", "pptx"],
                    },
                    "files": unique_files,
                }
            ),
            200,
        )

    except Exception as e:
        LOGGER.exception("Error while processing DocFinder files")
        return jsonify({"error": str(e)}), 500


@app.route("/api/docfinder/query", methods=["POST"])
def query_docfinder():
    global CURRENT_DOC_INDEX, CURRENT_DOC_CHUNKS, CURRENT_DOC_SOURCES

    if CURRENT_DOC_INDEX is None:
        return jsonify(
            {"error": "No project documents indexed yet. Upload and process files first."}
        ), 400

    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "Missing or empty 'question'."}), 400

    result = search_docs(
        query=question,
        index=CURRENT_DOC_INDEX,
        chunks=CURRENT_DOC_CHUNKS,
        sources=CURRENT_DOC_SOURCES,
        top_k=8,
    )

    return jsonify(result), 200


# -------------------------------------------------------------------
# DOCUMENT SUMMARIZER  ← NEW
# -------------------------------------------------------------------

@app.route("/api/summarize_docs", methods=["POST"])
def summarize_docs():
    """
    Accept one or more documents (PDF, DOCX, PPTX, TXT, CSV, XLSX)
    and return a rule-based extractive summary.

    Form fields:
        files       – one or more file uploads (key = 'files')
        num_points  – optional int, number of key sentences (default 10)
    """
    if "files" not in request.files:
        return jsonify({"error": "No files provided. Use form-data key 'files'."}), 400

    uploaded = request.files.getlist("files")
    if not uploaded or all(f.filename == "" for f in uploaded):
        return jsonify({"error": "No files selected."}), 400

    # parse optional parameter
    try:
        num_points = int(request.form.get("num_points", 10))
        num_points = max(3, min(num_points, 20))   # clamp 3–20
    except (TypeError, ValueError):
        num_points = 10

    SUPPORTED = {"pdf", "docx", "pptx", "txt", "md", "csv", "xlsx", "xls"}
    file_pairs = []
    rejected = []

    for f in uploaded:
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in SUPPORTED:
            rejected.append(f.filename)
            continue
        file_bytes = f.read()
        file_pairs.append((f.filename, file_bytes))

    if not file_pairs:
        return jsonify(
            {
                "error": "No supported files were found.",
                "rejected_files": rejected,
                "supported_types": sorted(SUPPORTED),
            }
        ), 400

    try:
        result = summarise_documents(file_pairs, num_points)
        result["rejected_files"] = rejected
        return jsonify(result), 200
    except Exception as exc:
        LOGGER.exception("Error during document summarisation")
        return jsonify({"error": str(exc)}), 500


# -------------------------------------------------------------------
# VENDOR RISK 360 + AP CONTROL + WHAT-IF + PLAYBOOK
# -------------------------------------------------------------------

@app.route("/api/vendor_risk_overview", methods=["GET"])
def vendor_risk_overview():
    global CURRENT_DF

    if CURRENT_DF is None:
        return jsonify(
            {"error": "No invoices processed yet. Upload a file on Tab 1 first."}
        ), 400

    df = CURRENT_DF.copy()

    if "InvoiceDate" in df.columns:
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")

    df["Amount"] = pd.to_numeric(df.get("Amount", 0.0), errors="coerce").fillna(0.0)
    df["RiskScore"] = pd.to_numeric(df.get("RiskScore", 0.0), errors="coerce").fillna(0.0)

    group = (
        df.groupby("Vendor", dropna=False)
        .agg(
            total_invoices=("InvoiceID", "count"),
            total_amount=("Amount", "sum"),
            risky_invoices=("RiskLevel", lambda s: s.isin(["HIGH", "MEDIUM"]).sum()),
            high_risk_invoices=("RiskLevel", lambda s: (s == "HIGH").sum()),
            avg_score=("RiskScore", "mean"),
            max_score=("RiskScore", "max"),
            last_invoice_date=("InvoiceDate", "max"),
        )
        .reset_index()
        .rename(columns={"Vendor": "vendor"})
    )

    vendors = []
    for _, row in group.iterrows():
        total = int(row["total_invoices"])
        risky = int(row["risky_invoices"])
        risky_pct = (risky / total * 100.0) if total else 0.0
        avg_score = float(row["avg_score"])
        max_score = float(row["max_score"])

        if risky_pct >= 40 or max_score >= 0.9:
            tier = "HIGH"
        elif risky_pct >= 15 or max_score >= 0.7:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        last_date = row["last_invoice_date"]
        if isinstance(last_date, pd.Timestamp):
            last_date_str = last_date.strftime("%Y-%m-%d")
        else:
            last_date_str = str(last_date)

        vendors.append(
            {
                "vendor": str(row["vendor"]) if row["vendor"] is not None else "(Unknown)",
                "total_invoices": total,
                "total_amount": float(row["total_amount"]),
                "risky_invoices": risky,
                "high_risk_invoices": int(row["high_risk_invoices"]),
                "risky_percentage": risky_pct,
                "avg_score": avg_score,
                "max_score": max_score,
                "last_invoice_date": last_date_str,
                "risk_tier": tier,
            }
        )

    vendors_sorted = sorted(
        vendors,
        key=lambda v: ({"HIGH": 3, "MEDIUM": 2, "LOW": 1}[v["risk_tier"]], v["total_amount"]),
        reverse=True,
    )

    return jsonify({"vendors": vendors_sorted}), 200


@app.route("/api/ap_control_overview", methods=["GET"])
def ap_control_overview():
    global CURRENT_DF

    if CURRENT_DF is None:
        return jsonify(
            {"error": "No invoices processed yet. Upload a file on Tab 1 first."}
        ), 400

    df = CURRENT_DF.copy()

    if "InvoiceDate" in df.columns:
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
        df["month"] = df["InvoiceDate"].dt.to_period("M").astype(str)
    else:
        df["month"] = "Unknown"

    df["Amount"] = pd.to_numeric(df.get("Amount", 0.0), errors="coerce").fillna(0.0)
    df["RiskScore"] = pd.to_numeric(df.get("RiskScore", 0.0), errors="coerce").fillna(0.0)

    total_invoices = int(len(df))
    risky_df = df[df["RiskLevel"].isin(["HIGH", "MEDIUM"])].copy()
    high_df = df[df["RiskLevel"] == "HIGH"].copy()

    summary = {
        "total_invoices": total_invoices,
        "risky_invoices": int(len(risky_df)),
        "high_risk_invoices": int(len(high_df)),
        "total_amount": float(df["Amount"].sum()),
        "total_risk_amount": float(risky_df["Amount"].sum()),
        "high_risk_amount": float(high_df["Amount"].sum()),
    }

    risk_distribution = {
        "HIGH": int((df["RiskLevel"] == "HIGH").sum()),
        "MEDIUM": int((df["RiskLevel"] == "MEDIUM").sum()),
        "LOW": int((df["RiskLevel"] == "LOW").sum()),
        "UNKNOWN": int((df["RiskLevel"] == "UNKNOWN").sum()),
    }

    monthly = (
        df.groupby("month")
        .agg(
            invoices=("InvoiceID", "count"),
            total_amount=("Amount", "sum"),
            risky_invoices=("RiskLevel", lambda s: s.isin(["HIGH", "MEDIUM"]).sum()),
            high_risk_invoices=("RiskLevel", lambda s: (s == "HIGH").sum()),
        )
        .reset_index()
        .sort_values("month")
    )

    monthly_trend = [
        {
            "month": row["month"],
            "invoices": int(row["invoices"]),
            "total_amount": float(row["total_amount"]),
            "risky_invoices": int(row["risky_invoices"]),
            "high_risk_invoices": int(row["high_risk_invoices"]),
        }
        for _, row in monthly.iterrows()
    ]

    top_risky_vendors = []
    if "Vendor" in df.columns and not risky_df.empty:
        risky_by_vendor = (
            risky_df.groupby("Vendor", dropna=False)
            .agg(
                risky_amount=("Amount", "sum"),
                risky_count=("InvoiceID", "count"),
                max_score=("RiskScore", "max"),
            )
            .reset_index()
            .rename(columns={"Vendor": "vendor"})
            .sort_values("risky_amount", ascending=False)
            .head(10)
        )

        for _, row in risky_by_vendor.iterrows():
            top_risky_vendors.append(
                {
                    "vendor": str(row["vendor"]) if row["vendor"] is not None else "(Unknown)",
                    "risky_amount": float(row["risky_amount"]),
                    "risky_count": int(row["risky_count"]),
                    "max_score": float(row["max_score"]),
                }
            )

    return jsonify(
        {
            "summary": summary,
            "risk_distribution": risk_distribution,
            "monthly_trend": monthly_trend,
            "top_risky_vendors": top_risky_vendors,
        }
    ), 200


@app.route("/api/ap_control_charts", methods=["GET"])
def ap_control_charts():
    """
    Returns extra breakdown data for Plotly charts on the AP Control tab.
    Called by static/js/ap_control_charts.js alongside /api/ap_control_overview.
    """
    global CURRENT_DF

    if CURRENT_DF is None:
        return jsonify(
            {"error": "No invoices processed yet. Upload a file on Tab 1 first."}
        ), 400

    df = CURRENT_DF.copy()
    df["Amount"]    = pd.to_numeric(df.get("Amount",    0.0), errors="coerce").fillna(0.0)
    df["RiskScore"] = pd.to_numeric(df.get("RiskScore", 0.0), errors="coerce").fillna(0.0)

    # ------------------------------------------------------------------
    # 1. Invoice-Type breakdown  → Grouped bar chart
    # ------------------------------------------------------------------
    invoice_type_breakdown = []
    if "InvoiceType" in df.columns:
        it_grp = (
            df.groupby(["InvoiceType", "RiskLevel"], dropna=False)
            .size()
            .reset_index(name="count")
        )
        invoice_type_breakdown = it_grp.to_dict(orient="records")

    # ------------------------------------------------------------------
    # 2. Cost-Center breakdown  → Stacked bar chart
    # ------------------------------------------------------------------
    cost_center_breakdown = []
    if "CostCenter" in df.columns:
        cc_grp = (
            df.groupby(["CostCenter", "RiskLevel"], dropna=False)
            .agg(count=("InvoiceID" if "InvoiceID" in df.columns else df.columns[0], "count"))
            .reset_index()
        )
        cost_center_breakdown = cc_grp.to_dict(orient="records")

    # ------------------------------------------------------------------
    # 3. Risk Score distribution  → Histogram (raw scores)
    # ------------------------------------------------------------------
    risk_scores = (
        df["RiskScore"]
        .dropna()
        .round(3)
        .tolist()
    )

    # ------------------------------------------------------------------
    # 4. Payment-Status breakdown  → Grouped bar chart
    # ------------------------------------------------------------------
    payment_status_breakdown = []
    if "PaymentStatus" in df.columns:
        ps_grp = (
            df.groupby(["PaymentStatus", "RiskLevel"], dropna=False)
            .agg(
                count=("Amount", "count"),
                total_amount=("Amount", "sum"),
            )
            .reset_index()
        )
        payment_status_breakdown = ps_grp.to_dict(orient="records")

    # ------------------------------------------------------------------
    # 5. Vendor-State risk summary  → Horizontal bar chart
    # ------------------------------------------------------------------
    vendor_state_breakdown = []
    if "VendorState" in df.columns:
        vs_grp = (
            df.groupby("VendorState", dropna=False)
            .agg(
                total=("Amount", "count"),
                risky=("RiskLevel", lambda s: s.isin(["HIGH", "MEDIUM"]).sum()),
                high_risk=("RiskLevel", lambda s: (s == "HIGH").sum()),
                total_amount=("Amount", "sum"),
                risky_amount=("Amount", lambda s: s[df.loc[s.index, "RiskLevel"].isin(["HIGH", "MEDIUM"])].sum()),
            )
            .reset_index()
            .sort_values("risky", ascending=False)
        )
        vendor_state_breakdown = vs_grp.to_dict(orient="records")

    # ------------------------------------------------------------------
    # 6. Monthly risky-amount split  → Stacked area chart
    #    (safe_amount = total_amount - risky_amount per month)
    # ------------------------------------------------------------------
    monthly_amount_split = []
    if "InvoiceDate" in df.columns:
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
        df["_month"] = df["InvoiceDate"].dt.to_period("M").astype(str)

        risky_mask = df["RiskLevel"].isin(["HIGH", "MEDIUM"])

        m_total = df.groupby("_month")["Amount"].sum().reset_index(name="total_amount")
        m_risky = df[risky_mask].groupby("_month")["Amount"].sum().reset_index(name="risky_amount")
        m_high  = df[df["RiskLevel"] == "HIGH"].groupby("_month")["Amount"].sum().reset_index(name="high_amount")

        m_merged = (
            m_total
            .merge(m_risky, on="_month", how="left")
            .merge(m_high,  on="_month", how="left")
            .fillna(0)
            .sort_values("_month")
        )
        m_merged["safe_amount"] = m_merged["total_amount"] - m_merged["risky_amount"]

        monthly_amount_split = [
            {
                "month":        row["_month"],
                "total_amount": float(row["total_amount"]),
                "risky_amount": float(row["risky_amount"]),
                "high_amount":  float(row["high_amount"]),
                "safe_amount":  float(row["safe_amount"]),
            }
            for _, row in m_merged.iterrows()
        ]

    return jsonify(
        {
            "invoice_type_breakdown":   invoice_type_breakdown,
            "cost_center_breakdown":    cost_center_breakdown,
            "risk_scores":              risk_scores,
            "payment_status_breakdown": payment_status_breakdown,
            "vendor_state_breakdown":   vendor_state_breakdown,
            "monthly_amount_split":     monthly_amount_split,
        }
    ), 200


@app.route("/api/what_if_simulator", methods=["POST"])
def what_if_simulator():
    global CURRENT_DF

    if CURRENT_DF is None:
        return jsonify(
            {"error": "No invoices processed yet. Upload a file on Tab 1 first."}
        ), 400

    df = CURRENT_DF.copy()
    df["Amount"] = pd.to_numeric(df.get("Amount", 0.0), errors="coerce").fillna(0.0)

    if "VendorAgeDays" not in df.columns:
        df["VendorAgeDays"] = 9999

    if "PONumber" not in df.columns:
        df["PONumber"] = None

    data = request.get_json(silent=True) or {}

    min_amount_dual_approval = float(data.get("min_amount_dual_approval") or 0)
    block_new_vendor_days = int(data.get("block_new_vendor_days") or 0)
    block_no_po_min_amount = float(data.get("block_no_po_min_amount") or 0)

    risky_df = df[df["RiskLevel"].isin(["HIGH", "MEDIUM"])].copy()

    base_risky_count = int(len(risky_df))
    base_risk_amount = float(risky_df["Amount"].sum())

    cond_dual = pd.Series(False, index=df.index)
    cond_new_vendor = pd.Series(False, index=df.index)
    cond_no_po = pd.Series(False, index=df.index)

    if min_amount_dual_approval > 0:
        cond_dual = df["Amount"] >= min_amount_dual_approval

    if block_new_vendor_days > 0:
        cond_new_vendor = (
            pd.to_numeric(df["VendorAgeDays"], errors="coerce").fillna(9999)
            <= block_new_vendor_days
        )

    if block_no_po_min_amount > 0:
        cond_no_po = (
            (df["Amount"] >= block_no_po_min_amount)
            & (df["PONumber"].isna() | df["PONumber"].astype(str).str.strip().eq(""))
        )

    combined_policy = cond_dual | cond_new_vendor | cond_no_po

    blocked_risky = risky_df[combined_policy.loc[risky_df.index]]
    blocked_risky_count = int(len(blocked_risky))
    blocked_risk_amount = float(blocked_risky["Amount"].sum())

    new_risky_count = base_risky_count - blocked_risky_count
    new_risk_amount = base_risk_amount - blocked_risk_amount

    response = {
        "base": {
            "risky_invoices": base_risky_count,
            "risky_amount": base_risk_amount,
        },
        "impact": {
            "blocked_risky_invoices": blocked_risky_count,
            "blocked_risk_amount": blocked_risk_amount,
            "new_risky_invoices": new_risky_count,
            "new_risk_amount": new_risk_amount,
            "dual_approval_hits": int(cond_dual.sum()),
            "new_vendor_hits": int(cond_new_vendor.sum()),
            "no_po_hits": int(cond_no_po.sum()),
            "total_policy_hits": int(combined_policy.sum()),
        },
    }

    return jsonify(response), 200


@app.route("/api/fraud_playbook", methods=["GET"])
def fraud_playbook():
    global CURRENT_DF

    if CURRENT_DF is None:
        return jsonify(
            {"error": "No invoices processed yet. Upload a file on Tab 1 first."}
        ), 400

    df = CURRENT_DF.copy()
    df["Amount"] = pd.to_numeric(df.get("Amount", 0.0), errors="coerce").fillna(0.0)
    df["RiskScore"] = pd.to_numeric(df.get("RiskScore", 0.0), errors="coerce").fillna(0.0)

    if "VendorAgeDays" not in df.columns:
        df["VendorAgeDays"] = 9999
    if "PONumber" not in df.columns:
        df["PONumber"] = None

    risky_df = df[df["RiskLevel"].isin(["HIGH", "MEDIUM"])].copy()
    high_df = df[df["RiskLevel"] == "HIGH"].copy()

    risky_count = int(len(risky_df))
    high_count = int(len(high_df))
    risky_amount = float(risky_df["Amount"].sum())
    high_amount = float(high_df["Amount"].sum())

    bank_change_count = 0
    if "BankChangeFlag" in df.columns:
        bank_change_count = int(
            df["BankChangeFlag"].astype(str).str.upper().eq("Y").sum()
        )

    new_vendor_count = int(
        (pd.to_numeric(df["VendorAgeDays"], errors="coerce").fillna(9999) <= 30).sum()
    )

    no_po_count = int(
        (df["PONumber"].isna() | df["PONumber"].astype(str).str.strip().eq("")).sum()
    )

    near_threshold_count = int(((df["Amount"] >= 95000) & (df["Amount"] < 100000)).sum())
    above_threshold_count = int((df["Amount"] >= 100000).sum())

    recommendations = []

    if above_threshold_count > 0:
        recommendations.append(
            {
                "title": "Strengthen dual approval for high-value invoices",
                "priority": "HIGH",
                "impact": "HIGH",
                "reason": f"{above_threshold_count} invoices are at or above ₹100000 and should use stricter approval routing.",
                "action": "Set mandatory dual approval above ₹100000 and require approver escalation for unusual vendors.",
            }
        )

    if new_vendor_count > 0:
        recommendations.append(
            {
                "title": "Apply enhanced review to new vendors",
                "priority": "HIGH",
                "impact": "HIGH",
                "reason": f"{new_vendor_count} invoices are linked to vendors aged 30 days or less.",
                "action": "Block or review invoices from new vendors until onboarding, GST, and bank verification are confirmed.",
            }
        )

    if bank_change_count > 0:
        recommendations.append(
            {
                "title": "Enforce dual verification for bank changes",
                "priority": "HIGH",
                "impact": "HIGH",
                "reason": f"{bank_change_count} invoices involve bank change signals, which are sensitive fraud indicators.",
                "action": "Require maker-checker validation and out-of-band confirmation for all vendor bank account changes.",
            }
        )

    if no_po_count > 0:
        recommendations.append(
            {
                "title": "Tighten no-PO invoice controls",
                "priority": "MEDIUM",
                "impact": "HIGH",
                "reason": f"{no_po_count} invoices appear to have missing PO information.",
                "action": "Require exception approval and reason code for no-PO invoices, especially above policy threshold.",
            }
        )

    if near_threshold_count > 0:
        recommendations.append(
            {
                "title": "Review split-value invoices near approval limit",
                "priority": "MEDIUM",
                "impact": "MEDIUM",
                "reason": f"{near_threshold_count} invoices are close to the ₹100000 approval boundary.",
                "action": "Create an alert for invoices between ₹95000 and ₹99999 to detect possible approval circumvention.",
            }
        )

    if risky_count > 0:
        recommendations.append(
            {
                "title": "Create daily risky invoice review queue",
                "priority": "MEDIUM",
                "impact": "MEDIUM",
                "reason": f"{risky_count} invoices are currently rated HIGH or MEDIUM risk.",
                "action": "Route risky invoices into a daily AP control queue with owner, aging, and disposition tracking.",
            }
        )

    watchlist_vendors = []
    if "Vendor" in risky_df.columns and not risky_df.empty:
        vendor_risk = (
            risky_df.groupby("Vendor", dropna=False)
            .agg(
                risky_invoices=("InvoiceID", "count"),
                risky_amount=("Amount", "sum"),
                max_score=("RiskScore", "max"),
            )
            .reset_index()
            .sort_values(["risky_amount", "risky_invoices"], ascending=[False, False])
            .head(5)
        )

        for _, row in vendor_risk.iterrows():
            watchlist_vendors.append(
                {
                    "vendor": str(row["Vendor"]) if row["Vendor"] is not None else "(Unknown)",
                    "risky_invoices": int(row["risky_invoices"]),
                    "risky_amount": float(row["risky_amount"]),
                    "max_score": float(row["max_score"]),
                }
            )

    return jsonify(
        {
            "headline_risk": {
                "risky_invoices": risky_count,
                "high_risk_invoices": high_count,
                "risky_amount": risky_amount,
                "high_risk_amount": high_amount,
                "bank_change_count": bank_change_count,
                "new_vendor_count": new_vendor_count,
                "no_po_count": no_po_count,
                "near_threshold_count": near_threshold_count,
            },
            "top_recommendations": recommendations,
            "quick_wins": [
                "Enable dual approval for invoices above ₹100000.",
                "Apply 30-day hold/review for new vendors.",
                "Require dual verification for vendor bank changes.",
                "Alert on invoices just below approval thresholds.",
                "Track top risky vendors weekly.",
            ],
            "watchlist_vendors": watchlist_vendors,
            "executive_summary": (
                f"The current invoice population contains {risky_count} risky invoices "
                f"with total risky exposure of ₹{risky_amount:,.2f}. "
                f"Priority controls should focus on high-value approvals, new-vendor review, "
                f"bank-change verification, and targeted monitoring of risky vendors."
            ),
        }
    ), 200


# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------

if __name__ == "__main__":
    LOGGER.info("Starting SAP AI FraudGuard backend")
    init_user_db()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
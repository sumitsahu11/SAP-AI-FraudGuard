import re
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
_model = SentenceTransformer(MODEL_NAME)

def _clean(text):
    return " ".join(str(text).replace("\n", " ").split()).strip()

def _extract_direct_answer(query, text):
    q = query.lower()
    t = _clean(text)

    patterns = []

    if "tax procedure" in q:
        patterns = [
            r"tax procedure(?:.*?)(TAX[A-Z0-9]+)",
            r"\b(TAXINN|TAXVAT|TAX[A-Z0-9]+)\b",
        ]

    elif "pricing procedure" in q:
        patterns = [
            r"pricing procedure(?:.*?)(Z[A-Z0-9]+)",
            r"\b(ZEXP\d+|Z[A-Z0-9]+)\b",
        ]

    elif "approval threshold" in q or "high value invoice approval threshold" in q:
        patterns = [
            r"(INR\s?[0-9,]+)",
            r"(USD\s?[0-9,]+)",
        ]

    elif "vendor account groups" in q or "account groups" in q:
        domestic = re.search(r"domestic.*?(Z[A-Z0-9]+)", t, re.IGNORECASE)
        import_ = re.search(r"import.*?(Z[A-Z0-9]+)", t, re.IGNORECASE)
        if domestic and import_:
            return f"Domestic: {domestic.group(1)}; Import: {import_.group(1)}"

    elif "tolerance key" in q:
        patterns = [
            r"tolerance key\s+([A-Z0-9]+).*?([0-9]+ ?percent)",
            r"([A-Z0-9]+).*?([0-9]+ ?percent)",
        ]

    elif "payment terms" in q:
        patterns = [
            r"payment terms\s+([A-Z0-9]+)",
            r"\b(Z[0-9]{3})\b",
        ]

    elif "obyc" in q or "gr/ir" in q or "inventory posting" in q:
        bsx = re.search(r"\bBSX\b", t)
        wrx = re.search(r"\bWRX\b", t)
        if bsx and wrx:
            return "BSX for inventory posting; WRX for GR/IR clearing"

    elif "three-way match" in q:
        amt = re.search(r"(INR\s?[0-9,]+)", t, re.IGNORECASE)
        if amt:
            return f"Yes, above {amt.group(1)}"

    elif "duplicate invoice" in q and ("resolution" in q or "prevention" in q or "lesson" in q):
        if "error instead of warning" in t.lower():
            return "Duplicate invoice control was strengthened by changing the message to error instead of warning."
        if "duplicate invoice prevention improved" in t.lower():
            return "Duplicate invoice prevention improved after making the duplicate check error-based rather than warning-based."

    for p in patterns:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            if len(m.groups()) == 1:
                return m.group(1).strip()
            if len(m.groups()) == 2:
                return " | ".join([g.strip() for g in m.groups() if g])

    return None

def _fallback_answer(text):
    text = _clean(text)
    if len(text) <= 220:
        return text
    return text[:220].rsplit(" ", 1)[0] + "..."


def search_docs(query, index, chunks, sources, top_k=8):
    if index is None or not chunks:
        return {
            "answer": "No indexed documents available.",
            "matches": []
        }
    q_emb = _model.encode(
        [query],
        normalize_embeddings=True,
        show_progress_bar=False
    ).astype("float32")

    scores, ids = index.search(q_emb, top_k)

    matches = []
    seen = set()

    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue

        score = float(score)
        if score < 0.20:
            continue

        src = sources[idx]
        key = (src["file_name"], src["location"], src.get("chunk_id"))

        if key in seen:
            continue
        seen.add(key)

        matches.append({
            "score": score,
            "text": chunks[idx],
            "source": src
        })

    if not matches:
        return {
            "answer": "No strong answer found in the uploaded documents. Try asking with exact SAP terms like tax procedure, pricing procedure, company code, vendor group, MIRO, OBYC, or tolerance key.",
            "matches": []
        }

    top = matches[0]
    exact_answer = _extract_direct_answer(query, top["text"])

    if not exact_answer:
        for m in matches[1:4]:
            exact_answer = _extract_direct_answer(query, m["text"])
            if exact_answer:
                top = m
                break

    final_answer = exact_answer if exact_answer else _fallback_answer(top["text"])

    source_line = f"Source: {top['source']['file_name']} | {top['source']['location']}"

    return {
        "answer": final_answer,
        "source_line": source_line,
        "matches": matches[:5]
    }
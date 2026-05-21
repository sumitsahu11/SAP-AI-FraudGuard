from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd
from numpy.linalg import norm
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL_NAME, RAG_TOP_K
from src.utils import LOGGER


@dataclass
class SimilarInvoice:
    invoice_id: str
    vendor: str
    amount: float
    invoice_date: str
    risk_level: str
    risk_reason: str
    similarity: float


class RAGEngine:
    """
    Lightweight in-memory RAG engine for invoices.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        LOGGER.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self._embeddings: Optional[np.ndarray] = None
        self._texts: List[str] = []
        self._invoice_ids: List[str] = []
        self._meta: List[Dict[str, Any]] = []

    @staticmethod
    def _row_to_text(row: pd.Series) -> str:
        return (
            f"Invoice {row['InvoiceNumber']} (ID {row['InvoiceID']}) from vendor "
            f"{row['Vendor']} on {row['InvoiceDate'].date() if pd.notna(row['InvoiceDate']) else 'unknown date'} "
            f"for amount {row['Amount']} {row.get('Currency', 'N/A')} "
            f"with PO {row.get('PONumber', 'N/A')}. "
            f"Risk level: {row.get('RiskLevel', 'UNKNOWN')}. "
            f"Reason: {row.get('RiskReason', 'No reason specified')}."
        )

    def build_index(self, df: pd.DataFrame) -> None:
        """
        Build embeddings for all invoices in df and store them in memory.
        """
        LOGGER.info("Building RAG index for invoices")

        texts = []
        invoice_ids = []
        meta = []

        for _, row in df.iterrows():
            texts.append(self._row_to_text(row))
            invoice_ids.append(str(row["InvoiceID"]))
            meta.append(
                {
                    "Vendor": row["Vendor"],
                    "InvoiceNumber": row["InvoiceNumber"],
                    "InvoiceDate": row["InvoiceDate"],
                    "Amount": float(row["Amount"]),
                    "Currency": row.get("Currency", ""),
                    "RiskLevel": row.get("RiskLevel", ""),
                    "RiskReason": row.get("RiskReason", ""),
                }
            )

        embeddings = self.model.encode(texts, show_progress_bar=False)

        self._texts = texts
        self._invoice_ids = invoice_ids
        self._meta = meta
        self._embeddings = np.array(embeddings)

        LOGGER.info(f"RAG index built for {len(self._texts)} invoices")

    def _cosine_similarities(self, query_vector: np.ndarray) -> np.ndarray:
        if self._embeddings is None or len(self._embeddings) == 0:
            return np.array([])

        # Cosine similarity: (A · B) / (||A|| * ||B||)
        dot = self._embeddings @ query_vector
        norm_emb = norm(self._embeddings, axis=1) * norm(query_vector)
        # Avoid division by zero
        norm_emb = np.where(norm_emb == 0, 1e-10, norm_emb)
        return dot / norm_emb

    def find_similar_invoices(
        self, query: str, top_k: int = RAG_TOP_K, focus_invoice_id: Optional[str] = None
    ) -> List[SimilarInvoice]:
        """
        Return top_k similar invoices to the query (optionally filtered by vendor of a given invoice).
        """
        if self._embeddings is None or len(self._embeddings) == 0:
            LOGGER.warning("RAG index is empty")
            return []

        query_vec = self.model.encode([query])[0]
        sims = self._cosine_similarities(query_vec)

        indices = np.argsort(-sims)  # descending

        results = []
        for idx in indices[:top_k * 3]:  # gather more and then filter
            inv_id = self._invoice_ids[idx]
            m = self._meta[idx]
            sim = float(sims[idx])

            if focus_invoice_id is not None:
                # filter by same vendor as focus invoice
                focus_vendor = self._get_vendor_by_invoice_id(focus_invoice_id)
                if focus_vendor and m["Vendor"] != focus_vendor:
                    continue

            results.append(
                SimilarInvoice(
                    invoice_id=inv_id,
                    vendor=m["Vendor"],
                    amount=m["Amount"],
                    invoice_date=str(m["InvoiceDate"].date())
                    if m["InvoiceDate"] is not None
                    else "unknown",
                    risk_level=m["RiskLevel"],
                    risk_reason=m["RiskReason"],
                    similarity=sim,
                )
            )

            if len(results) >= top_k:
                break

        return results

    def _get_vendor_by_invoice_id(self, invoice_id: str) -> Optional[str]:
        for inv_id, meta in zip(self._invoice_ids, self._meta):
            if inv_id == invoice_id:
                return meta["Vendor"]
        return None

    def explain_invoice(
        self, df: pd.DataFrame, invoice_id: str, user_question: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build a simple natural-language explanation for a given invoice,
        using its risk metadata and similar invoices (RAG-style).
        """
        try:
            row = df[df["InvoiceID"] == invoice_id].iloc[0]
        except IndexError:
            return {"error": f"InvoiceID {invoice_id} not found."}

        base_question = (
            user_question
            if user_question
            else "Why is this invoice marked as risky and what similar invoices exist?"
        )

        similar_invs = self.find_similar_invoices(
            query=base_question, top_k=RAG_TOP_K, focus_invoice_id=invoice_id
        )

        explanation_lines = []

        explanation_lines.append(
            f"Invoice {row['InvoiceNumber']} from vendor {row['Vendor']} "
            f"dated {row['InvoiceDate'].date() if pd.notna(row['InvoiceDate']) else 'unknown date'} "
            f"for amount {row['Amount']} {row.get('Currency', 'N/A')} "
            f"is marked as {row.get('RiskLevel', 'UNKNOWN')} risk."
        )

        explanation_lines.append(f"Reason(s): {row.get('RiskReason', 'No reason specified')}.")

        if similar_invs:
            explanation_lines.append(
                f"We also found {len(similar_invs)} similar invoice(s) for this vendor:"
            )
            for sim in similar_invs:
                explanation_lines.append(
                    f"- InvoiceID {sim.invoice_id} on {sim.invoice_date} "
                    f"for {sim.amount} (risk: {sim.risk_level}, "
                    f"reason: {sim.risk_reason}) [similarity={sim.similarity:.2f}]"
                )
        else:
            explanation_lines.append(
                "No very similar past invoices were found in the current dataset."
            )

        return {
            "invoice_id": invoice_id,
            "user_question": base_question,
            "answer": "\n".join(explanation_lines),
            "similar_invoices": [sim.__dict__ for sim in similar_invs],
        }
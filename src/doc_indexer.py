import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from src.doc_extractors import extract_file

MODEL_NAME = "all-MiniLM-L6-v2"
_model = SentenceTransformer(MODEL_NAME)

def chunk_text(text, chunk_size=700, overlap=120):
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start += (chunk_size - overlap)

    return chunks

def build_doc_index(files):
    chunk_records = []

    for uploaded_file in files:
        extracted_docs = extract_file(uploaded_file)

        for doc in extracted_docs:
            text = doc["text"]
            source = doc["source"]

            chunks = chunk_text(text)
            for i, chunk in enumerate(chunks, start=1):
                chunk_records.append({
                    "text": chunk,
                    "source": {
                        "file_name": source["file_name"],
                        "location": source["location"],
                        "doc_type": source["doc_type"],
                        "chunk_id": i
                    }
                })

    if not chunk_records:
        raise ValueError("No readable text found in uploaded files.")

    chunk_texts = [x["text"] for x in chunk_records]
    chunk_sources = [x["source"] for x in chunk_records]

    embeddings = _model.encode(
        chunk_texts,
        normalize_embeddings=True,
        show_progress_bar=False
    ).astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    return index, chunk_texts, chunk_sources
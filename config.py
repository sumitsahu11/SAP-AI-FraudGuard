# config.py

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Flask config
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = True
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

# Allowed upload extensions
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

# Risk scoring thresholds
RISK_SCORE_HIGH_THRESHOLD = 0.7
RISK_SCORE_MEDIUM_THRESHOLD = 0.4

# Isolation Forest config
IFOREST_CONTAMINATION = 0.02  # expected proportion of anomalies

# RAG / embeddings
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
RAG_TOP_K = 5

# Future S/4HANA config placeholders (for later)
SAP_S4_BASE_URL = "https://your-s4hana-host.example.com"
SAP_S4_API_KEY = os.getenv("SAP_S4_API_KEY", "")
from pathlib import Path
from dotenv import load_dotenv
import certifi
import os

load_dotenv()
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Python installations on macOS do not always inherit the system CA store.
# Point all Neo4j clients (including LlamaIndex's vector store) at certifi's
# current CA bundle while preserving strict TLS verification for +s URIs.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", "")
NEBIUS_BASE_URL = os.getenv(
    "NEBIUS_BASE_URL",
    "https://api.tokenfactory.nebius.com/v1",
)
NEBIUS_MODEL = os.getenv(
    "NEBIUS_MODEL",
    "Qwen/Qwen3-30B-A3B-Instruct-2507",
)

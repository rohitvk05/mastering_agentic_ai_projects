from llama_index.core import SimpleDirectoryReader
from config import DATA_DIR


CORPUS_FOLDERS = (
    "people",
    "projects",
    "meetings",
    "decisions",
    "technical_docs",
)


def corpus_files():
    """Return canonical corpus files, excluding manifests and data README files."""
    extensions = {".md", ".txt", ".pdf"}
    return sorted(
        path
        for folder in CORPUS_FOLDERS
        for path in (DATA_DIR / folder).iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )


def load_documents():
    return SimpleDirectoryReader(
        input_files=[str(path) for path in corpus_files()],
    ).load_data()

if __name__ == "__main__":
    docs = load_documents()
    print(f"Loaded {len(docs)} documents")

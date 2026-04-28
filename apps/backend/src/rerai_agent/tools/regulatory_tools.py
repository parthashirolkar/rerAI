import os
import re
import unicodedata
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rerai_agent.tools.config import CHROMA_DATABASE, CHROMA_TENANT, get_embeddings

PDF_DIR = os.environ.get(
    "UDCPR_PDF_DIR",
    str(Path(__file__).resolve().parents[4] / "data" / "pdfs"),
)

_vector_store: Chroma | None = None


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    embeddings = get_embeddings()

    # Connect to ChromaDB Cloud
    chroma_api_key = os.environ.get("CHROMA_API_KEY")
    _vector_store = Chroma(
        collection_name="udcpr",
        embedding_function=embeddings,
        tenant=CHROMA_TENANT,
        database=CHROMA_DATABASE,
        chroma_cloud_api_key=chroma_api_key,
    )

    # Check if collection is empty and ingest if needed
    try:
        count = _vector_store._collection.count()
        if count == 0:
            print("ChromaDB Cloud collection is empty. Ingesting from PDFs...")
            return _ingest_pdfs(embeddings)
    except Exception:
        # Collection might not exist yet
        pass

    return _vector_store


def _ingest_pdfs(embeddings) -> Chroma:
    from pypdf import PdfReader

    pdf_dir = os.path.abspath(PDF_DIR)
    if not os.path.exists(pdf_dir) or not os.listdir(pdf_dir):
        raise FileNotFoundError(
            f"No PDFs found in {pdf_dir}. Place UDCPR PDFs there first."
        )

    all_docs: list[Document] = []
    for filename in sorted(os.listdir(pdf_dir)):
        if not filename.lower().endswith(".pdf"):
            continue
        filepath = os.path.join(pdf_dir, filename)
        reader = PdfReader(filepath)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                cleaned = _clean_text(text)
                if len(cleaned) > 20:
                    all_docs.append(
                        Document(
                            page_content=cleaned,
                            metadata={"source": filename, "page": i + 1},
                        )
                    )

    if not all_docs:
        raise ValueError("No extractable text found in PDFs.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(all_docs)

    valid_chunks = [c for c in chunks if c.page_content.strip()]

    # Add to existing ChromaDB Cloud collection
    batch_size = 50
    for i in range(0, len(valid_chunks), batch_size):
        batch = valid_chunks[i : i + batch_size]
        _vector_store.add_documents(documents=batch)

    return _vector_store


def init_udcpr_store() -> int:
    """Initialize the UDCPR vector store. Returns number of chunks ingested."""
    vs = _get_vector_store()
    return vs._collection.count()


@tool
async def query_udcpr(question: str, n_results: int = 3) -> str:
    """Query the Maharashtra UDCPR building regulations using semantic search.

    Searches the UDCPR corpus (updated to Jan 2025) for clauses relevant
    to the question. Returns matching regulation excerpts with page references.

    Use this for questions about FSI, setbacks, parking, fire safety, height
    restrictions, ground coverage, or any building regulation in Maharashtra.

    Args:
        question: Natural language question about building regulations
        n_results: Number of relevant chunks to return (default 3)
    """
    vs = _get_vector_store()
    results = vs.similarity_search_with_score(question, k=n_results)

    if not results:
        return "No relevant regulations found for this query."

    output_parts = []
    for doc, score in results:
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "?")
        content = doc.page_content
        output_parts.append(
            f"[{source}, page {page}] (relevance: {1 - score:.3f})\n{content}"
        )

    return "\n\n---\n\n".join(output_parts)

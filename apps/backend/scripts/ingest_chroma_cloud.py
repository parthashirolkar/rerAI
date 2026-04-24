#!/usr/bin/env python3
"""Ingest UDCPR PDFs into ChromaDB Cloud using OpenRouter (FREE NVIDIA embeddings)."""

import os
import re
import sys
import unicodedata

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from tenacity import retry, stop_after_attempt, wait_exponential

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rerai_agent.env import load_project_env
from rerai_agent.tools.config import EMBEDDING_MODEL, OpenRouterEmbeddings

load_project_env()

PDF_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "pdfs")
CHROMA_TENANT = os.environ.get("CHROMA_TENANT")
CHROMA_DATABASE = os.environ.get("CHROMA_DATABASE")
CHROMA_API_KEY = os.environ.get("CHROMA_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def ingest_udcpr():
    """Ingest UDCPR PDFs into ChromaDB Cloud using OpenRouter (FREE tier)."""
    pdf_dir = os.path.abspath(PDF_DIR)

    if not os.path.exists(pdf_dir):
        raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")

    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        raise FileNotFoundError(f"No PDFs found in {pdf_dir}")

    print(f"Found {len(pdf_files)} PDF(s) in {pdf_dir}")

    print(f"Using OpenRouter with {EMBEDDING_MODEL} (FREE tier)...")
    embeddings = OpenRouterEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        check_embedding_ctx_length=False,
    )
    print("✓ Embeddings initialized (2048-dim)")

    # Connect to ChromaDB Cloud
    print(f"Connecting to ChromaDB Cloud: tenant={CHROMA_TENANT}, db={CHROMA_DATABASE}")
    vector_store = Chroma(
        collection_name="udcpr",
        embedding_function=embeddings,
        tenant=CHROMA_TENANT,
        database=CHROMA_DATABASE,
        chroma_cloud_api_key=CHROMA_API_KEY,
    )

    # Check existing count
    try:
        existing_count = vector_store._collection.count()
        print(f"Existing documents in collection: {existing_count}")
        if existing_count > 0:
            confirm = input("Collection has existing data. Overwrite? [y/N]: ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
            vector_store.delete_collection()
            vector_store = Chroma(
                collection_name="udcpr",
                embedding_function=embeddings,
                tenant=CHROMA_TENANT,
                database=CHROMA_DATABASE,
                chroma_cloud_api_key=CHROMA_API_KEY,
            )
    except Exception as e:
        print(f"Collection may be new: {e}")

    # Extract text from PDFs
    all_docs: list[Document] = []
    for filename in sorted(pdf_files):
        print(f"Processing: {filename}")
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

    print(f"Extracted {len(all_docs)} pages total")

    if not all_docs:
        raise ValueError("No extractable text found in PDFs.")

    # Split into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(all_docs)
    valid_chunks = [c for c in chunks if c.page_content.strip()]

    print(f"Created {len(valid_chunks)} chunks")

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=60), stop=stop_after_attempt(5)
    )
    def add_batch_with_retry(batch):
        """Add documents with exponential backoff retry."""
        return vector_store.add_documents(documents=batch)

    # Ingest in batches with retry
    batch_size = 20
    for i in range(0, len(valid_chunks), batch_size):
        batch = valid_chunks[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(valid_chunks) - 1) // batch_size + 1
        print(f"Ingesting batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        try:
            add_batch_with_retry(batch)
        except Exception as e:
            print(f"  Failed after retries: {e}")
            raise

    final_count = vector_store._collection.count()
    print(f"✓ Ingestion complete! Total documents: {final_count}")
    print(f"\nNote: Using {EMBEDDING_MODEL} (2048-dim) for both ingestion and runtime")


if __name__ == "__main__":
    ingest_udcpr()

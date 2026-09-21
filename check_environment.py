"""Fast local deployment diagnostics without downloading the embedding model."""

from __future__ import annotations

import importlib.util
import json
import argparse
import sqlite3
from pathlib import Path

from ai_service import check_ollama, resolve_model_name
from knowledge_base import KnowledgeBase


ROOT = Path(__file__).resolve().parent
REQUIRED_MODULES = ("streamlit", "chromadb", "langchain_ollama", "langchain_huggingface", "sentence_transformers")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local AI assistant prerequisites.")
    parser.add_argument("--build-index", action="store_true", help="Download the embedding model if needed and build the Chroma index.")
    args = parser.parse_args()
    missing_modules = [module for module in REQUIRED_MODULES if importlib.util.find_spec(module) is None]
    sqlite_available = sqlite3.sqlite_version_info >= (3, 8, 0)
    missing_files = [str(path.relative_to(ROOT)) for path in (ROOT / "data" / "jobs.json", ROOT / "data" / "faq.md") if not path.exists()]
    ollama = check_ollama(model=resolve_model_name())
    result = {
        "dependencies": not missing_modules,
        "data_files": not missing_files,
        "ollama": bool(ollama["available"]),
        "model": bool(ollama["model_ready"]),
        "sqlite": sqlite_available,
        "missing_modules": missing_modules,
        "missing_files": missing_files,
    }
    if args.build_index and all((result["dependencies"], result["data_files"], result["ollama"], result["model"])):
        try:
            knowledge_base = KnowledgeBase()
            knowledge_base.load_data()
            result["index"] = bool(knowledge_base.stats()["index_current"])
        except Exception as error:
            result["index"] = False
            result["index_error"] = str(error)
    else:
        result["index"] = (ROOT / "chroma_db" / ".data_signature").exists()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all((result["dependencies"], result["data_files"], result["ollama"], result["model"], result["sqlite"], result["index"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())

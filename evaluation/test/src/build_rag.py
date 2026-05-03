import json
import os
import sys


MAIN_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../main/src"))
sys.path.append(MAIN_SRC_PATH)

from rag_builder import build_or_update_rag_database, _embed_text


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))


def _resolve_path(project_root: str, path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(project_root, path)


def _load_test_config(project_root: str) -> dict:
    config_path = os.path.join(project_root, "evaluation", "test", "src", "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise ValueError(f"测试配置根节点必须是对象: {config_path}")
    return config


def _require_section(config: dict, section: str) -> dict:
    value = config.get(section)
    if not isinstance(value, dict):
        raise ValueError(f"测试配置缺少对象字段: {section}")
    return value


def _check_pdf_inputs(raw_docs_dir: str) -> None:
    if not os.path.isdir(raw_docs_dir):
        raise FileNotFoundError(f"RAG 原始资料目录不存在: {raw_docs_dir}")
    pdfs = [fn for fn in os.listdir(raw_docs_dir) if fn.lower().endswith(".pdf")]
    if not pdfs:
        raise ValueError(f"RAG 原始资料目录中没有 PDF: {raw_docs_dir}")


def _check_chroma(chroma_db_path: str, embedding_config: dict) -> None:
    import chromadb

    client = chromadb.PersistentClient(path=chroma_db_path)
    collection = client.get_collection("clinical_knowledge")
    count = collection.count()
    if count <= 0:
        raise ValueError("clinical_knowledge collection 中没有 chunk")
    query_embedding = _embed_text("retinal laser photocoagulation", embedding_config)
    result = collection.query(query_embeddings=[query_embedding], n_results=1)
    docs = result.get("documents", [[]])[0]
    if not docs:
        raise ValueError("RAG 自检检索没有返回结果")


def run_build_rag() -> tuple[int, str]:
    project_root = _project_root()
    config = _load_test_config(project_root)
    llm_config = _require_section(config, "llm")
    embedding_config = _require_section(config, "embedding")
    rag_config = _require_section(config, "rag")

    raw_docs_dir = _resolve_path(project_root, rag_config["raw_docs_dir"])
    chroma_db_path = _resolve_path(project_root, rag_config["chroma_db_path"])
    manifest_path = _resolve_path(project_root, rag_config["manifest_path"])
    parsed_cache_dir = _resolve_path(project_root, rag_config["parsed_cache_dir"])
    chunk_cache_dir = _resolve_path(project_root, rag_config["chunk_cache_dir"])

    _check_pdf_inputs(raw_docs_dir)
    status, msg, stats = build_or_update_rag_database(
        raw_docs_dir=raw_docs_dir,
        chroma_db_path=chroma_db_path,
        manifest_path=manifest_path,
        parsed_cache_dir=parsed_cache_dir,
        chunk_cache_dir=chunk_cache_dir,
        llm_config=llm_config,
        embedding_config=embedding_config,
    )
    if status != 1 or stats is None:
        print(msg)
        return 0, msg

    if not os.path.isdir(chroma_db_path):
        raise FileNotFoundError(f"ChromaDB 目录不存在: {chroma_db_path}")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"RAG manifest 不存在: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    for source_file, item in manifest.get("files", {}).items():
        for key in ("sha256", "indexed_at", "chunk_count", "status"):
            if key not in item:
                raise ValueError(f"manifest 文件 {source_file} 缺少字段: {key}")
        if int(item["chunk_count"]) <= 0:
            raise ValueError(f"manifest 文件 {source_file} chunk_count 必须大于 0")

    _check_chroma(chroma_db_path, embedding_config)
    print("RAG 构建成功")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 1, "success"


if __name__ == "__main__":
    run_build_rag()

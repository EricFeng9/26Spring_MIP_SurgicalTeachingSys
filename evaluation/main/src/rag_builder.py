import hashlib
import json
import math
import os
import re
import shutil
import traceback
from datetime import datetime, timezone
from typing import Any

import fitz
import numpy as np
import requests


COLLECTION_NAME = "clinical_knowledge"


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return data


def _save_json(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _api_url(base_url: str, endpoint: str) -> str:
    return base_url.rstrip("/") + "/" + endpoint.lstrip("/")


def _request_embedding(text: str, embedding_config: dict[str, Any]) -> list[float]:
    response = requests.post(
        _api_url(str(embedding_config["base_url"]), "embeddings"),
        headers={
            "Authorization": f"Bearer {embedding_config['api_key']}",
            "Content-Type": "application/json",
        },
        json={"model": embedding_config["model"], "input": text},
        timeout=float(embedding_config.get("timeout_seconds", 60)),
    )
    response.raise_for_status()
    data = response.json()
    try:
        embedding = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"embedding 接口返回格式错误: {data}") from exc
    return [float(v) for v in embedding]


def _local_hash_embedding(text: str, dim: int = 384) -> list[float]:
    tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())
    if not tokens:
        tokens = [text[:64] or "empty"]
    vec = np.zeros(dim, dtype=float)
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        return vec.tolist()
    return (vec / norm).tolist()


def _embed_text(text: str, embedding_config: dict[str, Any]) -> list[float]:
    provider = str(embedding_config.get("provider", "openai_compatible"))
    if provider == "local_hash":
        return _local_hash_embedding(text)
    required = {"base_url", "api_key", "model"}
    missing = [key for key in required if not embedding_config.get(key)]
    if missing:
        raise ValueError(f"embedding_config 缺少必要字段: {', '.join(missing)}")
    return _request_embedding(text, embedding_config)


def _parse_pdf_pages(pdf_path: str) -> list[dict[str, Any]]:
    pages = []
    doc = fitz.open(pdf_path)
    try:
        for idx, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append({"page": idx, "text": text})
    finally:
        doc.close()
    if not pages:
        raise ValueError(f"PDF 未解析出文本: {pdf_path}")
    return pages


def _chunk_page_text(source_file: str, file_sha: str, page: int, text: str) -> list[dict[str, Any]]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    max_chars = 900
    overlap = 120
    chunks = []
    start = 0
    chunk_index = 1
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        body = cleaned[start:end].strip()
        if len(body) >= 80:
            chunk_id = f"{file_sha[:16]}_p{page:03d}_c{chunk_index:03d}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "source_file": source_file,
                    "source_type": "pdf",
                    "page_start": page,
                    "page_end": page,
                    "title": _infer_title(body),
                    "disease_tags": _infer_disease_tags(body),
                    "score_tags": _infer_score_tags(body),
                    "keywords": _infer_keywords(body),
                    "source_quote": body[:240],
                    "summary": body[:300],
                    "text": body,
                }
            )
            chunk_index += 1
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def _infer_title(text: str) -> str:
    candidates = re.split(r"[。.!?？\n]", text)
    for item in candidates:
        item = item.strip()
        if 8 <= len(item) <= 80:
            return item
    return text[:60]


def _infer_disease_tags(text: str) -> list[str]:
    lower = text.lower()
    tags = []
    if "retinal tear" in lower or "torn retina" in lower or "retina tears" in lower:
        tags.extend(["retinal_tear", "视网膜裂孔"])
    if "diabetic retinopathy" in lower:
        tags.extend(["diabetic_retinopathy", "糖尿病视网膜病变"])
    if "retinal vein occlusion" in lower:
        tags.extend(["retinal_vein_occlusion", "视网膜静脉阻塞"])
    if "retina" in lower or "retinal" in lower:
        tags.append("retina")
    return sorted(set(tags))


def _infer_score_tags(text: str) -> list[str]:
    lower = text.lower()
    tags = []
    if any(word in lower for word in ["seal", "scar", "tear", "detach", "fluid"]):
        tags.extend(["position_coverage", "missed_area", "retinal_sealing"])
    if any(word in lower for word in ["laser", "photocoagulation", "burn", "heat"]):
        tags.extend(["laser_photocoagulation", "spatial_parameter_adaptation"])
    if any(word in lower for word in ["side effect", "loss of vision", "macula", "peripheral vision"]):
        tags.extend(["safety_boundary", "risk_explanation"])
    if any(word in lower for word in ["pan-retinal", "scatter", "hundreds"]):
        tags.append("spot_distribution")
    return sorted(set(tags))


def _infer_keywords(text: str) -> list[str]:
    lower = text.lower()
    candidates = [
        "laser",
        "photocoagulation",
        "retina",
        "retinal tear",
        "diabetic retinopathy",
        "scatter laser",
        "pan-retinal",
        "macula",
        "seal",
        "scar",
        "heat",
        "vision loss",
    ]
    return [item for item in candidates if item in lower]


def _metadata_for_chroma(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk["chunk_id"],
        "source_file": chunk["source_file"],
        "source_type": chunk["source_type"],
        "page_start": int(chunk["page_start"]),
        "page_end": int(chunk["page_end"]),
        "title": chunk["title"],
        "disease_tags": ",".join(chunk["disease_tags"]),
        "score_tags": ",".join(chunk["score_tags"]),
        "keywords": ",".join(chunk["keywords"]),
    }


def _load_manifest(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"version": 1, "embedding_model": "", "files": {}}
    return _load_json(path)


def _get_collection(chroma_db_path: str):
    import chromadb

    os.makedirs(chroma_db_path, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_db_path)
    return client.get_or_create_collection(COLLECTION_NAME)


def _delete_source_file(collection, source_file: str) -> None:
    collection.delete(where={"source_file": source_file})


def _add_chunks(collection, chunks: list[dict[str, Any]], embedding_config: dict[str, Any]) -> None:
    if not chunks:
        return
    collection.add(
        ids=[chunk["chunk_id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[_metadata_for_chroma(chunk) for chunk in chunks],
        embeddings=[_embed_text(chunk["text"], embedding_config) for chunk in chunks],
    )


def build_or_update_rag_database(
    raw_docs_dir: str,
    chroma_db_path: str,
    manifest_path: str,
    parsed_cache_dir: str,
    chunk_cache_dir: str,
    llm_config: dict[str, Any],
    embedding_config: dict[str, Any],
) -> tuple[int, str, dict[str, Any] | None]:
    try:
        if not os.path.isdir(raw_docs_dir):
            raise FileNotFoundError(f"RAG 原始资料目录不存在: {raw_docs_dir}")
        pdf_paths = [
            os.path.join(raw_docs_dir, fn)
            for fn in sorted(os.listdir(raw_docs_dir))
            if fn.lower().endswith(".pdf")
        ]
        if not pdf_paths:
            raise ValueError(f"RAG 原始资料目录中没有 PDF: {raw_docs_dir}")

        os.makedirs(parsed_cache_dir, exist_ok=True)
        os.makedirs(chunk_cache_dir, exist_ok=True)
        manifest = _load_manifest(manifest_path)
        manifest.setdefault("version", 1)
        manifest.setdefault("files", {})
        manifest["embedding_model"] = str(embedding_config.get("model", embedding_config.get("provider", "")))

        collection = _get_collection(chroma_db_path)
        current_files = {os.path.basename(path): path for path in pdf_paths}
        indexed_files = 0
        skipped_files = 0
        deleted_files = 0
        chunk_count = 0

        for old_file in sorted(set(manifest["files"].keys()) - set(current_files.keys())):
            _delete_source_file(collection, old_file)
            manifest["files"].pop(old_file, None)
            deleted_files += 1

        for source_file, pdf_path in current_files.items():
            file_sha = _sha256_file(pdf_path)
            entry = manifest["files"].get(source_file)
            if entry and entry.get("sha256") == file_sha and entry.get("status") == "indexed":
                skipped_files += 1
                chunk_count += int(entry.get("chunk_count", 0))
                continue

            _delete_source_file(collection, source_file)
            pages = _parse_pdf_pages(pdf_path)
            parsed_cache_path = os.path.join(parsed_cache_dir, source_file + ".pages.json")
            _save_json(parsed_cache_path, {"source_file": source_file, "sha256": file_sha, "pages": pages})

            chunks = []
            for page_item in pages:
                chunks.extend(_chunk_page_text(source_file, file_sha, int(page_item["page"]), str(page_item["text"])))
            if not chunks:
                raise ValueError(f"PDF 未生成有效 chunk: {pdf_path}")
            chunk_cache_path = os.path.join(chunk_cache_dir, source_file + ".chunks.json")
            _save_json(chunk_cache_path, {"source_file": source_file, "sha256": file_sha, "chunks": chunks})

            _add_chunks(collection, chunks, embedding_config)
            manifest["files"][source_file] = {
                "sha256": file_sha,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "chunk_count": len(chunks),
                "status": "indexed",
            }
            indexed_files += 1
            chunk_count += len(chunks)

        _save_json(manifest_path, manifest)
        stats = {
            "indexed_files": indexed_files,
            "skipped_files": skipped_files,
            "deleted_files": deleted_files,
            "chunk_count": chunk_count,
            "collection": COLLECTION_NAME,
            "chroma_db_path": chroma_db_path,
            "manifest_path": manifest_path,
        }
        return 1, "success", stats
    except Exception:
        return 0, f"RAG 数据库构建失败：\n{traceback.format_exc()}", None

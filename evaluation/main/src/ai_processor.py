import json
import os
import traceback
from typing import Any

import requests

REQUIRED_FEEDBACK_KEYS = {"advantage", "disadvantage", "improvement"}


def _validate_config(config: dict[str, Any], name: str, require_temperature: bool = False) -> None:
    if not isinstance(config, dict):
        raise ValueError(f"{name} 必须是 dict")
    required = {"base_url", "api_key", "model"}
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"{name} 缺少必要字段: {', '.join(missing)}")
    if require_temperature and "temperature" not in config:
        raise ValueError(f"{name} 缺少必要字段: temperature")


def _api_url(base_url: str, endpoint: str) -> str:
    return base_url.rstrip("/") + "/" + endpoint.lstrip("/")


def _request_embedding(text: str, embedding_config: dict[str, Any]) -> list[float]:
    _validate_config(embedding_config, "embedding_config")
    response = requests.post(
        _api_url(str(embedding_config["base_url"]), "embeddings"),
        headers={
            "Authorization": f"Bearer {embedding_config['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": embedding_config["model"],
            "input": text,
        },
        timeout=float(embedding_config.get("timeout_seconds", 60)),
    )
    response.raise_for_status()
    data = response.json()
    try:
        embedding = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"embedding 接口返回格式错误: {data}") from exc
    if not isinstance(embedding, list) or not embedding:
        raise ValueError("embedding 接口返回空向量")
    return [float(v) for v in embedding]


def _extract_report_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI 返回内容不是合法 JSON: {raw_text}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("AI 返回 JSON 根节点必须是对象")
    keys = set(parsed.keys())
    if keys != REQUIRED_FEEDBACK_KEYS:
        raise ValueError(
            "AI 返回 JSON 字段必须且只能是 "
            f"{sorted(REQUIRED_FEEDBACK_KEYS)}，实际为 {sorted(keys)}"
        )
    for key in REQUIRED_FEEDBACK_KEYS:
        if not isinstance(parsed.get(key), str) or not parsed[key].strip():
            raise ValueError(f"AI 返回字段 {key} 必须是非空字符串")
    return parsed


def _build_rag_query(scoring_data: dict[str, Any], case_info: dict[str, Any]) -> str:
    dimensions = scoring_data.get("dimensions", {})
    dim2 = dimensions.get("dim2_energy", {})
    dim2_sub = dim2.get("sub_scores", {})
    penalties = scoring_data.get("penalties", {})

    parts = [
        str(case_info.get("diagnosis", "")),
        str(case_info.get("health_checkup", "")),
        "眼底光凝 教学反馈",
    ]
    if dim2:
        parts.append("激光参数空间适配度 参数场 局部参数偏差")
    for key, item in dim2_sub.items():
        regions = item.get("main_error_regions", [])
        if regions:
            parts.append(str(key))
            parts.extend(str(region) for region in regions)
    overlap = penalties.get("overlap_penalty", {})
    if overlap.get("count", 0):
        parts.append("光斑重叠 局部热量堆积")
    vessel = penalties.get("vessel_hit_penalty", {})
    if vessel.get("count", 0):
        parts.append("视网膜大血管 安全边界")
    return " ".join(part for part in parts if part).strip()


def _retrieve_rag_chunks(
    chroma_db_path: str,
    embedding_config: dict[str, Any],
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if not chroma_db_path or not os.path.exists(chroma_db_path):
        raise FileNotFoundError(f"RAG 向量数据库不存在: {chroma_db_path}")

    try:
        import chromadb
    except ImportError as exc:
        raise ImportError("缺少 chromadb 依赖，无法检索 RAG 向量数据库") from exc

    client = chromadb.PersistentClient(path=chroma_db_path)
    collections = client.list_collections()
    if not collections:
        raise ValueError(f"RAG 向量数据库中没有 collection: {chroma_db_path}")

    collection = None
    for item in collections:
        name = item.name if hasattr(item, "name") else str(item)
        if name == "clinical_knowledge":
            collection = client.get_collection(name)
            break
    if collection is None:
        first = collections[0]
        first_name = first.name if hasattr(first, "name") else str(first)
        collection = client.get_collection(first_name)

    query_embedding = _request_embedding(query, embedding_config)
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    chunks = []
    for idx, doc in enumerate(documents):
        metadata = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        distance = distances[idx] if idx < len(distances) else None
        chunks.append(
            {
                "text": doc,
                "metadata": metadata,
                "distance": distance,
            }
        )
    if not chunks:
        raise ValueError("RAG 检索结果为空")
    return chunks


def _build_messages(
    scoring_data: dict[str, Any],
    rubric_text: str,
    case_info: dict[str, Any],
    prompt_text: str,
    rag_chunks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    schema = {
        "advantage": "字符串：1-2个关键优点，必须引用评分事实",
        "disadvantage": "字符串：最关键问题，必须引用评分事实、机制和临床风险",
        "improvement": "字符串：至少2个可执行动作，包含观察指标",
    }
    user_payload = {
        "scoring_data": scoring_data,
        "case_info": case_info,
        "rubric_text": rubric_text,
        "rag_chunks": rag_chunks,
        "output_schema": schema,
        "hard_requirements": [
            "只输出合法 JSON，不要 Markdown，不要代码块。",
            "顶层字段必须且只能是 advantage、disadvantage、improvement。",
            "三个字段的值必须是字符串。",
            "不得修改评分数字，不得补造评分 JSON 中没有的错误。",
            "不要输出 IoU、R值、阈值、线性插值等内部算法词。",
            "若维度二为主要问题，必须结合 sub_scores、mean_error、main_error_regions 和热力图路径给出复盘指标。",
        ],
    }
    return [
        {
            "role": "system",
            "content": prompt_text.strip()
            + "\n你必须只输出严格 JSON，字段只能是 advantage、disadvantage、improvement。",
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]


def _request_chat(messages: list[dict[str, str]], llm_config: dict[str, Any]) -> str:
    _validate_config(llm_config, "llm_config", require_temperature=True)
    response = requests.post(
        _api_url(str(llm_config["base_url"]), "chat/completions"),
        headers={
            "Authorization": f"Bearer {llm_config['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": llm_config["model"],
            "messages": messages,
            "temperature": float(llm_config.get("temperature", 0.2)),
            "response_format": {"type": "json_object"},
        },
        timeout=float(llm_config.get("timeout_seconds", 60)),
    )
    response.raise_for_status()
    data = response.json()
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"chat 接口返回格式错误: {data}") from exc


def generate_teaching_feedback_report(
    scoring_data: dict[str, Any],
    rubric_text: str,
    case_info: dict[str, Any],
    prompt_text: str,
    chroma_db_path: str,
    llm_config: dict[str, Any],
    embedding_config: dict[str, Any],
    output_json_path: str | None = None,
) -> tuple[int, str, dict[str, Any] | None]:
    """基于规则评分结果和 RAG 知识库生成三段式教学反馈 JSON。"""
    try:
        if not isinstance(scoring_data, dict):
            raise ValueError("scoring_data 必须是 dict")
        if not isinstance(case_info, dict):
            raise ValueError("case_info 必须是 dict")
        if not isinstance(rubric_text, str) or not rubric_text.strip():
            raise ValueError("rubric_text 不能为空")
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            raise ValueError("prompt_text 不能为空")

        query = _build_rag_query(scoring_data, case_info)
        if not query:
            raise ValueError("无法从评分结果和病例信息构建 RAG query")
        rag_chunks = _retrieve_rag_chunks(chroma_db_path, embedding_config, query)
        messages = _build_messages(scoring_data, rubric_text, case_info, prompt_text, rag_chunks)
        raw_text = _request_chat(messages, llm_config)
        report_data = _extract_report_json(raw_text)

        if output_json_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

        return 1, "success", report_data
    except Exception:
        return 0, f"AI 教学反馈生成失败：\n{traceback.format_exc()}", None

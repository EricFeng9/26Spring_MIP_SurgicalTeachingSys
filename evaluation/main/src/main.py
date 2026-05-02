import json
import os
import traceback
from typing import Any

from ai_processor import generate_teaching_feedback_report
from evaluator import evaluate


def _load_json_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return data


def _load_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _require_file(path: str, label: str) -> None:
    if not path:
        raise ValueError(f"{label} 路径不能为空")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} 文件不存在: {path}")


def _require_dir(path: str, label: str) -> None:
    if not path:
        raise ValueError(f"{label} 路径不能为空")
    if not os.path.isdir(path):
        raise FileNotFoundError(f"{label} 目录不存在: {path}")


def _ensure_parent_dir(path: str, label: str) -> None:
    if not path:
        raise ValueError(f"{label} 路径不能为空")
    parent = os.path.dirname(os.path.abspath(path))
    if not parent:
        raise ValueError(f"{label} 父目录无效: {path}")
    os.makedirs(parent, exist_ok=True)


def _validate_ai_report(report_data: dict[str, Any]) -> None:
    expected = {"advantage", "disadvantage", "improvement"}
    keys = set(report_data.keys())
    if keys != expected:
        raise ValueError(f"教学反馈 JSON 字段必须且只能是 {sorted(expected)}，实际为 {sorted(keys)}")
    for key in expected:
        if not isinstance(report_data.get(key), str) or not report_data[key].strip():
            raise ValueError(f"教学反馈字段 {key} 必须是非空字符串")


def evaluate_with_ai_feedback(
    case_info_json_path: str,
    player_json_path: str,
    question_json_path: str,
    rubric_md_path: str,
    prompt_path: str,
    chroma_db_path: str,
    scoring_config_json_path: str,
    scoring_output_json_path: str,
    teaching_feedback_output_json_path: str,
    llm_config: dict[str, Any],
    embedding_config: dict[str, Any],
    param_tolerance_ratio: dict[str, float] | None = None,
) -> tuple[int, str, dict[str, Any] | None, dict[str, Any] | None]:
    """
    统一评测入口：先执行本地规则评分，再调用 AI 生成教学反馈。

    上层必须显式传入所有路径与模型配置；本函数不读取环境变量、不写死测试路径。
    """
    scoring_data: dict[str, Any] | None = None
    try:
        _require_file(case_info_json_path, "病例文本信息")
        _require_file(player_json_path, "玩家操作日志")
        _require_file(question_json_path, "病例手术 GT 参数")
        _require_file(rubric_md_path, "评分细则")
        _require_file(prompt_path, "提示词")
        _require_file(scoring_config_json_path, "评分配置")
        _require_dir(chroma_db_path, "RAG 向量数据库")
        _ensure_parent_dir(scoring_output_json_path, "玩家得分输出")
        _ensure_parent_dir(teaching_feedback_output_json_path, "教学反馈输出")

        score_status, score_msg = evaluate(
            question_json_path=question_json_path,
            player_json_path=player_json_path,
            scoring_output_json_path=scoring_output_json_path,
            config_json_path=scoring_config_json_path,
            param_tolerance_ratio=param_tolerance_ratio,
        )
        if score_status != 1:
            return 0, f"本地评分失败：{score_msg}", None, None

        scoring_data = _load_json_file(scoring_output_json_path)
        case_info = _load_json_file(case_info_json_path)
        rubric_text = _load_text_file(rubric_md_path)
        prompt_text = _load_text_file(prompt_path)

        feedback_status, feedback_msg, feedback_data = generate_teaching_feedback_report(
            scoring_data=scoring_data,
            rubric_text=rubric_text,
            case_info=case_info,
            prompt_text=prompt_text,
            chroma_db_path=chroma_db_path,
            llm_config=llm_config,
            embedding_config=embedding_config,
            output_json_path=teaching_feedback_output_json_path,
        )
        if feedback_status != 1 or feedback_data is None:
            return 0, f"本地评分成功，但 AI 教学反馈失败：{feedback_msg}", scoring_data, None

        _validate_ai_report(feedback_data)
        return 1, "success", scoring_data, feedback_data
    except Exception:
        return 0, f"统一评测流程发生异常：\n{traceback.format_exc()}", scoring_data, None

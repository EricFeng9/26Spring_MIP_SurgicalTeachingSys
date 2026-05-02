import json
import os
import sys

# 将主评估模块路径加入导入路径
MAIN_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../main/src'))
sys.path.append(MAIN_SRC_PATH)

from main import evaluate_with_ai_feedback

def _find_sample_paths(sample_root: str) -> tuple[str, str]:
    """在样本目录中定位一组 GT/Player 文件。"""
    candidates = []
    for root, _, files in os.walk(sample_root):
        for fn in files:
            if fn.endswith("_simgt.json"):
                gt_path = os.path.join(root, fn)
                player_path = gt_path.replace("_simgt.json", "_simplayer.json")
                if os.path.exists(player_path):
                    candidates.append((gt_path, player_path))
            elif fn.endswith("_after.json"):
                gt_path = os.path.join(root, fn)
                player_path = gt_path.replace("_after.json", "_player.json")
                if os.path.exists(player_path):
                    candidates.append((gt_path, player_path))
    if not candidates:
        raise FileNotFoundError(f"在 {sample_root} 下未找到可用的 GT/Player JSON 对")
    candidates.sort(key=lambda x: x[0])
    return candidates[0]


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


def _sample_id_from_gt_path(question_path: str) -> str:
    stem = os.path.splitext(os.path.basename(question_path))[0]
    for suffix in ("_after", "_simgt"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def run_sample_test() -> tuple[int, str]:
    """读取测试配置，调用 main.py 完成本地评分 + AI 教学反馈。"""
    project_root = _project_root()
    config = _load_test_config(project_root)
    llm_config = _require_section(config, "llm")
    embedding_config = _require_section(config, "embedding")
    rag_config = _require_section(config, "rag")
    inputs = _require_section(config, "inputs")
    outputs = _require_section(config, "outputs")

    sample_root = _resolve_path(project_root, inputs["sample_root"])
    question_path, player_path = _find_sample_paths(sample_root)
    sample_id = _sample_id_from_gt_path(question_path)
    base_config_path = _resolve_path(project_root, inputs["base_scoring_config_path"])
    outputs_base_dir = _resolve_path(project_root, outputs["base_dir"])
    output_dir = os.path.join(outputs_base_dir, sample_id)
    runtime_config_path = os.path.join(output_dir, "runtime_config_for_test.json")
    output_path = os.path.join(output_dir, "score_result.json")
    teaching_feedback_path = os.path.join(output_dir, "teaching_feedback.json")
    os.makedirs(output_dir, exist_ok=True)

    # 调用侧注入所有重建超参数（便于快速迭代调参）
    with open(base_config_path, "r", encoding="utf-8") as f:
        runtime_config = json.load(f)
    scoring_policy = runtime_config.setdefault("scoring_policy", {})
    scoring_policy["param_tolerance_ratio"] = {
        "power": 0.25,
        "spot_size": 0.25,
        "exposure_time": 0.25,
    }
    scoring_policy["spatial_parameter_field"] = {
        "field_resolution": "source_image_pixels",
        "field_sigma_px": 25.0,
        "heatmap_crop_padding_px": 40,
    }
    if "player_coordinate_space" in inputs:
        scoring_policy["player_coordinate_space"] = inputs["player_coordinate_space"]
    with open(runtime_config_path, "w", encoding="utf-8") as f:
        json.dump(runtime_config, f, ensure_ascii=False, indent=2)

    status_code, msg, scoring_data, feedback_data = evaluate_with_ai_feedback(
        case_info_json_path=_resolve_path(project_root, inputs["case_info_json_path"]),
        player_json_path=player_path,
        question_json_path=question_path,
        rubric_md_path=_resolve_path(project_root, inputs["rubric_md_path"]),
        prompt_path=_resolve_path(project_root, inputs["prompt_path"]),
        chroma_db_path=_resolve_path(project_root, rag_config["chroma_db_path"]),
        scoring_config_json_path=runtime_config_path,
        scoring_output_json_path=output_path,
        teaching_feedback_output_json_path=teaching_feedback_path,
        llm_config=llm_config,
        embedding_config=embedding_config,
        param_tolerance_ratio={
            "power": 0.25,
            "spot_size": 0.25,
            "exposure_time": 0.25,
        },
    )

    if scoring_data:
        result = scoring_data
        dimensions = result.get("dimensions", {})
        dim1 = dimensions.get("dim1_position", {})
        dim2 = dimensions.get("dim2_energy", {})
        dim3 = dimensions.get("dim3_density", {})
        dim2_sub = dim2.get("sub_scores", {})

        if status_code == 1:
            print(f"评估成功: {msg}")
        else:
            print(f"本地评分已生成，但完整链路失败: {msg}")
        print(f"GT输入: {question_path}")
        print(f"Player输入: {player_path}")
        print(f"输出目录: {output_dir}")
        print(f"输入配置: {runtime_config_path}")
        print(f"评分结果: {output_path}")
        print(f"总分: {result.get('total_score')} / 100")
        print(f"维度一 位置与范围: {dim1.get('score')} / {dim1.get('max_score')}, IoU={dim1.get('iou')}")
        print(f"维度二 激光参数空间适配度: {dim2.get('score')} / {dim2.get('max_score')}")
        for key in ("power", "spot_size", "exposure_time", "wavelength"):
            item = dim2_sub.get(key, {})
            print(
                f"  - {key}: {item.get('score')} / {item.get('max_score')}, "
                f"mean_error={item.get('mean_error')}, regions={item.get('main_error_regions')}"
            )
        print(f"维度三 密度与均匀度: {dim3.get('score')} / {dim3.get('max_score')}")
        print(f"Overlay可视化: {result.get('debug_visualization_paths')}")
        print(f"维度二热力图: {dim2.get('visualization')}")
    if status_code == 1:
        print(f"AI教学反馈: {teaching_feedback_path}")
        print(f"反馈内容: {feedback_data}")
    else:
        print(f"评估链路失败: {msg}")
    return status_code, msg

if __name__ == "__main__":
    run_sample_test()

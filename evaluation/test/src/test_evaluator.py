import json
import os
import sys

# 将主评估模块路径加入导入路径
MAIN_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../main/src'))
sys.path.append(MAIN_SRC_PATH)

from evaluator import evaluate

def _find_sample_paths(sample_root: str) -> tuple[str, str]:
    """在样本目录中定位一组 simgt/simplayer 文件。"""
    candidates = []
    for root, _, files in os.walk(sample_root):
        for fn in files:
            if not fn.endswith("_simgt.json"):
                continue
            gt_path = os.path.join(root, fn)
            player_path = gt_path.replace("_simgt.json", "_simplayer.json")
            if os.path.exists(player_path):
                candidates.append((gt_path, player_path))
    if not candidates:
        raise FileNotFoundError(f"在 {sample_root} 下未找到可用的 simgt/simplayer JSON 对")
    candidates.sort(key=lambda x: x[0])
    return candidates[0]


def run_sample_test() -> tuple[int, str]:
    """读取 Temp 样本输入并输出评分 json。"""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    sample_folder_name = "Temp770298_sample_v4"
    sample_root = os.path.join(project_root, "evaluation", "test", "sample_data", sample_folder_name)
    question_path, player_path = _find_sample_paths(sample_root)
    base_config_path = os.path.join(project_root, "evaluation", "docs", "config.json")
    output_dir = os.path.join(project_root, "evaluation", "test", "output", sample_folder_name)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "score_result.json")
    runtime_config_path = os.path.join(output_dir, "runtime_config_for_test.json")

    # 调用侧注入所有重建超参数（便于快速迭代调参）
    with open(base_config_path, "r", encoding="utf-8") as f:
        runtime_config = json.load(f)
    scoring_policy = runtime_config.setdefault("scoring_policy", {})
    scoring_policy["player_area_rebuild"] = {
        "ratio_candidates": [0.35, 0.30, 0.25, 0.20, 0.15, 0.10],
        "inner_iqr_k": 0.75,
        "inner_ratio_limit": 0.20,
        "inner_abs_limit": 3,
        "min_outer_points": 8,
    }
    scoring_policy["param_tolerance_abs"] = {
        "power": 25.0,
        "spot_size": 30.0,
        "exposure_time": 10.0,
    }
    scoring_policy["spatial_parameter_field"] = {
        "field_resolution": "source_image_pixels",
        "field_sigma_px": 25.0,
    }
    with open(runtime_config_path, "w", encoding="utf-8") as f:
        json.dump(runtime_config, f, ensure_ascii=False, indent=2)

    # 调用对外评估接口：输入题目路径、玩家路径、输出路径
    status_code, msg = evaluate(
        question_json_path=question_path,
        player_json_path=player_path,
        scoring_output_json_path=output_path,
        config_json_path=runtime_config_path,
    )

    if status_code == 1:
        with open(output_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        dimensions = result.get("dimensions", {})
        dim1 = dimensions.get("dim1_position", {})
        dim2 = dimensions.get("dim2_energy", {})
        dim3 = dimensions.get("dim3_density", {})
        dim2_sub = dim2.get("sub_scores", {})

        print(f"评估成功: {msg}")
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
    else:
        print(f"评估失败: {msg}")
    return status_code, msg

if __name__ == "__main__":
    run_sample_test()

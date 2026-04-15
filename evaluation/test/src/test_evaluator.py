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
    sample_folder_name = "Temp770298_sample"
    sample_root = os.path.join(project_root, "evaluation", "test", "sample_data", sample_folder_name)
    question_path, player_path = _find_sample_paths(sample_root)
    base_config_path = os.path.join(project_root, "evaluation", "docs", "config.json")
    output_path = os.path.join(project_root, "evaluation", "test", "output", f"{sample_folder_name}_output.json")
    runtime_config_path = os.path.join(project_root, "evaluation", "test", "output", "runtime_config_for_test.json")

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
        print(f"评估成功: {msg}")
        print(f"输入题目: {question_path}")
        print(f"输入玩家: {player_path}")
        print(f"输入配置: {runtime_config_path}")
        print(f"输出文件: {output_path}")
    else:
        print(f"评估失败: {msg}")
    return status_code, msg

if __name__ == "__main__":
    run_sample_test()

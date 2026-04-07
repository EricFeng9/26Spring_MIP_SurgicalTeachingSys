import os
import sys

# 将主评估模块路径加入导入路径
MAIN_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../main/src'))
sys.path.append(MAIN_SRC_PATH)

from evaluator import evaluate

def run_sample_test() -> tuple[int, str]:
    """读取样例输入并输出 scoring json。"""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    question_path = os.path.join(project_root, "evaluation", "docs", "question_sample.json")
    player_path = os.path.join(project_root, "evaluation", "docs", "player_sample.json")
    output_path = os.path.join(project_root, "evaluation", "test", "output", "scoring_output_from_test.json")

    # 调用对外评估接口：输入题目路径、玩家路径、输出路径
    status_code, msg = evaluate(
        question_json_path=question_path,
        player_json_path=player_path,
        scoring_output_json_path=output_path,
    )

    if status_code == 1:
        print(f"评估成功: {msg}")
        print(f"输出文件: {output_path}")
    else:
        print(f"评估失败: {msg}")
    return status_code, msg

if __name__ == "__main__":
    run_sample_test()

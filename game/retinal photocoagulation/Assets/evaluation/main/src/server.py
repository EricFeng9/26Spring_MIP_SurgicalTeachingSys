import json
import base64
import os
import shutil
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from PIL import Image

from evaluator import evaluate
from main import evaluate_with_ai_feedback


HOST = "127.0.0.1"
PORT = 8000
SAMPLE_CASE_ID = "4226701"
SERVER_VERSION = "unity-real-surgery-normalize-v2"
REQUIRE_REAL_PLAYER_PNG = True
MAX_EVALUATION_SESSIONS_TO_KEEP = 0


def _project_eval_root() -> str:
    # server.py lives in Assets/evaluation/main/src.
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _unity_project_root() -> str:
    # Assets/evaluation -> Unity project root.
    return os.path.abspath(os.path.join(_project_eval_root(), ".."))


def _sample_data_dir() -> str:
    return os.path.join(_project_eval_root(), "test", "sample_data")


def _sample_case_dir() -> str:
    return os.path.join(_sample_data_dir(), "2604_sampledata", SAMPLE_CASE_ID)


def _docs_dir() -> str:
    return os.path.join(_project_eval_root(), "docs")


def _unity_assets_root() -> str:
    return os.path.abspath(os.path.join(_project_eval_root(), ".."))


def _test_config_path() -> str:
    return os.path.join(_project_eval_root(), "test", "src", "config.json")


def _rag_chroma_db_dir() -> str:
    return os.path.join(_project_eval_root(), "test", "rag", "chroma_db")


def _resolve_config_path(path: str) -> str:
    if not path:
        return path

    if os.path.isabs(path):
        return path

    # test/src/config.json stores paths like "evaluation/test/..."; those are
    # relative to the Unity Assets folder, not to evaluation/main/src.
    return os.path.abspath(os.path.join(_unity_assets_root(), path))


def _output_dir() -> str:
    path = os.path.join(_unity_project_root(), "EvaluationOutput", "unity_http")
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup_old_output_sessions() -> None:
    if MAX_EVALUATION_SESSIONS_TO_KEEP <= 0:
        return

    root = _output_dir()
    try:
        session_dirs = [
            os.path.join(root, name)
            for name in os.listdir(root)
            if os.path.isdir(os.path.join(root, name))
            and os.path.isfile(os.path.join(root, name, "score_result.json"))
        ]
        session_dirs.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        for old_dir in session_dirs[MAX_EVALUATION_SESSIONS_TO_KEEP:]:
            shutil.rmtree(old_dir, ignore_errors=True)
    except Exception:
        # Cleanup must never break an otherwise successful evaluation.
        pass


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _safe_session_id(request_data: dict[str, Any]) -> str:
    session_id = str(request_data.get("session_id") or datetime.now().strftime("SESS_%Y%m%d_%H%M%S"))
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in session_id)


def _safe_output_id(request_data: dict[str, Any]) -> str:
    player_json = request_data.get("player_json") if isinstance(request_data.get("player_json"), dict) else {}
    task_id = (
        request_data.get("task_id")
        or player_json.get("task_id")
        or _safe_session_id(request_data)
    )
    safe_id = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in str(task_id))
    return safe_id or _safe_session_id(request_data)


def _save_raw_request(request_data: dict[str, Any], session_dir: str, session_id: str) -> str:
    path = os.path.join(session_dir, f"{session_id}_request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(request_data, f, ensure_ascii=False, indent=2)
    return path


def _sample_after_png_path() -> str:
    return os.path.join(_sample_case_dir(), f"{SAMPLE_CASE_ID}_after.png")


def _get_image_size(path: str) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def _resize_player_png_to_target(player_png_path: str, target_size: tuple[int, int], session_dir: str) -> tuple[int, int] | None:
    if not os.path.isfile(player_png_path):
        return None

    with Image.open(player_png_path) as img:
        source_size = img.size
        if source_size == target_size:
            return source_size

        original_path = os.path.join(session_dir, "player_original_unscaled.png")
        if not os.path.isfile(original_path):
            shutil.copyfile(player_png_path, original_path)

        resized = img.convert("RGBA").resize(target_size, Image.Resampling.LANCZOS)
        resized.save(player_png_path)
        return source_size


def _scale_player_json_to_target(
    player_json: dict[str, Any],
    source_size: tuple[int, int] | None,
    target_size: tuple[int, int],
) -> dict[str, Any]:
    if source_size is None or source_size == target_size:
        return player_json

    source_w, source_h = source_size
    target_w, target_h = target_size
    if source_w <= 0 or source_h <= 0:
        return player_json

    scale_x = target_w / source_w
    scale_y = target_h / source_h
    radius_scale = (scale_x + scale_y) * 0.5

    scaled_json = json.loads(json.dumps(player_json, ensure_ascii=False))
    shots = scaled_json.get("shots")
    if isinstance(shots, list):
        for shot in shots:
            if not isinstance(shot, dict):
                continue

            pos = shot.get("pos")
            if isinstance(pos, list) and len(pos) >= 2:
                if isinstance(pos[0], (int, float)):
                    pos[0] = float(pos[0]) * scale_x
                if isinstance(pos[1], (int, float)):
                    pos[1] = float(pos[1]) * scale_y

            radius_px = shot.get("radius_px")
            if isinstance(radius_px, (int, float)):
                shot["radius_px"] = float(radius_px) * radius_scale

    scaled_json["_unity_coordinate_normalization"] = {
        "source_size": [source_w, source_h],
        "target_size": [target_w, target_h],
        "scale_x": scale_x,
        "scale_y": scale_y,
        "radius_scale": radius_scale,
        "server_version": SERVER_VERSION,
    }
    return scaled_json


def _write_player_json(request_data: dict[str, Any], session_dir: str) -> str:
    player_json = request_data.get("player_json")
    if not isinstance(player_json, dict):
        raise ValueError("request must contain object field: player_json")

    player_png_path = os.path.join(session_dir, "player.png")
    player_png_base64 = request_data.get("player_png_base64")
    if isinstance(player_png_base64, str) and player_png_base64:
        with open(player_png_path, "wb") as f:
            f.write(base64.b64decode(player_png_base64))
    else:
        if REQUIRE_REAL_PLAYER_PNG:
            raise ValueError("request must contain real Unity field: player_png_base64")

        # Keep the old sample-image bridge for requests that only send JSON.
        sample_player_png = os.path.join(_sample_case_dir(), f"{SAMPLE_CASE_ID}_player.png")
        if os.path.isfile(sample_player_png):
            shutil.copyfile(sample_player_png, player_png_path)

    target_size = _get_image_size(_sample_after_png_path())
    source_size = _resize_player_png_to_target(player_png_path, target_size, session_dir)
    normalized_player_json = _scale_player_json_to_target(player_json, source_size, target_size)

    path = os.path.join(session_dir, "player.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized_player_json, f, ensure_ascii=False, indent=2)

    return path


def _build_demo_response(request_data: dict[str, Any], saved_path: str, reason: str | None = None) -> dict[str, Any]:
    player_json = request_data.get("player_json") or {}
    shots = player_json.get("shots") or []
    consultation = request_data.get("consultation") or {}
    selected_disease = consultation.get("selected_disease") or "未选择病症"
    needs_photocoagulation = bool(consultation.get("needs_photocoagulation"))

    shot_count = len(shots)
    total_score = 60.0 + min(30.0, shot_count * 1.5)
    if needs_photocoagulation:
        total_score += 5.0

    message = f"demo evaluator response; request saved to {saved_path}"
    if reason:
        message += f"; real evaluator fallback reason: {reason}"

    return {
        "success": True,
        "message": message,
        "total_score": round(min(total_score, 100.0), 1),
        "advantage": f"已收到玩家对「{selected_disease}」的诊断判断，并记录 {shot_count} 个光斑。当前 Unity 到 Python 的 HTTP 链路正常。",
        "disadvantage": "当前返回的是 Demo fallback 评分，真实 evaluator 未成功完成或仍在接入中。",
        "improvement": "请查看 server.py 控制台与 unity_http 输出目录中的 score_result.json / request.json，逐步替换为真实截图和任务标准答案。",
        "standard_image_path": "",
        "player_image_path": ""
    }


def _load_json_if_exists(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _has_model_config(config: dict[str, Any], key: str) -> bool:
    value = config.get(key)
    if not isinstance(value, dict):
        return False

    return bool(value.get("base_url") and value.get("api_key") and value.get("model"))


def _can_run_ai_feedback(config: dict[str, Any]) -> bool:
    return _has_model_config(config, "llm_config") and _has_model_config(config, "embedding_config")


def _load_unified_eval_config() -> dict[str, Any]:
    test_config = _load_json_if_exists(_test_config_path())
    docs_config = _load_json_if_exists(os.path.join(_docs_dir(), "config.json"))

    if not test_config:
        return {
            "scoring_config_path": os.path.join(_docs_dir(), "config.json"),
            "llm_config": docs_config.get("llm_config") or {},
            "embedding_config": docs_config.get("embedding_config") or {},
            "case_info_json_path": os.path.join(_sample_case_dir(), f"{SAMPLE_CASE_ID}_introduction.json"),
            "rubric_md_path": os.path.join(_docs_dir(), "评分细则v5.md"),
            "prompt_path": os.path.join(_docs_dir(), "llm_structured_scoring_report_prompt.txt"),
            "chroma_db_path": _rag_chroma_db_dir(),
        }

    inputs = test_config.get("inputs") if isinstance(test_config.get("inputs"), dict) else {}
    rag = test_config.get("rag") if isinstance(test_config.get("rag"), dict) else {}

    base_scoring_config = inputs.get("base_scoring_config_path") or "evaluation/docs/config.json"
    return {
        "scoring_config_path": _resolve_config_path(base_scoring_config),
        "llm_config": test_config.get("llm") or test_config.get("llm_config") or {},
        "embedding_config": test_config.get("embedding") or test_config.get("embedding_config") or {},
        "case_info_json_path": _resolve_config_path(
            inputs.get("case_info_json_path") or f"evaluation/test/sample_data/2604_sampledata/{SAMPLE_CASE_ID}/{SAMPLE_CASE_ID}_introduction.json"
        ),
        "rubric_md_path": _resolve_config_path(inputs.get("rubric_md_path") or "evaluation/docs/评分细则v5.md"),
        "prompt_path": _resolve_config_path(inputs.get("prompt_path") or "evaluation/docs/llm_structured_scoring_report_prompt.txt"),
        "chroma_db_path": _resolve_config_path(rag.get("chroma_db_path") or "evaluation/test/rag/chroma_db"),
    }


def _build_success_response(
    scoring_data: dict[str, Any],
    session_dir: str,
    message: str,
    evaluation_mode: str,
    ai_feedback_status: str,
    feedback_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if feedback_data:
        advantage = str(feedback_data.get("advantage") or "")
        disadvantage = str(feedback_data.get("disadvantage") or "")
        improvement = str(feedback_data.get("improvement") or "")
    else:
        advantage, disadvantage, improvement = _summarize_scoring(scoring_data)

    return {
        "success": True,
        "message": message,
        "evaluation_mode": evaluation_mode,
        "ai_feedback_status": ai_feedback_status,
        "total_score": float(scoring_data.get("total_score", 0)),
        "advantage": advantage,
        "disadvantage": disadvantage,
        "improvement": improvement,
        "standard_image_path": os.path.join(_sample_case_dir(), f"{SAMPLE_CASE_ID}_after.png"),
        "player_image_path": os.path.join(session_dir, "player.png"),
        "scoring_output_path": os.path.join(session_dir, "score_result.json"),
        "teaching_feedback_path": os.path.join(session_dir, "teaching_feedback.json"),
    }


def _summarize_scoring(scoring_data: dict[str, Any]) -> tuple[str, str, str]:
    dimensions = scoring_data.get("dimensions") or {}
    dim1 = dimensions.get("dim1_position") or {}
    dim2 = dimensions.get("dim2_energy") or {}
    dim3 = dimensions.get("dim3_density") or {}
    penalties = scoring_data.get("penalties") or {}

    advantage = (
        f"真实评分已完成。总分 {scoring_data.get('total_score', 0)}。"
        f"位置得分 {dim1.get('score', '-')}/{dim1.get('max_score', '-')}，"
        f"能量参数得分 {dim2.get('score', '-')}/{dim2.get('max_score', '-')}，"
        f"密度得分 {dim3.get('score', '-')}/{dim3.get('max_score', '-')}。"
    )

    disadvantage = (
        f"位置评价：{dim1.get('eval_msg', '暂无')}\n"
        f"参数评价：{dim2.get('eval_msg', '暂无')}\n"
        f"密度评价：{dim3.get('eval_msg', '暂无')}"
    )

    improvement = (
        "建议根据低分维度优先复盘：若位置分低，检查病灶边界和包围范围；"
        "若参数分低，复查功率、光斑直径、曝光时间与波长；"
        "若密度分低，调整光斑间距与连续性。"
    )

    overlap = (penalties.get("overlap_penalty") or {}).get("count")
    vessel = (penalties.get("vessel_hit_penalty") or {}).get("count")
    if overlap is not None or vessel is not None:
        improvement += f"\n惩罚项：重叠 {overlap if overlap is not None else '-'} 次，血管/危险区域命中 {vessel if vessel is not None else '-'} 次。"

    return advantage, disadvantage, improvement


def _try_real_evaluate(request_data: dict[str, Any], session_dir: str) -> dict[str, Any]:
    player_json_path = _write_player_json(request_data, session_dir)
    question_json_path = os.path.join(_sample_case_dir(), f"{SAMPLE_CASE_ID}_after.json")
    scoring_output_path = os.path.join(session_dir, "score_result.json")
    teaching_feedback_output_path = os.path.join(session_dir, "teaching_feedback.json")
    eval_config = _load_unified_eval_config()
    config_json_path = eval_config["scoring_config_path"]

    if _can_run_ai_feedback(eval_config):
        status, message, scoring_data, feedback_data = evaluate_with_ai_feedback(
            case_info_json_path=eval_config["case_info_json_path"],
            player_json_path=player_json_path,
            question_json_path=question_json_path,
            rubric_md_path=eval_config["rubric_md_path"],
            prompt_path=eval_config["prompt_path"],
            chroma_db_path=eval_config["chroma_db_path"],
            scoring_config_json_path=config_json_path,
            scoring_output_json_path=scoring_output_path,
            teaching_feedback_output_json_path=teaching_feedback_output_path,
            llm_config=eval_config["llm_config"],
            embedding_config=eval_config["embedding_config"],
        )

        if scoring_data is not None:
            ai_status = "success" if status == 1 and feedback_data is not None else "failed_after_rule_score"
            return _build_success_response(
                scoring_data=scoring_data,
                session_dir=session_dir,
                message=message,
                evaluation_mode="main_with_ai",
                ai_feedback_status=ai_status,
                feedback_data=feedback_data,
            )

        raise RuntimeError(message)

    status, message = evaluate(
        question_json_path=question_json_path,
        player_json_path=player_json_path,
        scoring_output_json_path=scoring_output_path,
        config_json_path=config_json_path,
    )

    if status != 1:
        raise RuntimeError(message)

    with open(scoring_output_path, "r", encoding="utf-8") as f:
        scoring_data = json.load(f)

    return _build_success_response(
        scoring_data=scoring_data,
        session_dir=session_dir,
        message=(
            f"rule evaluator success; score saved to {scoring_output_path}; "
            "AI feedback skipped because evaluation/test/src/config.json has no usable llm/embedding config"
        ),
        evaluation_mode="rule_only",
        ai_feedback_status="skipped_missing_model_config",
    )


class EvaluationRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        _json_response(self, 200, {"success": True})

    def do_GET(self) -> None:
        if self.path == "/health":
            _json_response(self, 200, {
                "success": True,
                "message": "local evaluation server is running",
                "host": HOST,
                "port": PORT,
                "mode": "real evaluator first, demo fallback",
                "server_version": SERVER_VERSION,
                "require_real_player_png": REQUIRE_REAL_PLAYER_PNG,
                "sample_case_id": SAMPLE_CASE_ID,
                "sample_case_dir": _sample_case_dir()
            })
            return

        _json_response(self, 404, {
            "success": False,
            "message": "Not found. Use GET /health or POST /evaluate."
        })

    def do_POST(self) -> None:
        if self.path != "/evaluate":
            _json_response(self, 404, {
                "success": False,
                "message": "Not found. Use POST /evaluate."
            })
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            request_data = json.loads(raw_body.decode("utf-8"))
            if not isinstance(request_data, dict):
                raise ValueError("request body must be a JSON object")

            session_id = _safe_session_id(request_data)
            output_id = _safe_output_id(request_data)
            session_dir = os.path.join(_output_dir(), output_id)
            if os.path.isdir(session_dir):
                shutil.rmtree(session_dir)
            os.makedirs(session_dir, exist_ok=True)
            saved_path = _save_raw_request(request_data, session_dir, session_id)

            try:
                response = _try_real_evaluate(request_data, session_dir)
            except Exception as exc:
                traceback_path = os.path.join(session_dir, "real_evaluator_error.txt")
                with open(traceback_path, "w", encoding="utf-8") as f:
                    f.write(traceback.format_exc())
                response = _build_demo_response(request_data, saved_path, reason=str(exc))

            _cleanup_old_output_sessions()
            _json_response(self, 200, response)
        except Exception as exc:
            _json_response(self, 500, {
                "success": False,
                "message": str(exc),
                "total_score": 0,
                "advantage": "",
                "disadvantage": "本机评估服务处理请求失败。",
                "improvement": "请检查 Unity 发送的 JSON 格式，以及 server.py 控制台报错。"
            })


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), EvaluationRequestHandler)
    print(f"Local evaluation server running at http://{HOST}:{PORT}")
    print("Health check: http://127.0.0.1:8000/health")
    print("Evaluate API: POST http://127.0.0.1:8000/evaluate")
    print("Mode: try real evaluator first; fallback to demo response if it fails.")
    server.serve_forever()


if __name__ == "__main__":
    run()

using System;
using System.Collections;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace RetinalPrototype.Hub
{
    public sealed class EvaluationApiClient : MonoBehaviour
    {
        [SerializeField] private string apiUrl = "http://127.0.0.1:8000/evaluate";
        [SerializeField] private int requestTimeoutSeconds = 120;
        [SerializeField] private bool alsoWriteLocalDebugFiles = true;
        [SerializeField] private string localDebugFolderName = "EvaluationDebug";

        public IEnumerator SubmitCurrentSession(Action<GameFlowEvaluationResponse> onSuccess, Action<string> onError)
        {
            var session = GameFlowSession.Instance;
            if (string.IsNullOrWhiteSpace(session.SessionId) || session.Shots == null || session.Shots.Count <= 0)
            {
                onError?.Invoke("Skipped legacy GameFlowSession evaluation submit: no active surgery session or no recorded shots.");
                yield break;
            }

            var requestData = session.BuildEvaluationRequest();
            string json = JsonUtility.ToJson(requestData, true).Replace("\"params_data\"", "\"params\"");

            if (alsoWriteLocalDebugFiles)
            {
                WriteDebugJson(json);
            }

            if (string.IsNullOrWhiteSpace(apiUrl))
            {
                onError?.Invoke("Evaluation API Url is empty. Local debug JSON has been written if enabled.");
                yield break;
            }

            using var request = new UnityWebRequest(apiUrl, UnityWebRequest.kHttpVerbPOST);
            byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
            request.uploadHandler = new UploadHandlerRaw(bodyRaw);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.timeout = Mathf.Max(1, requestTimeoutSeconds);
            request.SetRequestHeader("Content-Type", "application/json");

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                onError?.Invoke(request.error + "\n" + request.downloadHandler.text);
                yield break;
            }

            GameFlowEvaluationResponse response;
            try
            {
                response = JsonUtility.FromJson<GameFlowEvaluationResponse>(request.downloadHandler.text);
            }
            catch (Exception ex)
            {
                onError?.Invoke("Failed to parse evaluation response: " + ex.Message);
                yield break;
            }

            onSuccess?.Invoke(response);
        }

        public IEnumerator SubmitExportedSurgery(
            string sessionId,
            string taskId,
            string playerId,
            string playerName,
            string playerJson,
            byte[] playerPngBytes,
            Action<GameFlowEvaluationResponse> onSuccess,
            Action<string> onError)
        {
            if (string.IsNullOrWhiteSpace(playerJson))
            {
                onError?.Invoke("Exported surgery JSON is empty.");
                yield break;
            }

            string json = BuildExportedSurgeryRequestJson(
                sessionId,
                taskId,
                playerId,
                playerName,
                playerJson,
                playerPngBytes);

            if (alsoWriteLocalDebugFiles)
            {
                WriteDebugJson(json, sessionId);
            }

            if (string.IsNullOrWhiteSpace(apiUrl))
            {
                onError?.Invoke("Evaluation API Url is empty. Local debug JSON has been written if enabled.");
                yield break;
            }

            using var request = new UnityWebRequest(apiUrl, UnityWebRequest.kHttpVerbPOST);
            byte[] bodyRaw = Encoding.UTF8.GetBytes(json);
            request.uploadHandler = new UploadHandlerRaw(bodyRaw);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.timeout = Mathf.Max(1, requestTimeoutSeconds);
            request.SetRequestHeader("Content-Type", "application/json");

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                onError?.Invoke(request.error + "\n" + request.downloadHandler.text);
                yield break;
            }

            GameFlowEvaluationResponse response;
            try
            {
                response = JsonUtility.FromJson<GameFlowEvaluationResponse>(request.downloadHandler.text);
            }
            catch (Exception ex)
            {
                onError?.Invoke("Failed to parse evaluation response: " + ex.Message);
                yield break;
            }

            onSuccess?.Invoke(response);
        }

        private void WriteDebugJson(string json)
        {
            WriteDebugJson(json, GameFlowSession.Instance.SessionId);
        }

        private void WriteDebugJson(string json, string sessionId)
        {
            string dir = Path.Combine(Application.persistentDataPath, localDebugFolderName);
            Directory.CreateDirectory(dir);

            if (string.IsNullOrEmpty(sessionId))
            {
                sessionId = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            }

            string path = Path.Combine(dir, sessionId + "_evaluation_request.json");
            File.WriteAllText(path, json);
            Debug.Log("Evaluation request JSON written to: " + path);
        }

        private static string BuildExportedSurgeryRequestJson(
            string sessionId,
            string taskId,
            string playerId,
            string playerName,
            string playerJson,
            byte[] playerPngBytes)
        {
            string safeSessionId = string.IsNullOrWhiteSpace(sessionId) ? DateTime.Now.ToString("yyyyMMdd_HHmmss") : sessionId;
            string safeTaskId = string.IsNullOrWhiteSpace(taskId) ? "T001_RP_Standard" : taskId;
            string safePlayerId = string.IsNullOrWhiteSpace(playerId) ? "ST_001" : playerId;
            string safePlayerName = string.IsNullOrWhiteSpace(playerName) ? "Operator" : playerName;
            string pngBase64 = playerPngBytes != null && playerPngBytes.Length > 0
                ? Convert.ToBase64String(playerPngBytes)
                : string.Empty;

            var sb = new StringBuilder(1024 + playerJson.Length + pngBase64.Length);
            sb.Append("{");
            sb.Append("\"session_id\":\"").Append(EscapeJsonString(safeSessionId)).Append("\",");
            sb.Append("\"task_id\":\"").Append(EscapeJsonString(safeTaskId)).Append("\",");
            sb.Append("\"player_info\":{");
            sb.Append("\"id\":\"").Append(EscapeJsonString(safePlayerId)).Append("\",");
            sb.Append("\"name\":\"").Append(EscapeJsonString(safePlayerName)).Append("\"");
            sb.Append("},");
            sb.Append("\"player_json\":").Append(playerJson).Append(",");
            sb.Append("\"player_png_base64\":\"").Append(pngBase64).Append("\"");
            sb.Append("}");
            return sb.ToString();
        }

        private static string EscapeJsonString(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return string.Empty;
            }

            return value
                .Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\b", "\\b")
                .Replace("\f", "\\f")
                .Replace("\n", "\\n")
                .Replace("\r", "\\r")
                .Replace("\t", "\\t");
        }
    }
}

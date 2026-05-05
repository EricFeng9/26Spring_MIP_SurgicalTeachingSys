using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    public sealed class GameFlowSession : MonoBehaviour
    {
        private static GameFlowSession _instance;

        [SerializeField] private GameFlowPlayerInfo playerInfo = new GameFlowPlayerInfo();
        [SerializeField] private GameFlowTaskInfo currentTask = new GameFlowTaskInfo();
        [SerializeField] private GameFlowConsultationDecision consultationDecision = new GameFlowConsultationDecision();
        [SerializeField] private string sessionId;

        private readonly List<GameFlowShot> _shots = new List<GameFlowShot>();

        public static GameFlowSession Instance
        {
            get
            {
                EnsureInstance();
                return _instance;
            }
        }

        public GameFlowPlayerInfo PlayerInfo => playerInfo;
        public GameFlowTaskInfo CurrentTask => currentTask;
        public GameFlowConsultationDecision ConsultationDecision => consultationDecision;
        public string SessionId => sessionId;
        public IReadOnlyList<GameFlowShot> Shots => _shots;

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }

            _instance = this;
            DontDestroyOnLoad(gameObject);
        }

        public void ConfigurePlayer(string playerId, string playerName)
        {
            playerInfo.id = string.IsNullOrWhiteSpace(playerId) ? playerInfo.id : playerId;
            playerInfo.name = string.IsNullOrWhiteSpace(playerName) ? playerInfo.name : playerName;
        }

        public void StartTask(GameFlowTaskInfo task)
        {
            currentTask = task ?? new GameFlowTaskInfo();
            consultationDecision = new GameFlowConsultationDecision
            {
                task_id = currentTask.task_id,
                player_id = playerInfo.id,
                player_name = playerInfo.name
            };
        }

        public void RecordConsultationDecision(string selectedDisease, bool needsPhotocoagulation)
        {
            consultationDecision.task_id = currentTask.task_id;
            consultationDecision.player_id = playerInfo.id;
            consultationDecision.player_name = playerInfo.name;
            consultationDecision.selected_disease = selectedDisease;
            consultationDecision.needs_photocoagulation = needsPhotocoagulation;
        }

        public string BeginSurgerySession()
        {
            sessionId = "SESS_" + DateTime.Now.ToString("yyyyMMdd_HHmmss");
            _shots.Clear();
            return sessionId;
        }

        public void RecordShot(
            Vector2 texturePosition,
            bool isTrial,
            int spotGrade,
            float power,
            float spotSize,
            float exposureTime,
            float wavelength)
        {
            if (string.IsNullOrEmpty(sessionId))
            {
                BeginSurgerySession();
            }

            _shots.Add(new GameFlowShot
            {
                id = _shots.Count + 1,
                pos = new[] { texturePosition.x, texturePosition.y },
                is_trial = isTrial,
                spot_grade = spotGrade,
                params_data = new GameFlowLaserParams
                {
                    power = power,
                    spot_size = spotSize,
                    exposure_time = exposureTime,
                    wavelength = wavelength
                }
            });
        }

        public GameFlowPlayerShotsJson BuildPlayerShotsJson()
        {
            return new GameFlowPlayerShotsJson
            {
                session_id = sessionId,
                task_id = currentTask.task_id,
                player_info = playerInfo,
                shots = new List<GameFlowShot>(_shots)
            };
        }

        public GameFlowEvaluationRequest BuildEvaluationRequest()
        {
            return new GameFlowEvaluationRequest
            {
                session_id = sessionId,
                task_id = currentTask.task_id,
                player_info = playerInfo,
                consultation = consultationDecision,
                player_json = BuildPlayerShotsJson()
            };
        }

        public string ExportPlayerShotsJson(string directory)
        {
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, $"{sessionId}_player.json");
            string json = BuildPlayerShotsJsonString();
            File.WriteAllText(path, json);
            return path;
        }

        public string BuildPlayerShotsJsonString()
        {
            string json = JsonUtility.ToJson(BuildPlayerShotsJson(), true);
            return json.Replace("\"params_data\"", "\"params\"");
        }

        private static void EnsureInstance()
        {
            if (_instance != null)
            {
                return;
            }

            var obj = new GameObject(nameof(GameFlowSession));
            _instance = obj.AddComponent<GameFlowSession>();
        }
    }
}

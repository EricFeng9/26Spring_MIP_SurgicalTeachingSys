using UnityEngine;
using System;
using System.IO;

namespace RetinalPrototype.Hub
{
    public sealed class TreatmentRecordStore : MonoBehaviour
    {
        private static TreatmentRecordStore _instance;
        private TreatmentRecordData _latestRecord;

        public static bool HasLatestRecord => _instance != null && _instance._latestRecord != null;

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

        public static void SaveLatest(TreatmentRecordData record)
        {
            EnsureInstance();
            _instance._latestRecord = record;
        }

        public static TreatmentRecordData GetLatest()
        {
            TreatmentRecordData latestDiskRecord = TryLoadLatestEvaluationRecordFromDisk();
            if (latestDiskRecord != null)
            {
                SaveLatest(latestDiskRecord);
                return latestDiskRecord;
            }

            return _instance != null ? _instance._latestRecord : null;
        }

        private static void EnsureInstance()
        {
            if (_instance != null)
            {
                return;
            }

            var storeObject = new GameObject(nameof(TreatmentRecordStore));
            _instance = storeObject.AddComponent<TreatmentRecordStore>();
        }

        private static TreatmentRecordData TryLoadLatestEvaluationRecordFromDisk()
        {
            string[] roots = GetEvaluationOutputRoots();
            DirectoryInfo latestValidSession = null;

            foreach (string root in roots)
            {
                if (string.IsNullOrWhiteSpace(root) || !Directory.Exists(root))
                {
                    continue;
                }

                foreach (DirectoryInfo dir in new DirectoryInfo(root).GetDirectories())
                {
                    string scorePath = Path.Combine(dir.FullName, "score_result.json");
                    if (!File.Exists(scorePath))
                    {
                        continue;
                    }

                    if (latestValidSession == null || dir.LastWriteTimeUtc > latestValidSession.LastWriteTimeUtc)
                    {
                        latestValidSession = dir;
                    }
                }
            }

            if (latestValidSession == null)
            {
                return null;
            }

            return BuildRecordFromEvaluationSession(latestValidSession.FullName);
        }

        private static TreatmentRecordData BuildRecordFromEvaluationSession(string sessionDir)
        {
            string scorePath = Path.Combine(sessionDir, "score_result.json");
            string feedbackPath = Path.Combine(sessionDir, "teaching_feedback.json");

            ScoreResultJson score = ReadJsonFile<ScoreResultJson>(scorePath);
            TeachingFeedbackJson feedback = ReadJsonFile<TeachingFeedbackJson>(feedbackPath);

            return new TreatmentRecordData
            {
                caseId = !string.IsNullOrWhiteSpace(score?.task_id) ? score.task_id : Path.GetFileName(sessionDir),
                diagnosis = "暂无记录",
                playerNeedsPhotocoagulation = true,
                caseText = BuildScoreSummary(score),
                standardSpotImage = LoadSpriteFromPng(Path.Combine(sessionDir, "score_result_gt_overlay.png")),
                playerSpotImage = LoadSpriteFromPng(Path.Combine(sessionDir, "score_result_player_overlay.png")),
                advantages = !string.IsNullOrWhiteSpace(feedback?.advantage) ? NormalizeFeedbackText(feedback.advantage) : BuildRuleAdvantage(score),
                disadvantages = !string.IsNullOrWhiteSpace(feedback?.disadvantage) ? NormalizeFeedbackText(feedback.disadvantage) : BuildRuleDisadvantage(score),
                improvementAdvice = !string.IsNullOrWhiteSpace(feedback?.improvement) ? NormalizeFeedbackText(feedback.improvement) : BuildRuleImprovement(score)
            };
        }

        private static string[] GetEvaluationOutputRoots()
        {
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string projectOutput = Path.Combine(projectRoot, "EvaluationOutput", "unity_http");

            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string legacyLocalOutput = string.IsNullOrWhiteSpace(localAppData)
                ? string.Empty
                : Path.Combine(localAppData, "RetinalPhotocoagulation", "EvaluationOutput", "unity_http");

            // Prefer the project/exe-adjacent output. Keep LocalAppData as a
            // migration fallback for records generated before the path change.
            return new[] { projectOutput, legacyLocalOutput };
        }

        private static T ReadJsonFile<T>(string path) where T : class
        {
            if (!File.Exists(path))
            {
                return null;
            }

            try
            {
                return JsonUtility.FromJson<T>(File.ReadAllText(path));
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"Failed to parse record JSON: {path}\n{ex.Message}");
                return null;
            }
        }

        private static Sprite LoadSpriteFromPng(string path)
        {
            if (!File.Exists(path))
            {
                return null;
            }

            try
            {
                byte[] bytes = File.ReadAllBytes(path);
                Texture2D texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (!texture.LoadImage(bytes))
                {
                    UnityEngine.Object.Destroy(texture);
                    return null;
                }

                texture.wrapMode = TextureWrapMode.Clamp;
                return Sprite.Create(
                    texture,
                    new Rect(0, 0, texture.width, texture.height),
                    new Vector2(0.5f, 0.5f),
                    100f);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"Failed to load record image: {path}\n{ex.Message}");
                return null;
            }
        }

        private static string BuildScoreSummary(ScoreResultJson score)
        {
            if (score == null)
            {
                return "暂无评分记录";
            }

            return
                $"总分：{score.total_score:0.##}\n" +
                $"位置：{FormatScore(score.dimensions?.dim1_position)}\n" +
                $"参数：{FormatScore(score.dimensions?.dim2_energy)}\n" +
                $"密度：{FormatScore(score.dimensions?.dim3_density)}";
        }

        private static string BuildRuleAdvantage(ScoreResultJson score)
        {
            if (score == null)
            {
                return "暂无优点评估";
            }

            return $"真实评分已完成。总分 {score.total_score:0.##}。可结合右侧标准图与玩家图复盘。";
        }

        private static string BuildRuleDisadvantage(ScoreResultJson score)
        {
            if (score == null)
            {
                return "暂无缺点评估";
            }

            string pos = score.dimensions?.dim1_position?.eval_msg;
            string energy = score.dimensions?.dim2_energy?.eval_msg;
            string density = score.dimensions?.dim3_density?.eval_msg;
            return $"位置评价：{FallbackText(pos)}\n参数评价：{FallbackText(energy)}\n密度评价：{FallbackText(density)}";
        }

        private static string BuildRuleImprovement(ScoreResultJson score)
        {
            int overlap = score?.penalties?.overlap_penalty?.count ?? 0;
            int vessel = score?.penalties?.vessel_hit_penalty?.count ?? 0;
            return $"建议优先复盘低分维度，检查病灶边界覆盖、参数设置和打点密度。\n惩罚项：重叠 {overlap} 次，血管/危险区域命中 {vessel} 次。";
        }

        private static string FallbackText(string value)
        {
            return string.IsNullOrWhiteSpace(value) ? "暂无" : value;
        }

        private static string NormalizeFeedbackText(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return value;
            }

            string text = value.Trim();
            string[] prefixes =
            {
                "本次模拟的优点：",
                "本次模拟的优点:",
                "本次模拟的缺点：",
                "本次模拟的缺点:",
                "改进建议：",
                "改进建议:"
            };

            foreach (string prefix in prefixes)
            {
                if (text.StartsWith(prefix, StringComparison.Ordinal))
                {
                    return prefix.TrimEnd('：', ':') + "\n" + text.Substring(prefix.Length).TrimStart();
                }
            }

            return text;
        }

        private static string FormatScore(ScoreDimension dimension)
        {
            if (dimension == null)
            {
                return "暂无";
            }

            return $"{dimension.score:0.##}/{dimension.max_score:0.##}";
        }
        [Serializable]
        private sealed class TeachingFeedbackJson
        {
            public string advantage;
            public string disadvantage;
            public string improvement;
        }

        [Serializable]
        private sealed class ScoreResultJson
        {
            public string session_id;
            public string task_id;
            public float total_score;
            public ScoreDimensions dimensions;
            public ScorePenalties penalties;
        }

        [Serializable]
        private sealed class ScoreDimensions
        {
            public ScoreDimension dim1_position;
            public ScoreDimension dim2_energy;
            public ScoreDimension dim3_density;
        }

        [Serializable]
        private sealed class ScoreDimension
        {
            public float score;
            public float max_score;
            public string eval_msg;
        }

        [Serializable]
        private sealed class ScorePenalties
        {
            public ScorePenalty overlap_penalty;
            public ScorePenalty vessel_hit_penalty;
        }

        [Serializable]
        private sealed class ScorePenalty
        {
            public int count;
            public float deducted_points;
        }
    }
}


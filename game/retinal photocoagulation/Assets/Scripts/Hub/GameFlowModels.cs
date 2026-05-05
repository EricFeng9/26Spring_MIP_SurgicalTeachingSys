using System;
using System.Collections.Generic;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    [Serializable]
    public sealed class GameFlowPlayerInfo
    {
        public string id = "PLAYER_001";
        public string name = "Player";
    }

    [Serializable]
    public sealed class GameFlowTaskInfo
    {
        public string task_id;
        public int difficulty;
        public string disease_category;
        public string pre_op_image_path;
        public string pre_op_case_text;
        public int max_reputation_reward;
        public int max_money_reward;
    }

    [Serializable]
    public sealed class GameFlowConsultationDecision
    {
        public string task_id;
        public string player_id;
        public string player_name;
        public string selected_disease;
        public bool needs_photocoagulation;
    }

    [Serializable]
    public sealed class GameFlowLaserParams
    {
        public float power;
        public float spot_size;
        public float exposure_time;
        public float wavelength;
    }

    [Serializable]
    public sealed class GameFlowShot
    {
        public int id;
        public float[] pos;
        public bool is_trial;
        public int spot_grade;
        public GameFlowLaserParams params_data;

        // The evaluation sample uses "params". Unity JsonUtility cannot map a
        // field named params directly, so we replace the key during export.
        public string ToJson()
        {
            string json = JsonUtility.ToJson(this, true);
            return json.Replace("\"params_data\"", "\"params\"");
        }
    }

    [Serializable]
    public sealed class GameFlowPlayerShotsJson
    {
        public string session_id;
        public string task_id;
        public GameFlowPlayerInfo player_info;
        public List<GameFlowShot> shots = new List<GameFlowShot>();
    }

    [Serializable]
    public sealed class GameFlowEvaluationRequest
    {
        public string session_id;
        public string task_id;
        public GameFlowPlayerInfo player_info;
        public GameFlowConsultationDecision consultation;
        public GameFlowPlayerShotsJson player_json;
    }

    [Serializable]
    public sealed class GameFlowEvaluationResponse
    {
        public bool success;
        public string message;
        public float total_score;
        public string advantage;
        public string disadvantage;
        public string improvement;
        public string evaluation_mode;
        public string ai_feedback_status;
        public string scoring_output_path;
        public string teaching_feedback_path;
        public string standard_image_base64;
        public string player_image_base64;
        public string standard_image_path;
        public string player_image_path;
    }
}

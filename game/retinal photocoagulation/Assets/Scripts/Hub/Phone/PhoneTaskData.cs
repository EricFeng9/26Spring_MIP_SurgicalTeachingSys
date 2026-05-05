using System;
using System.Collections.Generic;
using UnityEngine;

namespace RetinalPrototype.Hub.Phone
{
    public enum PhoneSender
    {
        Patient = 0,
        Doctor = 1
    }

    [Serializable]
    public sealed class PhoneMessageData
    {
        public PhoneSender sender = PhoneSender.Patient;
        [TextArea(2, 8)] public string text;
        public Sprite image;
        public bool useImage;
    }

    [CreateAssetMenu(fileName = "PhoneTaskData", menuName = "RetinalPrototype/Hub/Phone Task Data")]
    public sealed class PhoneTaskData : ScriptableObject
    {
        [Header("Contact")]
        public string contactId = "patient_001";
        public string displayName = "患者 #001";
        public string remark = "线上问诊";
        public Sprite avatar;
        public string lastMessagePreview = "点击查看详情";

        [Header("Decision")]
        public bool requiresDecision = true;
        public string taskId = "TASK_001";
        public string diseaseCategory = "未分类";
        public string selectedDiseaseWhenAccepted = "未选择";
        public string yesSceneName;
        public string noSceneName;

        [Header("Conversation")]
        public List<PhoneMessageData> messages = new List<PhoneMessageData>();
    }
}

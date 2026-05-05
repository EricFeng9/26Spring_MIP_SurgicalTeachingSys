using System;
using System.Collections.Generic;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    [Serializable]
    public sealed class TreatmentRecordData
    {
        [Header("Pre-operation")]
        public string caseId = "病例#001";
        public string diagnosis = "未填写";
        public bool playerNeedsPhotocoagulation = true;
        [TextArea(3, 8)] public string caseText;
        public Sprite preOperationFundusImage;

        [Header("Treatment Result")]
        public Sprite standardSpotImage;
        public Sprite playerSpotImage;

        [Header("Analysis")]
        [TextArea(2, 6)] public string advantages;
        [TextArea(2, 6)] public string disadvantages;
        [TextArea(2, 6)] public string improvementAdvice;

        [Header("Parameter Detail")]
        public List<TreatmentParameterSnapshot> parameterSnapshots = new List<TreatmentParameterSnapshot>();
    }

    [Serializable]
    public sealed class TreatmentParameterSnapshot
    {
        public string title;
        public Sprite image;
        [TextArea(1, 4)] public string description;
    }
}

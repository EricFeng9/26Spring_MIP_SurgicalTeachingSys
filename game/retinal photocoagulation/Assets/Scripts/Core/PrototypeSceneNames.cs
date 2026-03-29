using System.Collections.Generic;

namespace RetinalPrototype
{
    public static class PrototypeSceneNames
    {
        public const string MainMenu = "MainMenu";
        public const string SaveSelect = "SaveSelect";
        public const string DevTeam = "DevTeam";
        public const string Settings = "Settings";

        public const string InGameComputer = "InGameComputer";
        public const string Desktop = "Desktop";
        public const string GuidanceDiabeticRetinopathy = "Guidance_DiabeticRetinopathy";
        public const string GuidanceRetinalVeinOcclusion = "Guidance_RetinalVeinOcclusion";
        public const string GuidanceRetinalTear = "Guidance_RetinalTear";
        public const string GuidanceMacularEdema = "Guidance_MacularEdema";
        public const string HistoryRecords = "HistoryRecords";
        public const string OrderPlatform = "OrderPlatform";

        public const string SurgerySimulation = "SurgerySimulation";
        public const string LaserParameterUI = "LaserParameterUI";
        public const string SurgicalFieldView = "SurgicalFieldView";
        public const string FundusImaging = "FundusImaging";
        public const string SpotSimulation = "SpotSimulation";

        public const string TreatmentReport = "TreatmentReport";
        public const string DeviceAndPatient = "DeviceAndPatient";

        public static IReadOnlyList<string> AllScenes => _allScenes;

        private static readonly string[] _allScenes =
        {
            MainMenu,
            SaveSelect,
            DevTeam,
            Settings,
            InGameComputer,
            Desktop,
            GuidanceDiabeticRetinopathy,
            GuidanceRetinalVeinOcclusion,
            GuidanceRetinalTear,
            GuidanceMacularEdema,
            HistoryRecords,
            OrderPlatform,
            SurgerySimulation,
            LaserParameterUI,
            SurgicalFieldView,
            FundusImaging,
            SpotSimulation,
            TreatmentReport,
            DeviceAndPatient
        };
    }
}

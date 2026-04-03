using UnityEngine;

[CreateAssetMenu(fileName = "NewCaseData", menuName = "Hospital/Case Data")]
public class CaseData : ScriptableObject
{
    [Header("接诊大厅显示信息 (Task Card)")]
    public string CaseID;           // 案例ID：例如 Case-#1042
    [TextArea(3, 10)]
    public string PatientSymptoms;  // 主诉症状: "眼前有黑影飘动"
    [Range(1, 5)]
    public int ExpectedDifficulty;  // 预估难度: 1-5星 (整型)
    public int ConsultationFee;     // 接诊费 (基础奖励)
    public int MaxSurgeryFee;       // 手术费预估 (潜在收益)
    public int ExpectedReputation;  // 预期声望 (完成该案例的学术声望)

    public int RequiredReputation;  // 接取该案例需要的最低声望等级 (可选)

    [Header("诊断室详细信息 (Diagnostic Window)")]
    [TextArea(10, 20)]
    public string DetailedMedicalRecord; // 详细病历文本
    public Sprite FundusImage;           // 术前眼底图像

    [Header("真实病情判定 (后台逻辑，隐藏数据)")]
    public bool ActuallyNeedsSurgery;    // 核心判定：是否真的需要手术？
    [TextArea]
    public string TrueDiagnosis;         // 真实的诊断结果（用于结算界面展示给玩家看）
}
using UnityEngine;
using TMPro; // 如果需要直接更新UI
using System.Collections.Generic;
using UnityEngine.UI;
using UnityEditor.UI;

public class GameDataManager : MonoBehaviour
{
    public static GameDataManager Instance { get; private set; }

    [Header("玩家属性")]
    [SerializeField] private int currentMoney = 1000;
    [SerializeField] private int currentReputation = 0;

    // 引用UI Text用于实时更新
    [Header("UI 引用")]
    public TextMeshProUGUI moneyText;
    public TextMeshProUGUI reputationText;

    private void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject); // 跨场景保留
        }
        else
        {
            Destroy(gameObject);
        }
    }

    private void Start()
    {
        UpdateUI();
    }

    public int GetMoney() => currentMoney;
    public int GetReputation() => currentReputation;

    // 增加/扣除声望的方法
    public void AddReputation(int amount)
    {
        currentReputation += amount;
        if (currentReputation < 0) currentReputation = 0; // 声望不能为负
        UpdateUI();
        // 触发一个事件，通知任务系统重新检查解锁状态
    }

    // 增加/扣除金钱的方法
    public void AddMoney(int amount)
    {
        currentMoney += amount;
        UpdateUI();
    }

    private void UpdateUI()
    {
        if (moneyText != null) moneyText.text = currentMoney.ToString();
        if (reputationText != null) reputationText.text = currentReputation.ToString();
    }

    [Header("病例管理")]
    public List<CaseData> activeCases = new List<CaseData>();  // 诊疗中
    public List<CaseData> historyCases = new List<CaseData>(); // 已诊疗

    // 当玩家在揭榜界面点击“接取”时调用此方法
    public void AcceptNewCase(CaseData newCase)
    {
        if (!activeCases.Contains(newCase))
        {
            activeCases.Add(newCase);
            // 这里可以扣除时间/精力等
        }
    }

    // 当玩家完成诊断或手术后调用此方法，将病例移入历史记录
    public void MoveCaseToHistory(CaseData completedCase)
    {
        if (activeCases.Contains(completedCase))
        {
            activeCases.Remove(completedCase);
            historyCases.Add(completedCase);
        }
    }

    public void CompleteSurgery(CaseData data, bool isSuccess)
    {
        if (isSuccess)
        {
            // 增加手术费
            AddMoney(data.MaxSurgeryFee);
            // 增加声望
            AddReputation(data.ExpectedReputation);
            Debug.Log("手术成功！奖励已发放。");
        }
        else
        {
            // 手术失败的逻辑（比如只给一半钱，或者扣声望）
            AddReputation(-10); 
            Debug.Log("手术失败，扣除声望。");
        }
        
        // 这里可以标记该 CaseData 为“已完成”状态，方便诊疗记录显示
    }
}
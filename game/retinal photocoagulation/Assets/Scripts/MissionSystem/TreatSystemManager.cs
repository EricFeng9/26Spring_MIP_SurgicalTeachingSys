using UnityEngine;
using System.Collections.Generic;
using UnityEngine.UI;
using UnityEngine.Events;

public class TreatSystemManager : MonoBehaviour
{
    [Header("任务配置数据")]
    public List<CaseData> allCases; // 拖入所有的CaseData ScriptableObjects

    [Header("UI 引用")]
    public GameObject taskCardPrefab; // 拖入你的 TaskCard_Prefab
    public Transform taskScrollContent; // 拖入 Scroll View 的 Content 节点

    [Header("事件 (逻辑拓展)")]
    // 定义一个事件，当案例被接取时触发，传递 CaseData 数据
    public UnityEvent<CaseData> OnCaseAccepted; 

    private void OnEnable()
    {
        // 界面每次打开时重新刷新任务列表
        RefreshTaskList();
    }

    private void RefreshTaskList()
    {
        // 1. 清除旧的卡片
        foreach (Transform child in taskScrollContent)
        {
            Destroy(child.gameObject);
        }

        // 2. 根据声望高低对任务进行排序（可选：低难度任务排在前面）
        allCases.Sort((a, b) => a.ExpectedDifficulty.CompareTo(b.ExpectedDifficulty));

        // 3. 实例化卡片
        foreach (CaseData data in allCases)
        {
            GameObject cardGO = Instantiate(taskCardPrefab, taskScrollContent);
            TaskCard card = cardGO.GetComponent<TaskCard>();
            
            if (card != null)
            {
                card.Setup(data, this); // 将自己传递过去，处理接取事件
            }
        }
    }

    // 处理接取任务的逻辑 (由 TaskCard 调用)
    public void AcceptCase(CaseData data){
        Debug.Log("成功接取案例: " + data.CaseID);
        
        // 1. 从“可接取列表”中移除该数据，防止重复出现
        if (allCases.Contains(data))
        {
            allCases.Remove(data);
        }

        // 2. 支付基础接诊费（金钱增加）
        GameDataManager.Instance.AddMoney(data.ConsultationFee);

        // 3. 将此任务存入“诊疗记录”
        GameDataManager.Instance.AcceptNewCase(data);

        // 4. 触发事件（用于跳转场景或记录当前正在进行的手术）
        if (OnCaseAccepted != null)
        {
            OnCaseAccepted.Invoke(data);
        }

        // 5. 立即刷新 UI：重新生成列表，被移除的卡片自然消失，顺位补充
        RefreshTaskList();

        // 6. 如果你希望接完一个就关闭界面：
        // gameObject.SetActive(false); 
    }
}
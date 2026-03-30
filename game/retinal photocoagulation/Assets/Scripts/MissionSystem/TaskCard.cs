using UnityEngine;
using TMPro;
using UnityEngine.UI;
using System.Collections.Generic;

public class TaskCard : MonoBehaviour
{
    [Header("UI 元素引用")]
    public TextMeshProUGUI textID;
    public TextMeshProUGUI textSymptoms;
    public List<Image> starImages; // 拖入5个星星的Image组件引用
    public TextMeshProUGUI textMoney;
    public TextMeshProUGUI textRep;
    public Button acceptButton;

    public TextMeshProUGUI textRequiredRep; // 可选：显示任务需要的声望等级

    // 缓存星星的亮/暗精灵图
    private Sprite starFullSprite;
    private Sprite starEmptySprite;

    private CaseData myData;
    private TreatSystemManager myManager;

    private void Awake()
    {
        // 建议在 Awake 中加载星星精灵，或者在 Setup 中传入
        // 这里假设已经在 Prefab Inspector 中设置好了默认的亮星材质，
        // 我们只需通过代码控制暗星。
        // 为了方便演示，这里提供一个直接在 Setup 改变材质的方法。
    }

    public void Setup(CaseData data, TreatSystemManager manager)
    {
        myData = data;
        myManager = manager;

        // 1. 填充文本数据
        if (textID != null) textID.text = data.CaseID;
        if (textSymptoms != null) textSymptoms.text = data.PatientSymptoms;
        
        // 显示一个预估金钱范围 (预估难度 * 金钱系数) 或者直接显示预估手术费
        if (textMoney != null) textMoney.text = "+" + (data.ConsultationFee + data.MaxSurgeryFee).ToString(); 
        
        if (textRep != null) textRep.text = "+" + data.ExpectedReputation.ToString();

        if (textRequiredRep != null) textRequiredRep.text = data.RequiredReputation.ToString();

        // 2. 设置难度星级 (没有半星)
        for (int i = 0; i < starImages.Count; i++)
        {
            // 如果任务难度是3，则 i=0,1,2 时星星点亮 (亮白色)，i=3,4 时星星熄灭 (暗灰色)
            if (i < data.ExpectedDifficulty)
            {
                starImages[i].color = Color.white; // 亮星
            }
            else
            {
                starImages[i].color = new Color(0.5f, 0.5f, 0.5f, 0.5f); // 暗星（灰色，半透明）
            }
        }

        // 3. 根据声望判断是否置灰卡片 (可选的解锁机制)
        int playerRep = GameDataManager.Instance.GetReputation();
        if (playerRep < data.RequiredReputation) // 需要在CaseData中增加RequiredReputation字段
        {
            // 置灰卡片
            GetComponent<Image>().color = new Color(0.5f, 0.5f, 0.5f, 0.5f); // 整体变灰
            acceptButton.interactable = false; // 禁止点击
            if (textRequiredRep != null)
            {
                textRequiredRep.text = data.RequiredReputation.ToString();
                textRequiredRep.color = Color.red; // 红色提示需要的声望等级
                textRequiredRep.gameObject.SetActive(true);
            }
        }
        else
        {
            // 正常显示
            GetComponent<Image>().color = Color.white;
            acceptButton.interactable = true;
            if (textRequiredRep != null)
            {

                textRequiredRep.gameObject.SetActive(true);
            }
        }
    }

    // 绑定在按钮 onClick 事件上的方法
    public void OnAcceptButtonClick()
    {
        if (myManager != null && myData != null)
        {
            myManager.AcceptCase(myData);
        }
    }
}
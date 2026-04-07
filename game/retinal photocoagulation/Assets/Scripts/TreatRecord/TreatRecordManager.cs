using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections.Generic;
using UnityEngine.SceneManagement;

public class TreatRecordManager : MonoBehaviour
{
    [Header("UI 引用 - 中栏")]
    public Transform middleContent; // 拖入中栏的 Content
    public GameObject caseListItemPrefab;
    public GameObject middleColumnPanel; // 拖入 MiddleColumn 节点

    [Header("UI 引用 - 右栏动态文本")]
    public GameObject rightColumnPanel; // 拖入 RightColumn 节点
    public TextMeshProUGUI caseIDLabel;    // 拖入 CaseID_Label
    public TextMeshProUGUI bodyText_Chief; // 拖入 ChiefComplaint 下的 BodyText
    public TextMeshProUGUI text_Body_PE;   // 拖入 PhysicalExam 下的 Text_Body
    public Image fundusImagePanel;         // 拖入 FundusImagePanel (如果它是 Image 的话)

    [Header("UI 引用 - 右栏操作区")]
    public TMP_Dropdown dropdownDiagnosis; // 拖入 Dropdown_Diagnosis
    public Button btnSurgeryYes;           // 拖入 Btn_SurgeryYes
    public Button btnSurgeryNo;            // 拖入 Btn_SurgeryNo

    [Header("场景跳转")]
    public string surgerySceneName = "ComputerScreen";

    private CaseData currentSelectedCase;

    private void OnEnable()
    {
        middleColumnPanel.SetActive(false);
        rightColumnPanel.SetActive(false);
    }

    public void OnClickActiveCases()
    {
        middleColumnPanel.SetActive(true);
        rightColumnPanel.SetActive(false);
        PopulateMiddleList(GameDataManager.Instance.activeCases, true);
    }

    public void OnClickHistoryCases()
    {
        middleColumnPanel.SetActive(true);
        rightColumnPanel.SetActive(false);
        PopulateMiddleList(GameDataManager.Instance.historyCases, false);
    }

    private void PopulateMiddleList(List<CaseData> cases, bool isActiveList)
    {
        foreach (Transform child in middleContent) { Destroy(child.gameObject); }

        foreach (CaseData data in cases)
        {
            GameObject itemGO = Instantiate(caseListItemPrefab, middleContent);
            TextMeshProUGUI itemText = itemGO.GetComponentInChildren<TextMeshProUGUI>();
            if (itemText != null) itemText.text = data.CaseID;
            
            Button btn = itemGO.GetComponent<Button>();
            btn.onClick.AddListener(() => OnCaseListItemClicked(data, isActiveList));
        }
    }

    private void OnCaseListItemClicked(CaseData data, bool isActiveList)
    {
        currentSelectedCase = data;
        rightColumnPanel.SetActive(true);

        // 匹配你的 Hierarchy 节点赋值
        if(caseIDLabel != null) caseIDLabel.text = "Case ID: " + data.CaseID;
        if(bodyText_Chief != null) bodyText_Chief.text = data.PatientSymptoms;
        if(text_Body_PE != null) text_Body_PE.text = data.DetailedMedicalRecord;
        if(fundusImagePanel != null) fundusImagePanel.sprite = data.FundusImage;

        if(dropdownDiagnosis != null) dropdownDiagnosis.interactable = isActiveList;
        if(btnSurgeryYes != null) btnSurgeryYes.gameObject.SetActive(isActiveList);
        if(btnSurgeryNo != null) btnSurgeryNo.gameObject.SetActive(isActiveList);
    }

    public void OnConfirmSurgeryClick()
    {
        Debug.Log("进入手术逻辑");
        if (string.IsNullOrWhiteSpace(surgerySceneName))
        {
            Debug.LogError("未配置手术场景名，请在 Inspector 中设置 surgerySceneName。");
            return;
        }

        SceneManager.LoadScene(surgerySceneName);
    }

    public void OnNoSurgeryClick()
    {
        Debug.Log("无需手术，归档");
        GameDataManager.Instance.MoveCaseToHistory(currentSelectedCase);
        OnClickActiveCases(); 
    }
}
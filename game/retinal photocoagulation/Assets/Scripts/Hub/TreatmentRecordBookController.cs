using TMPro;
using System.Collections;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    public sealed class TreatmentRecordBookController : MonoBehaviour
    {
        [Header("Root")]
        [SerializeField] private GameObject panelRoot;
        [SerializeField] private bool loadLatestRecordOnEnable = true;

        [Header("Left Page")]
        [SerializeField] private TMP_Text caseIdText;
        [SerializeField] private RecordTextSlot diagnosisText;
        [SerializeField] private RecordTextSlot photocoagulationDecisionText;
        [SerializeField] private RecordImageSlot preOperationImage;
        [SerializeField] private RecordTextSlot caseText;

        [Header("Right Page")]
        [SerializeField] private RecordImageSlot standardSpotImage;
        [SerializeField] private RecordImageSlot playerSpotImage;
        [SerializeField] private RecordTextSlot advantagesText;
        [SerializeField] private RecordTextSlot disadvantagesText;
        [SerializeField] private RecordTextSlot improvementAdviceText;
        [SerializeField] private bool shareFeedbackFontSize = true;

        [Header("Parameter Panel")]
        [SerializeField] private TreatmentParameterPanelController parameterPanel;

        [Header("Fallback Preview Data")]
        [SerializeField] private bool useFallbackWhenNoRuntimeRecord = false;
        [SerializeField] private TreatmentRecordData fallbackRecord = new TreatmentRecordData();

        private TreatmentRecordData _currentRecord;

        private void OnEnable()
        {
            if (loadLatestRecordOnEnable)
            {
                LoadLatestRecord();
            }
        }

        public void Open()
        {
            if (panelRoot != null)
            {
                panelRoot.SetActive(true);
            }

            LoadLatestRecord();
        }

        public void Close()
        {
            if (panelRoot != null)
            {
                panelRoot.SetActive(false);
            }
        }

        public void LoadLatestRecord()
        {
            TreatmentRecordData record = TreatmentRecordStore.GetLatest();
            if (record == null && useFallbackWhenNoRuntimeRecord)
            {
                record = fallbackRecord;
            }

            ApplyRecord(record);
        }

        public void ApplyRecord(TreatmentRecordData record)
        {
            _currentRecord = record;

            if (_currentRecord == null)
            {
                ApplyEmptyRecord();
                return;
            }

            if (caseIdText != null)
            {
                caseIdText.text = string.IsNullOrWhiteSpace(_currentRecord.caseId) ? "病例#---" : _currentRecord.caseId;
            }

            if (diagnosisText != null)
            {
                diagnosisText.SetText(_currentRecord.diagnosis);
            }

            if (photocoagulationDecisionText != null)
            {
                photocoagulationDecisionText.SetText(_currentRecord.playerNeedsPhotocoagulation ? "是" : "否");
            }

            if (preOperationImage != null)
            {
                preOperationImage.SetSprite(_currentRecord.preOperationFundusImage);
            }

            if (caseText != null)
            {
                caseText.SetText(_currentRecord.caseText);
            }

            if (standardSpotImage != null)
            {
                standardSpotImage.SetSprite(_currentRecord.standardSpotImage);
            }

            if (playerSpotImage != null)
            {
                playerSpotImage.SetSprite(_currentRecord.playerSpotImage);
            }

            if (advantagesText != null)
            {
                advantagesText.SetText(_currentRecord.advantages);
            }

            if (disadvantagesText != null)
            {
                disadvantagesText.SetText(_currentRecord.disadvantages);
            }

            if (improvementAdviceText != null)
            {
                improvementAdviceText.SetText(_currentRecord.improvementAdvice);
            }

            SyncFeedbackFontSizeNextFrame();

            if (parameterPanel != null)
            {
                parameterPanel.SetSnapshots(_currentRecord.parameterSnapshots);
            }
        }

        public void OpenParameterPanel()
        {
            if (parameterPanel != null)
            {
                parameterPanel.Open();
            }
        }

        private void ApplyEmptyRecord()
        {
            if (caseIdText != null)
            {
                caseIdText.text = "病例#---";
            }

            diagnosisText?.SetText("暂无诊断记录");
            photocoagulationDecisionText?.SetText("暂无判断记录");
            preOperationImage?.SetSprite(null);
            caseText?.SetText("暂无病例文本");
            standardSpotImage?.SetSprite(null);
            playerSpotImage?.SetSprite(null);
            advantagesText?.SetText("暂无优点分析");
            disadvantagesText?.SetText("暂无缺点分析");
            improvementAdviceText?.SetText("暂无改进建议");
            SyncFeedbackFontSizeNextFrame();
            parameterPanel?.SetSnapshots(null);
        }

        private void SyncFeedbackFontSizeNextFrame()
        {
            if (!shareFeedbackFontSize || !isActiveAndEnabled)
            {
                return;
            }

            StartCoroutine(SyncFeedbackFontSizeRoutine());
        }

        private IEnumerator SyncFeedbackFontSizeRoutine()
        {
            yield return null;
            Canvas.ForceUpdateCanvases();

            float minSize = float.MaxValue;
            minSize = IncludeResolvedSize(advantagesText, minSize);
            minSize = IncludeResolvedSize(disadvantagesText, minSize);
            minSize = IncludeResolvedSize(improvementAdviceText, minSize);

            if (minSize == float.MaxValue || minSize <= 0f)
            {
                yield break;
            }

            advantagesText?.SetSharedFontSize(minSize);
            disadvantagesText?.SetSharedFontSize(minSize);
            improvementAdviceText?.SetSharedFontSize(minSize);
        }

        private static float IncludeResolvedSize(RecordTextSlot slot, float currentMin)
        {
            if (slot == null)
            {
                return currentMin;
            }

            float size = slot.GetResolvedFontSize();
            return size > 0f ? Mathf.Min(currentMin, size) : currentMin;
        }
    }
}

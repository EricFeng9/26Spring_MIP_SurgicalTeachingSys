using System.Collections;
using UnityEngine;
using UnityEngine.Events;

namespace RetinalPrototype.Hub
{
    public sealed class SurgeryEvaluationSubmitter : MonoBehaviour
    {
        [SerializeField] private EvaluationApiClient apiClient;
        [SerializeField] private Sprite fallbackStandardImage;
        [SerializeField] private Sprite fallbackPlayerImage;

        [Header("Events")]
        [SerializeField] private UnityEvent onSubmitStarted;
        [SerializeField] private UnityEvent onSubmitSucceeded;
        [SerializeField] private UnityEvent onSubmitFailed;

        private bool _isSubmitting;

        public void Submit()
        {
            if (_isSubmitting)
            {
                return;
            }

            if (apiClient == null)
            {
                apiClient = FindFirstObjectByType<EvaluationApiClient>();
            }

            if (apiClient == null)
            {
                Debug.LogWarning("No EvaluationApiClient found. Building fallback treatment record only.");
                ApplyFallbackRecord("未连接后端评分接口。", "暂无后端缺点分析。", "请先配置 EvaluationApiClient.apiUrl。");
                onSubmitFailed?.Invoke();
                return;
            }

            StartCoroutine(SubmitRoutine());
        }

        private IEnumerator SubmitRoutine()
        {
            _isSubmitting = true;
            onSubmitStarted?.Invoke();

            bool done = false;
            GameFlowEvaluationResponse response = null;
            string error = null;

            yield return apiClient.SubmitCurrentSession(
                result =>
                {
                    response = result;
                    done = true;
                },
                err =>
                {
                    error = err;
                    done = true;
                });

            while (!done)
            {
                yield return null;
            }

            if (response != null && response.success)
            {
                ApplyResponseRecord(response);
                onSubmitSucceeded?.Invoke();
            }
            else
            {
                Debug.LogWarning("Evaluation submit failed: " + error);
                if (!string.IsNullOrWhiteSpace(error) && error.Contains("Skipped legacy GameFlowSession"))
                {
                    // The active surgery scene exports real evaluation files.
                    // Do not overwrite the record book with this legacy empty-session failure.
                    onSubmitFailed?.Invoke();
                    _isSubmitting = false;
                    yield break;
                }

                ApplyFallbackRecord(
                    "评分请求失败，但已保留本次手术记录。",
                    error,
                    "检查后端 API 是否启动，或使用本地 debug JSON 进行离线评估。"
                );
                onSubmitFailed?.Invoke();
            }

            _isSubmitting = false;
        }

        private void ApplyResponseRecord(GameFlowEvaluationResponse response)
        {
            var session = GameFlowSession.Instance;
            TreatmentRecordStore.SaveLatest(new TreatmentRecordData
            {
                caseId = session.CurrentTask.task_id,
                diagnosis = session.ConsultationDecision.selected_disease,
                playerNeedsPhotocoagulation = session.ConsultationDecision.needs_photocoagulation,
                caseText = session.CurrentTask.pre_op_case_text,
                standardSpotImage = fallbackStandardImage,
                playerSpotImage = fallbackPlayerImage,
                advantages = response.advantage,
                disadvantages = response.disadvantage,
                improvementAdvice = response.improvement
            });
        }

        private void ApplyFallbackRecord(string advantage, string disadvantage, string improvement)
        {
            var session = GameFlowSession.Instance;
            TreatmentRecordStore.SaveLatest(new TreatmentRecordData
            {
                caseId = session.CurrentTask.task_id,
                diagnosis = session.ConsultationDecision.selected_disease,
                playerNeedsPhotocoagulation = session.ConsultationDecision.needs_photocoagulation,
                caseText = session.CurrentTask.pre_op_case_text,
                standardSpotImage = fallbackStandardImage,
                playerSpotImage = fallbackPlayerImage,
                advantages = advantage,
                disadvantages = disadvantage,
                improvementAdvice = improvement
            });
        }
    }
}

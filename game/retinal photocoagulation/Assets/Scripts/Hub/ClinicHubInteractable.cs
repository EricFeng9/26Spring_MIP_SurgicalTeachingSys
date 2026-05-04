using System.Collections;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;

namespace RetinalPrototype.Hub
{
    public enum ClinicHubAction
    {
        Idle = 0,
        Walk = 1,
        Microwave = 2,
        Surgery = 3,
        Documenting = 4,
        Sit = 5
    }

    public sealed class ClinicHubInteractable : MonoBehaviour, IClinicHubInteractable
    {
        [Header("UI")]
        [SerializeField] private string promptText = "[E] Interact";

        [Header("Interaction")]
        [SerializeField] private ClinicHubAction enterAction = ClinicHubAction.Idle;
        [SerializeField] private bool lockMovementDuringInteraction = true;
        [SerializeField] private float preActionDelay = 0.2f;
        [SerializeField] private float postActionDelay = 0.3f;
        [SerializeField] private bool clearActionAfterInteraction = true;

        [Header("Optional Snap")]
        [SerializeField] private Transform snapPoint;
        [SerializeField] private bool forceFacingOnSnap;
        [SerializeField] private bool snapFacingRight = true;

        [Header("Scene Transition")]
        [SerializeField] private string targetSceneName;
        [SerializeField] private bool savePlayerReturnPose = true;
        [SerializeField] private ClinicHubLoadingOverlayController loadingOverlay;
        [SerializeField] private SceneTransitionController sceneTransition;

        [Header("Events")]
        [SerializeField] private UnityEvent onInteractionStart;
        [SerializeField] private UnityEvent onInteractionExecuted;
        [SerializeField] private UnityEvent onInteractionEnd;

        private bool _isBusy;

        public string PromptText => promptText;

        public bool CanInteract(ClinicHubPlayerController player)
        {
            return player != null && !_isBusy && isActiveAndEnabled;
        }

        public bool TryInteract(ClinicHubPlayerController player)
        {
            if (!CanInteract(player))
            {
                return false;
            }

            StartCoroutine(InteractionRoutine(player));
            return true;
        }

        private IEnumerator InteractionRoutine(ClinicHubPlayerController player)
        {
            _isBusy = true;
            onInteractionStart?.Invoke();

            if (snapPoint != null)
            {
                player.SnapTo(snapPoint.position);
            }

            if (forceFacingOnSnap)
            {
                player.SetFacingRight(snapFacingRight);
            }

            if (lockMovementDuringInteraction)
            {
                player.SetInputLocked(true);
            }

            player.SetAction(enterAction);

            if (preActionDelay > 0f)
            {
                yield return new WaitForSeconds(preActionDelay);
            }

            onInteractionExecuted?.Invoke();

            if (!string.IsNullOrEmpty(targetSceneName))
            {
                if (savePlayerReturnPose)
                {
                    ClinicHubReturnState.SavePose(player.transform.position, player.IsFacingRight());
                }

                if (loadingOverlay != null)
                {
                    loadingOverlay.LoadScene(targetSceneName, enterAction);
                }
                else if (sceneTransition != null)
                {
                    sceneTransition.LoadScene(targetSceneName);
                }
                else
                {
                    SceneManager.LoadScene(targetSceneName);
                }

                yield break;
            }

            if (postActionDelay > 0f)
            {
                yield return new WaitForSeconds(postActionDelay);
            }

            if (clearActionAfterInteraction)
            {
                player.SetAction(ClinicHubAction.Idle);
            }

            if (lockMovementDuringInteraction)
            {
                player.SetInputLocked(false);
            }

            onInteractionEnd?.Invoke();
            _isBusy = false;
        }
    }
}

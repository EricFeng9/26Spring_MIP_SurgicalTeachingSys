using System.Collections;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;

namespace RetinalPrototype.Hub
{
    public enum ClinicHubPose
    {
        None = 0,
        Seated = 1,
        Operating = 2,
        Microwave = 3,
        Cabinet = 4
    }

    public sealed class ClinicHubInteractable : MonoBehaviour, IClinicHubInteractable
    {
        [Header("UI")]
        [SerializeField] private string promptText = "[E] 交互";

        [Header("Interaction")]
        [SerializeField] private ClinicHubPose enterPose = ClinicHubPose.None;
        [SerializeField] private bool lockMovementDuringInteraction = true;
        [SerializeField] private float preActionDelay = 0.2f;
        [SerializeField] private float postActionDelay = 0.3f;
        [SerializeField] private bool clearPoseAfterAction = true;

        [Header("Optional Snap")]
        [SerializeField] private Transform snapPoint;
        [SerializeField] private bool snapFacingRight;
        [SerializeField] private bool forceFacingOnSnap;

        [Header("Scene Transition")]
        [SerializeField] private string targetSceneName;
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

            player.SetPose(enterPose);
            if (preActionDelay > 0f)
            {
                yield return new WaitForSeconds(preActionDelay);
            }

            onInteractionExecuted?.Invoke();

            if (!string.IsNullOrEmpty(targetSceneName))
            {
                if (sceneTransition != null)
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

            if (clearPoseAfterAction)
            {
                player.SetPose(ClinicHubPose.None);
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

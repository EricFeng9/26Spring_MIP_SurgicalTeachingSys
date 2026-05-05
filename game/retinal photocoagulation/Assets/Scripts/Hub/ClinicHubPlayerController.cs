using System.Collections.Generic;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    [RequireComponent(typeof(Rigidbody2D))]
    public sealed class ClinicHubPlayerController : MonoBehaviour
    {
        [Header("Movement")]
        [SerializeField] private float moveSpeed = 2.5f;
        [SerializeField] private bool useRawInput = true;

        [Header("Components")]
        [SerializeField] private Rigidbody2D rb;
        [SerializeField] private Animator animator;
        [SerializeField] private SpriteRenderer spriteRenderer;
        [SerializeField] private ClinicHubPromptUI promptUI;

        [Header("Input")]
        [SerializeField] private KeyCode interactKey = KeyCode.E;

        [Header("Animation Parameter Names")]
        [SerializeField] private string speedParam = "Speed";
        [SerializeField] private string actionStateParam = "ActionState";
        [SerializeField] private string isInteractingParam = "IsInteracting";

        [Header("Legacy Bool Params (Optional)")]
        [SerializeField] private string isSittingParam = "IsSitting";
        [SerializeField] private string isOperatingParam = "IsOperating";

        private readonly List<IClinicHubInteractable> _nearby = new List<IClinicHubInteractable>();
        private IClinicHubInteractable _current;
        private Vector2 _moveInput;
        private bool _inputLocked;
        private bool _facingRight = true;
        private ClinicHubAction _forcedAction = ClinicHubAction.Idle;

        private void Reset()
        {
            rb = GetComponent<Rigidbody2D>();
            animator = GetComponentInChildren<Animator>();
            spriteRenderer = GetComponentInChildren<SpriteRenderer>();
        }

        private void Awake()
        {
            if (rb == null)
            {
                rb = GetComponent<Rigidbody2D>();
            }

            rb.gravityScale = 0f;
            rb.freezeRotation = true;

            ClinicHubReturnState.ConsumePose(this);
        }

        private void Update()
        {
            UpdateMoveInput();
            RefreshCurrentInteractable();
            UpdatePrompt();

            if (Input.GetKeyDown(interactKey) && _current != null)
            {
                _current.TryInteract(this);
            }
        }

        private void FixedUpdate()
        {
            var velocity = rb.velocity;
            velocity.x = _inputLocked ? 0f : (_moveInput.x * moveSpeed);
            velocity.y = 0f;
            rb.velocity = velocity;

            UpdateFacing(velocity.x);
            UpdateAnimator(velocity.x);
        }

        private void OnTriggerEnter2D(Collider2D other)
        {
            var interactable = ResolveInteractable(other);
            if (interactable == null || _nearby.Contains(interactable))
            {
                return;
            }

            _nearby.Add(interactable);
        }

        private void OnTriggerExit2D(Collider2D other)
        {
            var interactable = ResolveInteractable(other);
            if (interactable == null)
            {
                return;
            }

            _nearby.Remove(interactable);
            if (_current == interactable)
            {
                _current = null;
            }
        }

        public void SetInputLocked(bool locked)
        {
            _inputLocked = locked;
            if (locked)
            {
                rb.velocity = Vector2.zero;
            }
        }

        public void SetAction(ClinicHubAction action)
        {
            _forcedAction = action;
        }

        public void SnapTo(Vector3 worldPosition)
        {
            transform.position = new Vector3(worldPosition.x, worldPosition.y, transform.position.z);
            rb.position = new Vector2(transform.position.x, transform.position.y);
            rb.velocity = Vector2.zero;
        }

        public void SetFacingRight(bool facingRight)
        {
            _facingRight = facingRight;
            if (spriteRenderer != null)
            {
                spriteRenderer.flipX = !_facingRight;
            }
        }

        public bool IsFacingRight()
        {
            return _facingRight;
        }

        private void UpdateMoveInput()
        {
            if (_inputLocked)
            {
                _moveInput = Vector2.zero;
                return;
            }

            float horizontal = useRawInput ? Input.GetAxisRaw("Horizontal") : Input.GetAxis("Horizontal");
            _moveInput = new Vector2(Mathf.Clamp(horizontal, -1f, 1f), 0f);
        }

        private void UpdateFacing(float velocityX)
        {
            if (Mathf.Abs(velocityX) < 0.01f)
            {
                return;
            }

            SetFacingRight(velocityX > 0f);
        }

        private void UpdateAnimator(float velocityX)
        {
            if (animator == null)
            {
                return;
            }

            float absSpeed = Mathf.Abs(velocityX);
            ClinicHubAction resolvedAction = _forcedAction;
            if (_forcedAction == ClinicHubAction.Idle && absSpeed > 0.01f)
            {
                resolvedAction = ClinicHubAction.Walk;
            }

            animator.SetFloat(speedParam, absSpeed);
            animator.SetInteger(actionStateParam, (int)resolvedAction);
            animator.SetBool(isInteractingParam, resolvedAction != ClinicHubAction.Idle && resolvedAction != ClinicHubAction.Walk);

            // Backward compatibility if your current controller still uses bools.
            animator.SetBool(isSittingParam, resolvedAction == ClinicHubAction.Sit);
            animator.SetBool(
                isOperatingParam,
                resolvedAction == ClinicHubAction.Surgery ||
                resolvedAction == ClinicHubAction.Microwave ||
                resolvedAction == ClinicHubAction.Documenting
            );
        }

        private void RefreshCurrentInteractable()
        {
            _nearby.RemoveAll(item => item == null);
            if (_nearby.Count == 0)
            {
                _current = null;
                return;
            }

            float minDistance = float.MaxValue;
            IClinicHubInteractable best = null;
            var currentPos = transform.position;

            for (int i = 0; i < _nearby.Count; i++)
            {
                var candidate = _nearby[i];
                if (candidate == null || !candidate.CanInteract(this))
                {
                    continue;
                }

                var candidateMono = candidate as MonoBehaviour;
                if (candidateMono == null)
                {
                    continue;
                }

                float dist = Vector2.SqrMagnitude(candidateMono.transform.position - currentPos);
                if (dist < minDistance)
                {
                    minDistance = dist;
                    best = candidate;
                }
            }

            _current = best;
        }

        private void UpdatePrompt()
        {
            if (promptUI == null)
            {
                return;
            }

            if (_current == null || _inputLocked)
            {
                promptUI.HideImmediate();
                return;
            }

            promptUI.Show(_current.PromptText);
        }

        private static IClinicHubInteractable ResolveInteractable(Collider2D collider)
        {
            if (collider == null)
            {
                return null;
            }

            var interactable = collider.GetComponent<IClinicHubInteractable>();
            if (interactable != null)
            {
                return interactable;
            }

            return collider.GetComponentInParent<IClinicHubInteractable>();
        }
    }
}

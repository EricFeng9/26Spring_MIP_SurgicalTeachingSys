namespace RetinalPrototype.Hub
{
    public interface IClinicHubInteractable
    {
        string PromptText { get; }
        bool CanInteract(ClinicHubPlayerController player);
        bool TryInteract(ClinicHubPlayerController player);
    }
}

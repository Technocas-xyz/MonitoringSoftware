namespace Agent.Service;

/// <summary>Resolved device identity for this agent instance, loaded from config + secret store.</summary>
public sealed class AgentIdentity
{
    public Guid DeviceId { get; init; }
    public Guid EmployeeId { get; init; }
    public string OrganizationSlug { get; init; } = "";
    public string AgentVersion { get; init; } = "1.0.0";
    public string Os { get; init; } = "windows";
}

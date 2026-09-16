namespace Agent.Common;

/// <summary>
/// Protects small secrets at rest (device token, signing secret). On Windows the concrete
/// implementation uses DPAPI; other platforms provide an equivalent. Never stored in plain text.
/// </summary>
public interface ISecretStore
{
    void Save(string key, string value);
    string? Load(string key);
    void Delete(string key);
}

/// <summary>Collectors emit events into the queue. Windows implementations arrive in Phase 4;
/// the interfaces exist now so the pipeline is complete and testable. None of these ever
/// capture keystroke content, clipboard, passwords, private messages, or auth tokens.</summary>
public interface ICollector
{
    /// <summary>Called on a timer while monitoring is active; returns events to enqueue.</summary>
    Task<IReadOnlyList<IngestEvent>> CollectAsync(MonitoringConfig config, CancellationToken ct);
}

/// <summary>Reports the current desktop idle time (no input) for idle detection.</summary>
public interface IIdleProbe
{
    TimeSpan GetIdleTime();
}

/// <summary>Shows a native notification/toast to the employee.</summary>
public interface INotifier
{
    void Notify(string title, string message);
}

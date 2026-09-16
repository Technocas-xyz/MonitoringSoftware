using Agent.Common;

namespace Agent.Service;

/// <summary>
/// Shared in-memory view of the current shift + monitoring config, refreshed from the server.
/// The server is authoritative; this is a cache the tray reads and collectors consult. Never
/// used to decide lateness/worked time locally (spec 100).
/// </summary>
public sealed class AgentState
{
    private readonly object _gate = new();
    private CurrentShift? _shift;
    private long _sequence;

    public CurrentShift? CurrentShift
    {
        get { lock (_gate) return _shift; }
        set { lock (_gate) _shift = value; }
    }

    public bool MonitoringActive
    {
        get
        {
            lock (_gate)
                return _shift is { state: "WORKING" };
        }
    }

    public long NextSequence()
    {
        lock (_gate) return ++_sequence;
    }
}

namespace Agent.Common;

/// <summary>
/// Local offline buffer for monitoring + lifecycle events (doc 05 §4).
///
/// Every event carries a client-generated GUID event_id and a monotonic per-device sequence.
/// The server dedupes by event_id, so re-sending an un-acked batch is safe. Events persist
/// (encrypted at rest by the concrete implementation) until the server acknowledges them.
/// </summary>
public interface IEventQueue
{
    /// <summary>Append an event and return the assigned monotonic sequence.</summary>
    Task<long> EnqueueAsync(IngestEvent evt, CancellationToken ct = default);

    /// <summary>Return up to <paramref name="max"/> un-acked events in sequence order.</summary>
    Task<IReadOnlyList<QueuedEvent>> PeekBatchAsync(int max, CancellationToken ct = default);

    /// <summary>Mark events acknowledged (delete/flag) up to and including a sequence.</summary>
    Task AckAsync(long throughSequence, CancellationToken ct = default);

    /// <summary>Count of un-acked events (for backpressure/metrics).</summary>
    Task<int> PendingCountAsync(CancellationToken ct = default);
}

public record QueuedEvent(long Sequence, IngestEvent Event);

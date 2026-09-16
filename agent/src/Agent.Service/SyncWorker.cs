using Agent.Common;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Agent.Service;

/// <summary>
/// Drains the offline queue to the server in idempotent batches (doc 05 §4). On network
/// failure it backs off and retries; because the server dedupes by event_id, re-sending an
/// un-acked batch never double-counts.
/// </summary>
public sealed class SyncWorker : BackgroundService
{
    private readonly IEventQueue _queue;
    private readonly ApiClient _api;
    private readonly AgentState _state;
    private readonly AgentIdentity _identity;
    private readonly ILogger<SyncWorker> _log;

    private const int BatchSize = 200;
    private static readonly TimeSpan Interval = TimeSpan.FromSeconds(15);

    public SyncWorker(IEventQueue queue, ApiClient api, AgentState state, AgentIdentity identity, ILogger<SyncWorker> log)
    {
        _queue = queue; _api = api; _state = state; _identity = identity; _log = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var backoff = TimeSpan.Zero;
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await FlushOnce(stoppingToken);
                backoff = TimeSpan.Zero;
            }
            catch (Exception ex)
            {
                // Offline or server error: keep buffering, back off (capped).
                backoff = backoff == TimeSpan.Zero ? TimeSpan.FromSeconds(5)
                    : TimeSpan.FromSeconds(Math.Min(backoff.TotalSeconds * 2, 120));
                _log.LogWarning(ex, "sync failed, backing off {Backoff}s", backoff.TotalSeconds);
            }
            await Task.Delay(backoff == TimeSpan.Zero ? Interval : backoff, stoppingToken);
        }
    }

    private async Task FlushOnce(CancellationToken ct)
    {
        var batch = await _queue.PeekBatchAsync(BatchSize, ct);
        if (batch.Count == 0) return;

        var shift = _state.CurrentShift;
        var payload = new IngestBatch(
            device_id: _identity.DeviceId,
            shift_id: shift?.shift_id,
            sequence: batch[^1].Sequence,
            events: batch.Select(q => q.Event).ToList());

        await _api.IngestAsync(payload, ct);
        await _queue.AckAsync(batch[^1].Sequence, ct);
        _log.LogInformation("synced {Count} events through seq {Seq}", batch.Count, batch[^1].Sequence);
    }
}

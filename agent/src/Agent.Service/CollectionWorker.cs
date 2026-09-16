using Agent.Common;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Agent.Service;

/// <summary>
/// Runs registered collectors on a timer while monitoring is active, enqueuing their events.
/// Monitoring only runs when the server-reported shift state is WORKING and the resolved
/// monitoring config enables the relevant dimension. Concrete Windows collectors land in
/// Phase 4; this worker completes the pipeline (collect -> queue -> sync) now.
/// </summary>
public sealed class CollectionWorker : BackgroundService
{
    private readonly IEnumerable<ICollector> _collectors;
    private readonly IEventQueue _queue;
    private readonly AgentState _state;
    private readonly ILogger<CollectionWorker> _log;

    private static readonly TimeSpan Interval = TimeSpan.FromSeconds(60);

    public CollectionWorker(
        IEnumerable<ICollector> collectors, IEventQueue queue, AgentState state,
        ILogger<CollectionWorker> log)
    {
        _collectors = collectors; _queue = queue; _state = state; _log = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var shift = _state.CurrentShift;
            if (_state.MonitoringActive && shift?.monitoring is { } config)
            {
                foreach (var collector in _collectors)
                {
                    try
                    {
                        var events = await collector.CollectAsync(config, stoppingToken);
                        foreach (var e in events)
                            await _queue.EnqueueAsync(e, stoppingToken);
                    }
                    catch (Exception ex)
                    {
                        _log.LogWarning(ex, "collector {Collector} failed", collector.GetType().Name);
                    }
                }
            }
            await Task.Delay(Interval, stoppingToken);
        }
    }
}

using Agent.Common;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Agent.Service;

/// <summary>
/// Periodically refreshes the current shift from the server and sends a heartbeat (spec 18).
/// Heartbeat drives presence + the monitoring-lost alert; it is never used alone to determine
/// productivity. Shift state shown in the tray always comes from the server.
/// </summary>
public sealed class HeartbeatWorker : BackgroundService
{
    private readonly ApiClient _api;
    private readonly AgentState _state;
    private readonly AgentIdentity _identity;
    private readonly ILogger<HeartbeatWorker> _log;

    private static readonly TimeSpan Interval = TimeSpan.FromSeconds(30);

    public HeartbeatWorker(ApiClient api, AgentState state, AgentIdentity identity, ILogger<HeartbeatWorker> log)
    {
        _api = api; _state = state; _identity = identity; _log = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var shift = await _api.GetCurrentShiftAsync(stoppingToken);
                _state.CurrentShift = shift;

                await _api.SendHeartbeatAsync(new Heartbeat(
                    shift_id: shift.shift_id,
                    agent_version: _identity.AgentVersion,
                    os: _identity.Os,
                    online: true,
                    tracking_state: shift.state,
                    timestamp: DateTimeOffset.UtcNow,
                    net: null), stoppingToken);
            }
            catch (Exception ex)
            {
                _log.LogWarning(ex, "heartbeat/shift-sync failed (offline?)");
            }
            await Task.Delay(Interval, stoppingToken);
        }
    }
}

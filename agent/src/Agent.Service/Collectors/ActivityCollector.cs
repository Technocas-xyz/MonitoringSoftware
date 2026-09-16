using System.Runtime.Versioning;
using Agent.Common;

namespace Agent.Service.Collectors;

/// <summary>
/// Emits ACTIVITY_INTERVAL events with aggregate keyboard/mouse activity percentages and an
/// IDLE flag. PRIVACY: this counts input *events only* — it never records key codes, key
/// content, typed text, or clipboard. Counts are converted to a 0–100 activity percentage per
/// interval and the raw counters are reset.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class ActivityCollector : ICollector
{
    private readonly IIdleProbe _idle;
    private readonly IInputCounter _input;
    private DateTimeOffset _intervalStart = DateTimeOffset.UtcNow;

    // Heuristic saturation points: counts at/above these map to 100% for the interval.
    private const int KeyboardSaturation = 200;   // key events per interval
    private const int MouseSaturation = 400;       // mouse move/click events per interval

    public ActivityCollector(IIdleProbe idle, IInputCounter input)
    {
        _idle = idle;
        _input = input;
    }

    public Task<IReadOnlyList<IngestEvent>> CollectAsync(MonitoringConfig config, CancellationToken ct)
    {
        var end = DateTimeOffset.UtcNow;
        var events = new List<IngestEvent>();

        var idleTime = _idle.GetIdleTime();
        var isIdle = config.monitor_idle && idleTime.TotalSeconds >= config.idle_threshold_seconds;

        if (isIdle)
        {
            var e = new IngestEvent { Type = "IDLE", Timestamp = _intervalStart };
            e.Payload["interval_start"] = _intervalStart;
            e.Payload["interval_end"] = end;
            events.Add(e);
        }
        else if (config.monitor_kbd_mouse)
        {
            var (keys, mouse) = _input.SampleAndReset();
            var kbdPct = ActivityMath.Percent(keys, KeyboardSaturation);
            var mousePct = ActivityMath.Percent(mouse, MouseSaturation);
            var combined = (int)Math.Round((kbdPct + mousePct) / 2.0);

            var e = new IngestEvent { Type = "ACTIVITY_INTERVAL", Timestamp = _intervalStart };
            e.Payload["interval_start"] = _intervalStart;
            e.Payload["interval_end"] = end;
            e.Payload["keyboard_pct"] = kbdPct;
            e.Payload["mouse_pct"] = mousePct;
            e.Payload["combined_pct"] = combined;
            e.Payload["is_idle"] = false;
            events.Add(e);
        }

        _intervalStart = end;
        return Task.FromResult<IReadOnlyList<IngestEvent>>(events);
    }
}

/// <summary>Counts input events without capturing their content (privacy). Windows uses
/// low-level hooks that increment counters only; tests use a fake.</summary>
public interface IInputCounter
{
    /// <summary>Return (keyboardEvents, mouseEvents) since last call and reset counters.</summary>
    (int keys, int mouse) SampleAndReset();
}

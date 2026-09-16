using System.Runtime.Versioning;
using Agent.Common;

namespace Agent.Tray;

/// <summary>
/// System-tray application (doc 05 §3, spec 17/101). Shows the current shift and offers
/// Start / Pause / Resume / End. All durations and state come from the server (via ApiClient);
/// the tray never computes lateness or worked time locally. A background timer refreshes state.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class TrayApplicationContext : ApplicationContext
{
    private readonly NotifyIcon _icon;
    private readonly ApiClient _api;
    private readonly System.Windows.Forms.Timer _timer;
    private CurrentShift? _shift;

    private readonly ToolStripMenuItem _statusItem = new("Loading…") { Enabled = false };
    private readonly ToolStripMenuItem _startItem = new("Start Shift");
    private readonly ToolStripMenuItem _pauseItem = new("Pause");
    private readonly ToolStripMenuItem _resumeItem = new("Resume");
    private readonly ToolStripMenuItem _endItem = new("End Shift");

    public TrayApplicationContext(ApiClient api)
    {
        _api = api;

        var menu = new ContextMenuStrip();
        menu.Items.Add(_statusItem);
        menu.Items.Add(new ToolStripSeparator());
        _startItem.Click += async (_, _) => await SafeAction(DoStart);
        _pauseItem.Click += async (_, _) => await SafeAction(DoPause);
        _resumeItem.Click += async (_, _) => await SafeAction(DoResume);
        _endItem.Click += async (_, _) => await SafeAction(DoEnd);
        menu.Items.Add(_startItem);
        menu.Items.Add(_pauseItem);
        menu.Items.Add(_resumeItem);
        menu.Items.Add(_endItem);
        menu.Items.Add(new ToolStripSeparator());
        var exit = new ToolStripMenuItem("Exit");
        exit.Click += (_, _) => ExitThread();
        menu.Items.Add(exit);

        _icon = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Visible = true,
            Text = "Remote Work",
            ContextMenuStrip = menu,
        };

        _timer = new System.Windows.Forms.Timer { Interval = 15_000 };
        _timer.Tick += async (_, _) => await Refresh();
        _timer.Start();
        _ = Refresh();
    }

    private async Task Refresh()
    {
        try
        {
            _shift = await _api.GetCurrentShiftAsync();
            UpdateMenu();
        }
        catch
        {
            _statusItem.Text = "Offline — syncing…";
        }
    }

    private void UpdateMenu()
    {
        var state = _shift?.state ?? "NOT STARTED";
        _statusItem.Text = $"● {state}";
        _icon.Text = $"Remote Work — {state}";

        // Enable actions per state (server still authoritative on the call).
        var s = _shift?.state;
        _startItem.Enabled = s is null or "AVAILABLE" or "SCHEDULED";
        _pauseItem.Enabled = s == "WORKING";
        _resumeItem.Enabled = s is "ON_BREAK" or "PAUSED";
        _endItem.Enabled = s is "WORKING" or "ON_BREAK" or "PAUSED";
    }

    private ShiftActionRequest NewAction() =>
        new(device_id: null, client_time: DateTimeOffset.UtcNow, event_id: Guid.NewGuid().ToString());

    private async Task DoStart()
    {
        if (_shift?.shift_id is { } id)
            _shift = ToCurrent(await _api.StartShiftAsync(id, NewAction()));
    }

    private async Task DoPause()
    {
        if (_shift?.shift_id is { } id)
            _shift = ToCurrent(await _api.PauseShiftAsync(id, NewAction() with { is_break = true }));
    }

    private async Task DoResume()
    {
        if (_shift?.shift_id is { } id)
            _shift = ToCurrent(await _api.ResumeShiftAsync(id, NewAction()));
    }

    private async Task DoEnd()
    {
        if (_shift?.shift_id is { } id)
            _shift = ToCurrent(await _api.EndShiftAsync(id, NewAction()));
    }

    private CurrentShift ToCurrent(ShiftResponse r) => new(
        r.id, r.state, r.scheduled_start, r.scheduled_end, r.actual_start,
        r.timezone, _shift?.monitoring, DateTimeOffset.UtcNow);

    private async Task SafeAction(Func<Task> action)
    {
        try
        {
            await action();
            UpdateMenu();
        }
        catch (Exception ex)
        {
            _icon.ShowBalloonTip(3000, "Action failed", ex.Message, ToolTipIcon.Warning);
            await Refresh();
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _timer.Dispose();
            _icon.Visible = false;
            _icon.Dispose();
        }
        base.Dispose(disposing);
    }
}

using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;
using Agent.Common;

namespace Agent.Service.Collectors;

/// <summary>
/// Tracks the foreground application and (policy-permitting) its window title, emitting an
/// APPLICATION_ACTIVITY event per contiguous focus span. Only the process/app name and title
/// are read — never window contents, keystrokes, or clipboard.
///
/// Also derives a domain heuristically from a browser's title as a best-effort WEBSITE_ACTIVITY
/// signal when websites are monitored. Reliable per-tab URL capture requires a browser
/// extension / native-messaging host (doc 00 A2); this is the degraded fallback.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class ActiveWindowCollector : ICollector
{
    private string? _currentApp;
    private string? _currentTitle;
    private DateTimeOffset _spanStart = DateTimeOffset.UtcNow;

    private static readonly string[] Browsers = { "chrome", "msedge", "firefox", "brave", "opera" };

    public Task<IReadOnlyList<IngestEvent>> CollectAsync(MonitoringConfig config, CancellationToken ct)
    {
        var events = new List<IngestEvent>();
        var (app, title) = GetForeground();
        var nowTs = DateTimeOffset.UtcNow;

        if (app is not null && app != _currentApp)
        {
            // Close the previous span.
            if (_currentApp is not null)
            {
                var duration = (int)(nowTs - _spanStart).TotalSeconds;
                if (config.monitor_applications)
                    events.Add(AppEvent(_currentApp, _currentTitle, _spanStart, duration, config));
                if (config.monitor_websites && IsBrowser(_currentApp))
                {
                    var domain = DomainParser.FromTitle(_currentTitle);
                    if (domain is not null)
                        events.Add(WebEvent(domain, _spanStart, duration));
                }
            }
            _currentApp = app;
            _currentTitle = title;
            _spanStart = nowTs;
        }

        return Task.FromResult<IReadOnlyList<IngestEvent>>(events);
    }

    private static IngestEvent AppEvent(string app, string? title, DateTimeOffset start, int duration, MonitoringConfig config)
    {
        var e = new IngestEvent { Type = "APPLICATION_ACTIVITY", Timestamp = start };
        e.Payload["application"] = app;
        e.Payload["process"] = app;
        // Title only forwarded when apps are monitored; server drops it again if policy forbids.
        if (config.monitor_applications && title is not null) e.Payload["window_title"] = title;
        e.Payload["started_at"] = start;
        e.Payload["duration"] = duration;
        return e;
    }

    private static IngestEvent WebEvent(string domain, DateTimeOffset start, int duration)
    {
        var e = new IngestEvent { Type = "WEBSITE_ACTIVITY", Timestamp = start };
        e.Payload["domain"] = domain;
        e.Payload["started_at"] = start;
        e.Payload["duration"] = duration;
        return e;
    }

    private static bool IsBrowser(string app) =>
        Browsers.Any(b => app.Contains(b, StringComparison.OrdinalIgnoreCase));

    // --- Win32 foreground window ---
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    private static (string? app, string? title) GetForeground()
    {
        var hwnd = GetForegroundWindow();
        if (hwnd == IntPtr.Zero) return (null, null);

        var sb = new StringBuilder(512);
        GetWindowText(hwnd, sb, sb.Capacity);
        var title = sb.ToString();

        GetWindowThreadProcessId(hwnd, out var pid);
        string? app = null;
        try { app = Process.GetProcessById((int)pid).ProcessName; }
        catch { /* process may have exited */ }
        return (app, string.IsNullOrEmpty(title) ? null : title);
    }
}

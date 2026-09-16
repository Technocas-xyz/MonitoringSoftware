using System.Text.Json.Serialization;

namespace Agent.Common;

// Enrollment + token (doc 03 §3)
public record EnrollRequest(string? hostname, string? os, string? os_version, string? agent_version);
public record EnrollResponse(Guid device_id, string status);

public record TokenRequest(string organization_slug, Guid device_id, string timestamp, string signature);
public record TokenResponse(string device_token, Guid employee_id);

// Current shift + schedule (agent sync)
public record MonitoringConfig(
    bool monitor_applications = true,
    bool monitor_websites = true,
    string website_mode = "domain",
    bool monitor_idle = true,
    int idle_threshold_seconds = 600,
    string idle_classification = "idle",
    bool monitor_kbd_mouse = true,
    string screenshot_mode = "off",
    int? screenshot_interval_seconds = null,
    string screenshot_capture_scope = "working_only",
    bool screenshot_watermark = false);

public record CurrentShift(
    Guid? shift_id,
    string? state,
    DateTimeOffset? scheduled_start,
    DateTimeOffset? scheduled_end,
    DateTimeOffset? actual_start,
    string? timezone,
    MonitoringConfig? monitoring,
    DateTimeOffset server_time);

public record ScheduleWindow(DateTimeOffset scheduled_start, DateTimeOffset scheduled_end);
public record TodaySchedule(DateTime day, string? timezone, List<ScheduleWindow> windows, DateTimeOffset server_time);

// Heartbeat
public record Heartbeat(
    Guid? shift_id,
    string? agent_version,
    string? os,
    bool online,
    string? tracking_state,
    DateTimeOffset? timestamp,
    Dictionary<string, object>? net);

// Shift action request/response (doc 03 §7)
public record ShiftActionRequest(Guid? device_id, DateTimeOffset? client_time, string? event_id, bool is_break = true);
public record ShiftResponse(Guid id, Guid employee_id, string state,
    DateTimeOffset? scheduled_start, DateTimeOffset? scheduled_end,
    DateTimeOffset? actual_start, DateTimeOffset? actual_end, string timezone, int version);

// Ingestion batch (doc 03 §8).
public record IngestBatch(Guid device_id, Guid? shift_id, long sequence, List<IngestEvent> events);

// Screenshots (doc 03 §8)
public record PresignResponse(Guid screenshot_id, string storage_key, string upload_url);
public record ScreenshotConfirm(Guid id, Guid employee_id, Guid? shift_id, DateTimeOffset captured_at, string status, bool watermarked);

public class IngestEvent
{
    [JsonPropertyName("event_id")] public string EventId { get; set; } = Guid.NewGuid().ToString();
    [JsonPropertyName("type")] public string Type { get; set; } = "";
    [JsonPropertyName("timestamp")] public DateTimeOffset Timestamp { get; set; } = DateTimeOffset.UtcNow;
    // Flexible payload; only fields relevant to the type are populated.
    [JsonPropertyName("payload")] public Dictionary<string, object?> Payload { get; set; } = new();
}

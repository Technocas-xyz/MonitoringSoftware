using System.Net.Http.Json;
using System.Text;
using System.Text.Json;

namespace Agent.Common;

/// <summary>
/// Typed HTTP client for the agent API. Every device-authenticated request carries the device
/// bearer token plus an HMAC signature (X-Signature/X-Timestamp) over the exact body.
/// TLS certificate validation is left to the platform handler (do not disable in production).
/// </summary>
public class ApiClient
{
    private readonly HttpClient _http;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public string OrganizationSlug { get; }
    public string? DeviceToken { get; set; }
    public string? SigningSecret { get; set; }

    public ApiClient(HttpClient http, string organizationSlug)
    {
        _http = http;
        OrganizationSlug = organizationSlug;
    }

    // --- token exchange (no device token yet; proof is the signature) ---
    public async Task<TokenResponse> IssueDeviceTokenAsync(Guid deviceId, CancellationToken ct = default)
    {
        if (SigningSecret is null) throw new InvalidOperationException("signing secret required");
        var ts = RequestSigner.UnixNow();
        // Proof signs the device id as the body, path /auth/agent/token, method "TOKEN".
        var signature = RequestSigner.Sign(SigningSecret, "TOKEN", "/auth/agent/token", deviceId.ToString(), ts);
        var body = new TokenRequest(OrganizationSlug, deviceId, ts, signature);
        var resp = await _http.PostAsJsonAsync("/api/v1/auth/agent/token", body, Json, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<TokenResponse>(Json, ct))!;
    }

    public Task<CurrentShift> GetCurrentShiftAsync(CancellationToken ct = default) =>
        SignedGetAsync<CurrentShift>("/api/v1/agent/shift/current", ct);

    public Task<TodaySchedule> GetTodayScheduleAsync(CancellationToken ct = default) =>
        SignedGetAsync<TodaySchedule>("/api/v1/agent/schedule/today", ct);

    public Task SendHeartbeatAsync(Heartbeat hb, CancellationToken ct = default) =>
        SignedPostAsync("/api/v1/agent/heartbeat", hb, ct);

    public Task<object> IngestAsync(IngestBatch batch, CancellationToken ct = default) =>
        SignedPostAsync<object>("/api/v1/ingest/events", batch, ct);

    // --- screenshots (presign -> PUT blob -> confirm) ---
    public Task<PresignResponse> PresignScreenshotAsync(
        DateTimeOffset capturedAt, int bytes, string eventId, CancellationToken ct = default) =>
        SignedPostAsync<PresignResponse>(
            "/api/v1/screenshots/presign",
            new { captured_at = capturedAt, bytes, event_id = eventId },
            ct);

    public async Task UploadBlobAsync(string uploadUrl, byte[] data, CancellationToken ct = default)
    {
        // The presigned URL is absolute and pre-authorized; no signing header needed here.
        using var content = new ByteArrayContent(data);
        content.Headers.TryAddWithoutValidation("Content-Type", "image/jpeg");
        using var resp = await _http.PutAsync(uploadUrl, content, ct);
        resp.EnsureSuccessStatusCode();
    }

    public Task<ScreenshotConfirm> ConfirmScreenshotAsync(Guid screenshotId, CancellationToken ct = default) =>
        SignedPostAsync<ScreenshotConfirm>($"/api/v1/screenshots/{screenshotId}/confirm", new { }, ct);

    // Shift controls (device-signed).
    public Task<ShiftResponse> StartShiftAsync(Guid shiftId, ShiftActionRequest req, CancellationToken ct = default) =>
        SignedPostAsync<ShiftResponse>($"/api/v1/shifts/{shiftId}/start", req, ct);

    public Task<ShiftResponse> PauseShiftAsync(Guid shiftId, ShiftActionRequest req, CancellationToken ct = default) =>
        SignedPostAsync<ShiftResponse>($"/api/v1/shifts/{shiftId}/pause", req, ct);

    public Task<ShiftResponse> ResumeShiftAsync(Guid shiftId, ShiftActionRequest req, CancellationToken ct = default) =>
        SignedPostAsync<ShiftResponse>($"/api/v1/shifts/{shiftId}/resume", req, ct);

    public Task<ShiftResponse> EndShiftAsync(Guid shiftId, ShiftActionRequest req, CancellationToken ct = default) =>
        SignedPostAsync<ShiftResponse>($"/api/v1/shifts/{shiftId}/end", req, ct);

    // --- signing helpers ---
    private async Task<T> SignedGetAsync<T>(string path, CancellationToken ct)
    {
        using var req = BuildSigned(HttpMethod.Get, path, body: "");
        var resp = await _http.SendAsync(req, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<T>(Json, ct))!;
    }

    private async Task<T> SignedPostAsync<T>(string path, object payload, CancellationToken ct)
    {
        var json = JsonSerializer.Serialize(payload, Json);
        using var req = BuildSigned(HttpMethod.Post, path, json);
        req.Content = new StringContent(json, Encoding.UTF8, "application/json");
        var resp = await _http.SendAsync(req, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<T>(Json, ct))!;
    }

    private async Task SignedPostAsync(string path, object payload, CancellationToken ct)
    {
        var json = JsonSerializer.Serialize(payload, Json);
        using var req = BuildSigned(HttpMethod.Post, path, json);
        req.Content = new StringContent(json, Encoding.UTF8, "application/json");
        var resp = await _http.SendAsync(req, ct);
        resp.EnsureSuccessStatusCode();
    }

    private HttpRequestMessage BuildSigned(HttpMethod method, string path, string body)
    {
        if (DeviceToken is null || SigningSecret is null)
            throw new InvalidOperationException("device token and signing secret required");
        var ts = RequestSigner.UnixNow();
        var sig = RequestSigner.Sign(SigningSecret, method.Method, path, body, ts);
        var req = new HttpRequestMessage(method, path);
        req.Headers.TryAddWithoutValidation("Authorization", $"Bearer {DeviceToken}");
        req.Headers.TryAddWithoutValidation("X-Signature", sig);
        req.Headers.TryAddWithoutValidation("X-Timestamp", ts);
        return req;
    }
}

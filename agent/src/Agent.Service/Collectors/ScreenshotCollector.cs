using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Drawing;
using System.Drawing.Imaging;
using Agent.Common;

namespace Agent.Service.Collectors;

/// <summary>
/// Captures screenshots per policy and uploads them via the presign flow (doc 03 §8):
/// presign -> PUT blob -> confirm. Honors screenshot_mode (off/interval/random) and cadence.
/// Capture only happens while monitoring is active (WORKING) — the CollectionWorker already
/// gates on that; this collector additionally enforces the interval and mode.
///
/// This collector uploads out-of-band (not through the event queue), so CollectAsync returns
/// no queue events; it performs the presign/upload/confirm itself. Screenshot blobs are never
/// queued in plaintext.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class ScreenshotCollector : ICollector
{
    private readonly ApiClient _api;
    private readonly Random _rng = new();
    private DateTimeOffset _nextCapture = DateTimeOffset.MinValue;

    public ScreenshotCollector(ApiClient api) => _api = api;

    public async Task<IReadOnlyList<IngestEvent>> CollectAsync(MonitoringConfig config, CancellationToken ct)
    {
        if (config.screenshot_mode == "off")
            return Array.Empty<IngestEvent>();

        var now = DateTimeOffset.UtcNow;
        if (now < _nextCapture)
            return Array.Empty<IngestEvent>();

        ScheduleNext(config, now);

        try
        {
            var (bytes, width, height) = Capture();
            var eventId = Guid.NewGuid().ToString();
            var presign = await _api.PresignScreenshotAsync(now, bytes.Length, eventId, ct);
            await _api.UploadBlobAsync(presign.upload_url, bytes, ct);
            await _api.ConfirmScreenshotAsync(presign.screenshot_id, ct);
        }
        catch
        {
            // Upload failures are non-fatal; the next cycle retries a fresh capture (spec 81 #13).
        }

        return Array.Empty<IngestEvent>();
    }

    private void ScheduleNext(MonitoringConfig config, DateTimeOffset now)
    {
        var baseInterval = config.screenshot_interval_seconds ?? 600;
        var seconds = config.screenshot_mode == "random"
            ? _rng.Next(baseInterval / 2, baseInterval * 2 + 1)
            : baseInterval;
        _nextCapture = now.AddSeconds(seconds);
    }

    private static (byte[] bytes, int width, int height) Capture()
    {
        var bounds = GetVirtualScreenBounds();
        using var bmp = new Bitmap(bounds.Width, bounds.Height);
        using (var g = Graphics.FromImage(bmp))
            g.CopyFromScreen(bounds.X, bounds.Y, 0, 0, bmp.Size);

        using var ms = new MemoryStream();
        // Compressed JPEG to keep uploads small (spec 59).
        var encoder = GetJpegEncoder();
        var p = new EncoderParameters(1);
        p.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, 60L);
        bmp.Save(ms, encoder, p);
        return (ms.ToArray(), bounds.Width, bounds.Height);
    }

    private const int SM_XVIRTUALSCREEN = 76;
    private const int SM_YVIRTUALSCREEN = 77;
    private const int SM_CXVIRTUALSCREEN = 78;
    private const int SM_CYVIRTUALSCREEN = 79;

    [DllImport("user32.dll")] private static extern int GetSystemMetrics(int nIndex);

    private static Rectangle GetVirtualScreenBounds() => new(
        GetSystemMetrics(SM_XVIRTUALSCREEN),
        GetSystemMetrics(SM_YVIRTUALSCREEN),
        GetSystemMetrics(SM_CXVIRTUALSCREEN),
        GetSystemMetrics(SM_CYVIRTUALSCREEN));

    private static ImageCodecInfo GetJpegEncoder() =>
        ImageCodecInfo.GetImageEncoders().First(c => c.FormatID == ImageFormat.Jpeg.Guid);
}

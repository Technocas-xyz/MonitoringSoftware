using Agent.Common;
using Agent.Tray;

// Tray UI entry point (Windows-only). Reads DPAPI secrets written during enrollment/approval
// and drives shift actions through the signed ApiClient. If secrets are missing, prompts the
// operator to enroll (enrollment flow handled out-of-band / by a setup step).

if (!OperatingSystem.IsWindows())
{
    Console.Error.WriteLine("Agent.Tray runs on Windows only.");
    return;
}

ApplicationConfiguration.Initialize();

var apiBase = Environment.GetEnvironmentVariable("RWM_API_BASE") ?? "https://localhost:8000";
var orgSlug = Environment.GetEnvironmentVariable("RWM_ORG_SLUG") ?? "acme";
var dataDir = Environment.GetEnvironmentVariable("RWM_DATA_DIR")
              ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RwmAgent");

var reader = new TraySecretReader(dataDir);
var deviceToken = reader.Load("device_token");
var signingSecret = reader.Load("signing_secret");

if (deviceToken is null || signingSecret is null)
{
    MessageBox.Show(
        "This device is not enrolled yet. Complete enrollment and approval first.",
        "Remote Work", MessageBoxButtons.OK, MessageBoxIcon.Information);
    return;
}

var http = new HttpClient { BaseAddress = new Uri(apiBase) };
var api = new ApiClient(http, orgSlug) { DeviceToken = deviceToken, SigningSecret = signingSecret };

Application.Run(new TrayApplicationContext(api));

using Agent.Common;
using Agent.Service;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

// Agent.Service: the always-on Windows service (doc 05 §1). It owns the offline queue and all
// network I/O; the tray app is a thin UI over IPC (Phase 3 tray project). Runs as a Worker
// Service host; on Windows it can be installed with `sc create` / a hosted service installer.

var builder = Host.CreateApplicationBuilder(args);

var apiBase = Environment.GetEnvironmentVariable("RWM_API_BASE") ?? "https://localhost:8000";
var orgSlug = Environment.GetEnvironmentVariable("RWM_ORG_SLUG") ?? "acme";
var dataDir = Environment.GetEnvironmentVariable("RWM_DATA_DIR")
              ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RwmAgent");
Directory.CreateDirectory(dataDir);

// Secret store + payload cipher (DPAPI on Windows).
ISecretStore secrets = OperatingSystem.IsWindows()
    ? new DpapiSecretStore(dataDir)
    : throw new PlatformNotSupportedException("Agent.Service targets Windows for at-rest protection");
IPayloadCipher cipher = new DpapiPayloadCipher();

// Identity is loaded from the secret store (populated during enrollment/approval).
var deviceIdStr = secrets.Load("device_id");
var employeeIdStr = secrets.Load("employee_id");
var deviceToken = secrets.Load("device_token");
var signingSecret = secrets.Load("signing_secret");

var identity = new AgentIdentity
{
    DeviceId = Guid.TryParse(deviceIdStr, out var d) ? d : Guid.Empty,
    EmployeeId = Guid.TryParse(employeeIdStr, out var e) ? e : Guid.Empty,
    OrganizationSlug = orgSlug,
    AgentVersion = "1.0.0",
    Os = "windows",
};

builder.Services.AddSingleton(identity);
builder.Services.AddSingleton(secrets);
builder.Services.AddSingleton(cipher);
builder.Services.AddSingleton<AgentState>();
builder.Services.AddSingleton<IEventQueue>(_ =>
    new SqliteEventQueue(Path.Combine(dataDir, "queue.db"), cipher));

builder.Services.AddHttpClient("rwm", c => c.BaseAddress = new Uri(apiBase));
builder.Services.AddSingleton(sp =>
{
    var http = sp.GetRequiredService<IHttpClientFactory>().CreateClient("rwm");
    var api = new ApiClient(http, orgSlug)
    {
        DeviceToken = deviceToken,
        SigningSecret = signingSecret,
    };
    return api;
});

// Windows collectors (Phase 4). Registered as ICollector; CollectionWorker runs them while
// the server-reported shift state is WORKING.
if (OperatingSystem.IsWindows())
{
    builder.Services.AddSingleton<IIdleProbe, Win32IdleProbe>();
    builder.Services.AddSingleton<Agent.Service.Collectors.IInputCounter, Agent.Service.Collectors.WindowsInputCounter>();
    builder.Services.AddSingleton<ICollector, Agent.Service.Collectors.ActiveWindowCollector>();
    builder.Services.AddSingleton<ICollector, Agent.Service.Collectors.ActivityCollector>();
    builder.Services.AddSingleton<ICollector>(sp =>
        new Agent.Service.Collectors.ScreenshotCollector(sp.GetRequiredService<ApiClient>()));
}

builder.Services.AddHostedService<HeartbeatWorker>();
builder.Services.AddHostedService<SyncWorker>();
builder.Services.AddHostedService<CollectionWorker>();

var host = builder.Build();
await host.RunAsync();

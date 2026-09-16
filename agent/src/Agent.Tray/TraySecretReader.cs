using System.Runtime.Versioning;
using System.Security.Cryptography;
using System.Text;

namespace Agent.Tray;

/// <summary>Reads the same DPAPI-protected secrets the service wrote (device token, signing
/// secret, ids). The tray uses these to call the API for shift actions and status.</summary>
[SupportedOSPlatform("windows")]
public sealed class TraySecretReader
{
    private readonly string _dir;

    public TraySecretReader(string dir) => _dir = dir;

    public string? Load(string key)
    {
        var path = Path.Combine(_dir, key + ".sec");
        if (!File.Exists(path)) return null;
        var bytes = ProtectedData.Unprotect(File.ReadAllBytes(path), null, DataProtectionScope.CurrentUser);
        return Encoding.UTF8.GetString(bytes);
    }
}

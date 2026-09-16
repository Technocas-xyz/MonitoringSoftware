using System.Runtime.Versioning;
using System.Security.Cryptography;
using System.Text;
using Agent.Common;

namespace Agent.Service;

/// <summary>DPAPI-based secret store (spec 60). Secrets are encrypted for the current user
/// so another user on the machine cannot read them.</summary>
[SupportedOSPlatform("windows")]
public sealed class DpapiSecretStore : ISecretStore
{
    private readonly string _dir;

    public DpapiSecretStore(string dir)
    {
        _dir = dir;
        Directory.CreateDirectory(_dir);
    }

    private string PathFor(string key) => Path.Combine(_dir, key + ".sec");

    public void Save(string key, string value)
    {
        var protectedBytes = ProtectedData.Protect(
            Encoding.UTF8.GetBytes(value), null, DataProtectionScope.CurrentUser);
        File.WriteAllBytes(PathFor(key), protectedBytes);
    }

    public string? Load(string key)
    {
        var path = PathFor(key);
        if (!File.Exists(path)) return null;
        var bytes = ProtectedData.Unprotect(
            File.ReadAllBytes(path), null, DataProtectionScope.CurrentUser);
        return Encoding.UTF8.GetString(bytes);
    }

    public void Delete(string key)
    {
        var path = PathFor(key);
        if (File.Exists(path)) File.Delete(path);
    }
}

/// <summary>DPAPI cipher for queue payloads at rest.</summary>
[SupportedOSPlatform("windows")]
public sealed class DpapiPayloadCipher : IPayloadCipher
{
    public byte[] Encrypt(byte[] plaintext) =>
        ProtectedData.Protect(plaintext, null, DataProtectionScope.CurrentUser);

    public byte[] Decrypt(byte[] ciphertext) =>
        ProtectedData.Unprotect(ciphertext, null, DataProtectionScope.CurrentUser);
}

/// <summary>Win32 idle probe via GetLastInputInfo (no key content, only idle duration).</summary>
[SupportedOSPlatform("windows")]
public sealed class Win32IdleProbe : IIdleProbe
{
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    public TimeSpan GetIdleTime()
    {
        var info = new LASTINPUTINFO { cbSize = (uint)System.Runtime.InteropServices.Marshal.SizeOf<LASTINPUTINFO>() };
        if (!GetLastInputInfo(ref info)) return TimeSpan.Zero;
        var idleMs = (uint)Environment.TickCount - info.dwTime;
        return TimeSpan.FromMilliseconds(idleMs);
    }
}

using System.Security.Cryptography;
using System.Text;

namespace Agent.Common;

/// <summary>
/// HMAC-SHA256 request signing that must match the server's app.core.security.sign_request.
///
/// Canonical string:  METHOD\nPATH\nTIMESTAMP\nSHA256(body-hex)
/// Signature:         hex(HMAC-SHA256(secret, canonical))
///
/// The server recomputes this and rejects mismatches; timestamps outside a small skew window
/// are rejected to limit replay. Never trust the local clock for attendance truth — the
/// timestamp here is only for signature freshness.
/// </summary>
public static class RequestSigner
{
    public static string Sign(string secret, string method, string path, string body, string timestamp)
    {
        var bodyHash = Sha256Hex(body);
        var canonical = $"{method.ToUpperInvariant()}\n{path}\n{timestamp}\n{bodyHash}";
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        var sig = hmac.ComputeHash(Encoding.UTF8.GetBytes(canonical));
        return ToHex(sig);
    }

    public static string UnixNow() =>
        ((long)(DateTime.UtcNow - DateTime.UnixEpoch).TotalSeconds).ToString();

    private static string Sha256Hex(string input)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return ToHex(bytes);
    }

    private static string ToHex(byte[] bytes)
    {
        var sb = new StringBuilder(bytes.Length * 2);
        foreach (var b in bytes)
            sb.Append(b.ToString("x2"));
        return sb.ToString();
    }
}

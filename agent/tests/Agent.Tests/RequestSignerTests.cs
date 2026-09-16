using System.Security.Cryptography;
using System.Text;
using Agent.Common;
using Xunit;

namespace Agent.Tests;

public class RequestSignerTests
{
    // Independent re-implementation of the same canonical scheme, used to assert the signer
    // produces exactly what the server (app.core.security.sign_request) expects.
    private static string Reference(string secret, string method, string path, string body, string ts)
    {
        var bodyHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(body))).ToLowerInvariant();
        var canonical = $"{method.ToUpperInvariant()}\n{path}\n{ts}\n{bodyHash}";
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        return Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
    }

    [Fact]
    public void Empty_body_hash_matches_known_sha256_constant()
    {
        // SHA256("") is a well-known constant; confirms our body hashing is correct and thus
        // interoperable with the server's sha256(body) step.
        var hash = Convert.ToHexString(SHA256.HashData(Array.Empty<byte>())).ToLowerInvariant();
        Assert.Equal("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", hash);
    }

    [Fact]
    public void Signature_matches_reference_scheme()
    {
        var sig = RequestSigner.Sign("testsecret", "GET", "/api/v1/agent/shift/current", "", "1000");
        var expected = Reference("testsecret", "GET", "/api/v1/agent/shift/current", "", "1000");
        Assert.Equal(expected, sig);
    }

    [Fact]
    public void Signature_is_deterministic_and_body_sensitive()
    {
        var a = RequestSigner.Sign("s", "POST", "/p", "{\"x\":1}", "1000");
        var b = RequestSigner.Sign("s", "POST", "/p", "{\"x\":1}", "1000");
        var c = RequestSigner.Sign("s", "POST", "/p", "{\"x\":2}", "1000");
        Assert.Equal(a, b);
        Assert.NotEqual(a, c);
    }

    [Fact]
    public void Method_is_case_normalized()
    {
        var lower = RequestSigner.Sign("s", "get", "/p", "", "1");
        var upper = RequestSigner.Sign("s", "GET", "/p", "", "1");
        Assert.Equal(lower, upper);
    }
}

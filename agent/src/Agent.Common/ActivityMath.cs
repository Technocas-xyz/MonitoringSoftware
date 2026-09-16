namespace Agent.Common;

/// <summary>Pure, platform-independent helpers for collectors, extracted so they can be unit
/// tested without Windows APIs.</summary>
public static class ActivityMath
{
    /// <summary>Map a raw event count to a 0–100 activity percentage given a saturation point.</summary>
    public static int Percent(int count, int saturation)
    {
        if (count <= 0) return 0;
        if (saturation <= 0) return 100;
        if (count >= saturation) return 100;
        return (int)Math.Round(count * 100.0 / saturation);
    }
}

public static class DomainParser
{
    /// <summary>Best-effort extraction of a domain-like token from a browser window title.
    /// Returns null if none is found. Never parses page content.</summary>
    public static string? FromTitle(string? title)
    {
        if (string.IsNullOrWhiteSpace(title)) return null;
        foreach (var token in title.Split(new[] { ' ', '-', '|', '\u2013' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var t = token.Trim().TrimEnd('/');
            if (t.Contains('.') && !t.Contains(' ') && Uri.CheckHostName(t) != UriHostNameType.Unknown)
                return t.ToLowerInvariant();
        }
        return null;
    }
}

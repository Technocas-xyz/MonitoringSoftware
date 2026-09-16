using Agent.Common;
using Xunit;

namespace Agent.Tests;

public class ActivityMathTests
{
    [Theory]
    [InlineData(0, 200, 0)]
    [InlineData(200, 200, 100)]
    [InlineData(400, 200, 100)]   // above saturation clamps to 100
    [InlineData(100, 200, 50)]
    [InlineData(50, 200, 25)]
    public void Percent_maps_counts_to_bounded_percentage(int count, int sat, int expected)
    {
        Assert.Equal(expected, ActivityMath.Percent(count, sat));
    }

    [Fact]
    public void Percent_is_never_out_of_range()
    {
        for (var c = 0; c <= 1000; c += 37)
        {
            var p = ActivityMath.Percent(c, 200);
            Assert.InRange(p, 0, 100);
        }
    }
}

public class DomainParserTests
{
    [Theory]
    [InlineData("GitHub - github.com", "github.com")]
    [InlineData("Inbox (12) | mail.google.com", "mail.google.com")]
    [InlineData("Some Document - Google Docs", null)]  // no domain-like token
    [InlineData("", null)]
    [InlineData(null, null)]
    public void FromTitle_extracts_domain_or_null(string? title, string? expected)
    {
        Assert.Equal(expected, DomainParser.FromTitle(title));
    }

    [Fact]
    public void FromTitle_lowercases_domain()
    {
        Assert.Equal("example.com", DomainParser.FromTitle("Home - Example.COM"));
    }
}

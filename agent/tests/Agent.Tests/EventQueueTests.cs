using Agent.Common;
using Agent.Service;
using Xunit;

namespace Agent.Tests;

/// <summary>Passthrough cipher so the queue can be tested without DPAPI (Windows-only).</summary>
internal sealed class PlainCipher : IPayloadCipher
{
    public byte[] Encrypt(byte[] plaintext) => plaintext;
    public byte[] Decrypt(byte[] ciphertext) => ciphertext;
}

public class EventQueueTests : IDisposable
{
    private readonly string _dbPath = Path.Combine(Path.GetTempPath(), $"rwm-test-{Guid.NewGuid():N}.db");
    private SqliteEventQueue New() => new(_dbPath, new PlainCipher());

    [Fact]
    public async Task Enqueue_then_peek_returns_in_sequence_order()
    {
        var q = New();
        await q.EnqueueAsync(new IngestEvent { Type = "A" });
        await q.EnqueueAsync(new IngestEvent { Type = "B" });
        var batch = await q.PeekBatchAsync(10);
        Assert.Equal(2, batch.Count);
        Assert.Equal("A", batch[0].Event.Type);
        Assert.Equal("B", batch[1].Event.Type);
        Assert.True(batch[1].Sequence > batch[0].Sequence);
    }

    [Fact]
    public async Task Duplicate_event_id_is_ignored()
    {
        var q = New();
        var evt = new IngestEvent { EventId = "dup-1", Type = "A" };
        await q.EnqueueAsync(evt);
        await q.EnqueueAsync(evt); // same event_id -> ignored
        Assert.Equal(1, await q.PendingCountAsync());
    }

    [Fact]
    public async Task Ack_removes_events_through_sequence()
    {
        var q = New();
        await q.EnqueueAsync(new IngestEvent { Type = "A" });
        var s2 = await q.EnqueueAsync(new IngestEvent { Type = "B" });
        await q.EnqueueAsync(new IngestEvent { Type = "C" });
        await q.AckAsync(s2);
        var remaining = await q.PeekBatchAsync(10);
        Assert.Single(remaining);
        Assert.Equal("C", remaining[0].Event.Type);
    }

    [Fact]
    public async Task Payload_survives_roundtrip()
    {
        var q = New();
        var evt = new IngestEvent { Type = "APPLICATION_ACTIVITY" };
        evt.Payload["application"] = "Code";
        evt.Payload["duration"] = 600;
        await q.EnqueueAsync(evt);
        var batch = await q.PeekBatchAsync(1);
        Assert.Equal("APPLICATION_ACTIVITY", batch[0].Event.Type);
        Assert.Equal("Code", batch[0].Event.Payload["application"]?.ToString());
    }

    public void Dispose()
    {
        try { if (File.Exists(_dbPath)) File.Delete(_dbPath); } catch { /* best effort */ }
    }
}

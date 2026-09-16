using System.Text.Json;
using Agent.Common;
using Microsoft.Data.Sqlite;

namespace Agent.Service;

/// <summary>
/// SQLite-backed offline event queue (doc 05 §4). Payloads are encrypted at rest via the
/// provided ISecretStore-derived key wrapper before insert. Sequence is a monotonic rowid.
///
/// Note: the whole DB file should live in a per-user protected location; the payload column is
/// additionally encrypted so an at-rest DB copy does not leak collected data.
/// </summary>
public sealed class SqliteEventQueue : IEventQueue, IDisposable
{
    private readonly string _connString;
    private readonly IPayloadCipher _cipher;
    private readonly SemaphoreSlim _lock = new(1, 1);
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public SqliteEventQueue(string dbPath, IPayloadCipher cipher)
    {
        _connString = new SqliteConnectionStringBuilder { DataSource = dbPath }.ToString();
        _cipher = cipher;
        Init();
    }

    private void Init()
    {
        using var conn = Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                cipher   BLOB NOT NULL,
                acked    INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS ix_events_acked ON events(acked, sequence);
            """;
        cmd.ExecuteNonQuery();
    }

    private SqliteConnection Open()
    {
        var c = new SqliteConnection(_connString);
        c.Open();
        return c;
    }

    public async Task<long> EnqueueAsync(IngestEvent evt, CancellationToken ct = default)
    {
        await _lock.WaitAsync(ct);
        try
        {
            using var conn = Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText =
                "INSERT OR IGNORE INTO events (event_id, cipher) VALUES ($id, $c); SELECT last_insert_rowid();";
            var plaintext = JsonSerializer.SerializeToUtf8Bytes(evt, Json);
            cmd.Parameters.AddWithValue("$id", evt.EventId);
            cmd.Parameters.AddWithValue("$c", _cipher.Encrypt(plaintext));
            var result = await cmd.ExecuteScalarAsync(ct);
            return Convert.ToInt64(result);
        }
        finally { _lock.Release(); }
    }

    public async Task<IReadOnlyList<QueuedEvent>> PeekBatchAsync(int max, CancellationToken ct = default)
    {
        using var conn = Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText =
            "SELECT sequence, cipher FROM events WHERE acked = 0 ORDER BY sequence LIMIT $max;";
        cmd.Parameters.AddWithValue("$max", max);
        var list = new List<QueuedEvent>();
        using var reader = await cmd.ExecuteReaderAsync(ct);
        while (await reader.ReadAsync(ct))
        {
            var seq = reader.GetInt64(0);
            var cipher = (byte[])reader["cipher"];
            var plaintext = _cipher.Decrypt(cipher);
            var evt = JsonSerializer.Deserialize<IngestEvent>(plaintext, Json)!;
            list.Add(new QueuedEvent(seq, evt));
        }
        return list;
    }

    public async Task AckAsync(long throughSequence, CancellationToken ct = default)
    {
        await _lock.WaitAsync(ct);
        try
        {
            using var conn = Open();
            using var cmd = conn.CreateCommand();
            // Delete acked events to bound the file size.
            cmd.CommandText = "DELETE FROM events WHERE sequence <= $seq;";
            cmd.Parameters.AddWithValue("$seq", throughSequence);
            await cmd.ExecuteNonQueryAsync(ct);
        }
        finally { _lock.Release(); }
    }

    public async Task<int> PendingCountAsync(CancellationToken ct = default)
    {
        using var conn = Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM events WHERE acked = 0;";
        return Convert.ToInt32(await cmd.ExecuteScalarAsync(ct));
    }

    public void Dispose() => _lock.Dispose();
}

/// <summary>Encrypts queue payloads at rest. Windows uses DPAPI; tests use a passthrough.</summary>
public interface IPayloadCipher
{
    byte[] Encrypt(byte[] plaintext);
    byte[] Decrypt(byte[] ciphertext);
}

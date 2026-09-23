using Ambic.Print.Storage.Database;
using Ambic.PrintCore.Models;
using Microsoft.Data.Sqlite;

namespace Ambic.Print.Storage.Repositories;

public class IdempotencyStore
{
    private readonly NodeDatabase _db;

    public IdempotencyStore(NodeDatabase db)
    {
        _db = db;
    }

    public (bool IsNew, IdempotencyRecord? Existing) TryAcquire(string key, string sourceNodeId, string jobId, string logicalDestination)
    {
        using var conn = _db.CreateConnection();
        using var checkCmd = conn.CreateCommand();
        checkCmd.CommandText = "SELECT key, source_node_id, job_id, logical_destination, created_at_utc, expires_at_utc FROM idempotency_keys WHERE key = @key AND source_node_id = @source;";
        checkCmd.Parameters.AddWithValue("@key", key);
        checkCmd.Parameters.AddWithValue("@source", sourceNodeId);

        using (var reader = checkCmd.ExecuteReader())
        {
            if (reader.Read())
            {
                return (false, new IdempotencyRecord
                {
                    Key = reader.GetString(0),
                    SourceNodeId = reader.GetString(1),
                    JobId = reader.GetString(2),
                    LogicalDestination = reader.GetString(3),
                    CreatedAtUtc = DateTime.Parse(reader.GetString(4)),
                    ExpiresAtUtc = DateTime.Parse(reader.GetString(5))
                });
            }
        }

        using var insertCmd = conn.CreateCommand();
        insertCmd.CommandText = @"
            INSERT INTO idempotency_keys (key, source_node_id, job_id, logical_destination, created_at_utc, expires_at_utc)
            VALUES (@key, @source, @jobId, @dest, @created, @expires);
        ";
        var now = DateTime.UtcNow;
        var expires = now.AddDays(7);
        insertCmd.Parameters.AddWithValue("@key", key);
        insertCmd.Parameters.AddWithValue("@source", sourceNodeId);
        insertCmd.Parameters.AddWithValue("@jobId", jobId);
        insertCmd.Parameters.AddWithValue("@dest", logicalDestination);
        insertCmd.Parameters.AddWithValue("@created", now.ToString("O"));
        insertCmd.Parameters.AddWithValue("@expires", expires.ToString("O"));

        try
        {
            insertCmd.ExecuteNonQuery();
            return (true, null);
        }
        catch (SqliteException ex) when (ex.SqliteErrorCode == 19) // Constraint violation
        {
            return TryAcquire(key, sourceNodeId, jobId, logicalDestination);
        }
    }

    public void PurgeExpired()
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "DELETE FROM idempotency_keys WHERE expires_at_utc < @now;";
        cmd.Parameters.AddWithValue("@now", DateTime.UtcNow.ToString("O"));
        cmd.ExecuteNonQuery();
    }
}

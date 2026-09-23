using Ambic.Print.Storage.Database;
using Ambic.PrintCore.Models;
using Microsoft.Data.Sqlite;

namespace Ambic.Print.Storage.Repositories;

public class JobRepository
{
    private readonly NodeDatabase _db;

    public JobRepository(NodeDatabase db)
    {
        _db = db;
    }

    public void SaveJob(PrintJob job)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            INSERT INTO print_jobs (
                job_id, idempotency_key, document_type, logical_destination,
                target_physical_printer_id, source_node_id, source_process, source_user,
                copies, payload_type, payload_file_path, sha256_hash, state, state_detail,
                matched_rule_id, rule_version, created_at_utc, updated_at_utc
            ) VALUES (
                @id, @idem, @docType, @dest,
                @physId, @sourceNode, @sourceProc, @sourceUser,
                @copies, @payloadType, @payloadPath, @hash, @state, @detail,
                @ruleId, @ruleVer, @created, @updated
            )
            ON CONFLICT(job_id) DO UPDATE SET
                state = excluded.state,
                state_detail = excluded.state_detail,
                target_physical_printer_id = excluded.target_physical_printer_id,
                payload_file_path = excluded.payload_file_path,
                updated_at_utc = excluded.updated_at_utc;
        ";
        cmd.Parameters.AddWithValue("@id", job.JobId);
        cmd.Parameters.AddWithValue("@idem", job.IdempotencyKey);
        cmd.Parameters.AddWithValue("@docType", job.DocumentType);
        cmd.Parameters.AddWithValue("@dest", job.LogicalDestination);
        cmd.Parameters.AddWithValue("@physId", (object?)job.TargetPhysicalPrinterId ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@sourceNode", job.SourceNodeId);
        cmd.Parameters.AddWithValue("@sourceProc", (object?)job.SourceProcess ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@sourceUser", (object?)job.SourceUser ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@copies", job.Copies);
        cmd.Parameters.AddWithValue("@payloadType", (int)job.PayloadType);
        cmd.Parameters.AddWithValue("@payloadPath", (object?)job.PayloadFilePath ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@hash", (object?)job.Sha256Hash ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@state", (int)job.State);
        cmd.Parameters.AddWithValue("@detail", (object?)job.StateDetail ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@ruleId", (object?)job.MatchedRuleId ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@ruleVer", (object?)job.RuleVersion ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@created", job.CreatedAtUtc.ToString("O"));
        cmd.Parameters.AddWithValue("@updated", DateTime.UtcNow.ToString("O"));

        cmd.ExecuteNonQuery();
    }

    public void AddEvent(string jobId, JobState state, string nodeId, string detail)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            INSERT INTO job_events (job_id, timestamp_utc, state, node_id, detail)
            VALUES (@jobId, @ts, @state, @nodeId, @detail);
        ";
        cmd.Parameters.AddWithValue("@jobId", jobId);
        cmd.Parameters.AddWithValue("@ts", DateTime.UtcNow.ToString("O"));
        cmd.Parameters.AddWithValue("@state", (int)state);
        cmd.Parameters.AddWithValue("@nodeId", nodeId);
        cmd.Parameters.AddWithValue("@detail", detail);
        cmd.ExecuteNonQuery();
    }

    public PrintJob? GetJob(string jobId)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT job_id, idempotency_key, document_type, logical_destination,
                   target_physical_printer_id, source_node_id, source_process, source_user,
                   copies, payload_type, payload_file_path, sha256_hash, state, state_detail,
                   matched_rule_id, rule_version, created_at_utc, updated_at_utc
            FROM print_jobs WHERE job_id = @id;
        ";
        cmd.Parameters.AddWithValue("@id", jobId);
        using var reader = cmd.ExecuteReader();
        if (!reader.Read()) return null;

        return new PrintJob
        {
            JobId = reader.GetString(0),
            IdempotencyKey = reader.GetString(1),
            DocumentType = reader.GetString(2),
            LogicalDestination = reader.GetString(3),
            TargetPhysicalPrinterId = reader.IsDBNull(4) ? null : reader.GetString(4),
            SourceNodeId = reader.GetString(5),
            SourceProcess = reader.IsDBNull(6) ? "" : reader.GetString(6),
            SourceUser = reader.IsDBNull(7) ? "" : reader.GetString(7),
            Copies = reader.GetInt32(8),
            PayloadType = (PayloadType)reader.GetInt32(9),
            PayloadFilePath = reader.IsDBNull(10) ? null : reader.GetString(10),
            Sha256Hash = reader.IsDBNull(11) ? null : reader.GetString(11),
            State = (JobState)reader.GetInt32(12),
            StateDetail = reader.IsDBNull(13) ? null : reader.GetString(13),
            MatchedRuleId = reader.IsDBNull(14) ? null : reader.GetString(14),
            RuleVersion = reader.IsDBNull(15) ? null : reader.GetString(15),
            CreatedAtUtc = DateTime.Parse(reader.GetString(16)),
            UpdatedAtUtc = DateTime.Parse(reader.GetString(17))
        };
    }

    public List<PrintJob> GetRecentJobs(int limit = 50)
    {
        var list = new List<PrintJob>();
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT job_id, idempotency_key, document_type, logical_destination,
                   target_physical_printer_id, source_node_id, source_process, source_user,
                   copies, payload_type, payload_file_path, sha256_hash, state, state_detail,
                   matched_rule_id, rule_version, created_at_utc, updated_at_utc
            FROM print_jobs ORDER BY created_at_utc DESC LIMIT @limit;
        ";
        cmd.Parameters.AddWithValue("@limit", limit);
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            list.Add(new PrintJob
            {
                JobId = reader.GetString(0),
                IdempotencyKey = reader.GetString(1),
                DocumentType = reader.GetString(2),
                LogicalDestination = reader.GetString(3),
                TargetPhysicalPrinterId = reader.IsDBNull(4) ? null : reader.GetString(4),
                SourceNodeId = reader.GetString(5),
                SourceProcess = reader.IsDBNull(6) ? "" : reader.GetString(6),
                SourceUser = reader.IsDBNull(7) ? "" : reader.GetString(7),
                Copies = reader.GetInt32(8),
                PayloadType = (PayloadType)reader.GetInt32(9),
                PayloadFilePath = reader.IsDBNull(10) ? null : reader.GetString(10),
                Sha256Hash = reader.IsDBNull(11) ? null : reader.GetString(11),
                State = (JobState)reader.GetInt32(12),
                StateDetail = reader.IsDBNull(13) ? null : reader.GetString(13),
                MatchedRuleId = reader.IsDBNull(14) ? null : reader.GetString(14),
                RuleVersion = reader.IsDBNull(15) ? null : reader.GetString(15),
                CreatedAtUtc = DateTime.Parse(reader.GetString(16)),
                UpdatedAtUtc = DateTime.Parse(reader.GetString(17))
            });
        }
        return list;
    }
}

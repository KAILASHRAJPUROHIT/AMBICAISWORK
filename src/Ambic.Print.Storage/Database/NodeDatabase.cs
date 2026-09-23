using Microsoft.Data.Sqlite;

namespace Ambic.Print.Storage.Database;

public class NodeDatabase
{
    private readonly string _connectionString;

    public NodeDatabase(string dbPath)
    {
        var dir = Path.GetDirectoryName(dbPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
        {
            Directory.CreateDirectory(dir);
        }
        _connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = dbPath,
            Mode = SqliteOpenMode.ReadWriteCreate
        }.ToString();

        InitializeSchema();
    }

    public SqliteConnection CreateConnection()
    {
        var conn = new SqliteConnection(_connectionString);
        conn.Open();
        return conn;
    }

    private void InitializeSchema()
    {
        using var conn = CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;

            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                friendly_name TEXT NOT NULL,
                host_ip TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 8447,
                role TEXT NOT NULL DEFAULT 'PrintNode',
                os_version TEXT,
                service_version TEXT,
                is_dell_authority INTEGER NOT NULL DEFAULT 0,
                is_online INTEGER NOT NULL DEFAULT 1,
                last_heartbeat_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS physical_printers (
                printer_id TEXT PRIMARY KEY,
                friendly_name TEXT NOT NULL,
                manufacturer TEXT,
                model TEXT,
                connection INTEGER NOT NULL,
                host_node_id TEXT,
                host_ip TEXT,
                windows_queue_name TEXT,
                port_name TEXT,
                driver_name TEXT,
                pnp_device_id TEXT,
                usb_vid TEXT,
                usb_pid TEXT,
                usb_serial TEXT,
                mac_address TEXT,
                type INTEGER NOT NULL,
                supports_duplex INTEGER NOT NULL DEFAULT 0,
                supports_color INTEGER NOT NULL DEFAULT 0,
                paper_sizes TEXT,
                supported_languages TEXT,
                is_online INTEGER NOT NULL DEFAULT 1,
                status_detail TEXT,
                last_seen_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS logical_printers (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                required_type INTEGER NOT NULL,
                requires_duplex INTEGER NOT NULL DEFAULT 0,
                default_fallback_id TEXT
            );

            CREATE TABLE IF NOT EXISTS printer_bindings (
                logical_id TEXT PRIMARY KEY,
                physical_printer_id TEXT NOT NULL,
                primary_host_node_id TEXT NOT NULL,
                fallback_logical_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS print_jobs (
                job_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL,
                document_type TEXT NOT NULL,
                logical_destination TEXT NOT NULL,
                target_physical_printer_id TEXT,
                source_node_id TEXT NOT NULL,
                source_process TEXT,
                source_user TEXT,
                copies INTEGER NOT NULL DEFAULT 1,
                payload_type INTEGER NOT NULL,
                payload_file_path TEXT,
                sha256_hash TEXT,
                state INTEGER NOT NULL,
                state_detail TEXT,
                matched_rule_id TEXT,
                rule_version TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                state INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                detail TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                logical_destination TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                expires_at_utc TEXT NOT NULL,
                PRIMARY KEY (key, source_node_id)
            );

            CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys(expires_at_utc);
            CREATE INDEX IF NOT EXISTS idx_jobs_state ON print_jobs(state);
            CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id);
        ";
        cmd.ExecuteNonQuery();
    }
}

using Ambic.Print.Storage.Database;
using Ambic.PrintCore.Config;
using Ambic.PrintCore.Models;
using Microsoft.Data.Sqlite;

namespace Ambic.Print.Storage.Repositories;

public class TopologyRepository
{
    private readonly NodeDatabase _db;

    public TopologyRepository(NodeDatabase db)
    {
        _db = db;
        EnsureSeeded();
    }

    private void EnsureSeeded()
    {
        var printers = GetAllPhysicalPrinters();
        if (printers.Count == 0)
        {
            foreach (var node in DefaultTopology.GetNodes())
            {
                UpsertNode(node);
            }
            foreach (var p in DefaultTopology.GetPhysicalPrinters())
            {
                UpsertPhysicalPrinter(p);
            }
            var ruleset = DefaultTopology.CreateDefaultRuleset();
            foreach (var lp in ruleset.LogicalPrinters.Values)
            {
                UpsertLogicalPrinter(lp);
            }
            // Initial bindings
            SetBinding(new PrinterBinding { LogicalId = LogicalPrinterId.OfficeA4, PhysicalPrinterId = "PRN-P1007", PrimaryHostNodeId = DefaultTopology.BillingPc1NodeId, FallbackLogicalId = LogicalPrinterId.CustomerA4 });
            SetBinding(new PrinterBinding { LogicalId = LogicalPrinterId.CustomerA4, PhysicalPrinterId = "PRN-HP355", PrimaryHostNodeId = "" });
            SetBinding(new PrinterBinding { LogicalId = LogicalPrinterId.JewelleryLabel, PhysicalPrinterId = "PRN-ZEBRA", PrimaryHostNodeId = DefaultTopology.BillingPc1NodeId });
            SetBinding(new PrinterBinding { LogicalId = LogicalPrinterId.ProductLabel, PhysicalPrinterId = "PRN-TSC244", PrimaryHostNodeId = DefaultTopology.DevLaptopNodeId });
            SetBinding(new PrinterBinding { LogicalId = LogicalPrinterId.EstimateThermal, PhysicalPrinterId = "PRN-THERMAL", PrimaryHostNodeId = DefaultTopology.GoldPcNodeId });
        }
    }

    public void UpsertNode(NodeInfo node)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            INSERT INTO nodes (node_id, friendly_name, host_ip, port, role, os_version, service_version, is_dell_authority, is_online, last_heartbeat_utc)
            VALUES (@id, @name, @ip, @port, @role, @os, @ver, @isDell, @online, @hb)
            ON CONFLICT(node_id) DO UPDATE SET
                friendly_name = excluded.friendly_name,
                host_ip = excluded.host_ip,
                port = excluded.port,
                is_online = excluded.is_online,
                last_heartbeat_utc = excluded.last_heartbeat_utc;
        ";
        cmd.Parameters.AddWithValue("@id", node.NodeId);
        cmd.Parameters.AddWithValue("@name", node.FriendlyName);
        cmd.Parameters.AddWithValue("@ip", node.HostIp);
        cmd.Parameters.AddWithValue("@port", node.Port);
        cmd.Parameters.AddWithValue("@role", node.Role);
        cmd.Parameters.AddWithValue("@os", (object?)node.OsVersion ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@ver", node.ServiceVersion);
        cmd.Parameters.AddWithValue("@isDell", node.IsDellAuthority ? 1 : 0);
        cmd.Parameters.AddWithValue("@online", node.IsOnline ? 1 : 0);
        cmd.Parameters.AddWithValue("@hb", node.LastHeartbeatUtc.ToString("O"));
        cmd.ExecuteNonQuery();
    }

    public List<NodeInfo> GetAllNodes()
    {
        var list = new List<NodeInfo>();
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT node_id, friendly_name, host_ip, port, role, os_version, service_version, is_dell_authority, is_online, last_heartbeat_utc FROM nodes;";
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            list.Add(new NodeInfo
            {
                NodeId = reader.GetString(0),
                FriendlyName = reader.GetString(1),
                HostIp = reader.GetString(2),
                Port = reader.GetInt32(3),
                Role = reader.GetString(4),
                OsVersion = reader.IsDBNull(5) ? "" : reader.GetString(5),
                ServiceVersion = reader.GetString(6),
                IsDellAuthority = reader.GetInt32(7) == 1,
                IsOnline = reader.GetInt32(8) == 1,
                LastHeartbeatUtc = DateTime.Parse(reader.GetString(9))
            });
        }
        return list;
    }

    public void UpsertPhysicalPrinter(PhysicalPrinter p)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            INSERT INTO physical_printers (
                printer_id, friendly_name, manufacturer, model, connection,
                host_node_id, host_ip, windows_queue_name, port_name, driver_name,
                pnp_device_id, usb_vid, usb_pid, usb_serial, mac_address,
                type, supports_duplex, supports_color, paper_sizes, supported_languages,
                is_online, status_detail, last_seen_utc
            ) VALUES (
                @id, @name, @mfg, @model, @conn,
                @hostNode, @hostIp, @queue, @port, @driver,
                @pnp, @vid, @pid, @serial, @mac,
                @type, @duplex, @color, @sizes, @langs,
                @online, @status, @seen
            )
            ON CONFLICT(printer_id) DO UPDATE SET
                friendly_name = excluded.friendly_name,
                host_node_id = excluded.host_node_id,
                host_ip = excluded.host_ip,
                windows_queue_name = excluded.windows_queue_name,
                port_name = excluded.port_name,
                driver_name = excluded.driver_name,
                pnp_device_id = excluded.pnp_device_id,
                usb_vid = excluded.usb_vid,
                usb_pid = excluded.usb_pid,
                is_online = excluded.is_online,
                status_detail = excluded.status_detail,
                last_seen_utc = excluded.last_seen_utc;
        ";
        cmd.Parameters.AddWithValue("@id", p.PrinterId);
        cmd.Parameters.AddWithValue("@name", p.FriendlyName);
        cmd.Parameters.AddWithValue("@mfg", (object?)p.Manufacturer ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@model", (object?)p.Model ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@conn", (int)p.Connection);
        cmd.Parameters.AddWithValue("@hostNode", (object?)p.HostNodeId ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@hostIp", (object?)p.HostIp ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@queue", p.WindowsQueueName);
        cmd.Parameters.AddWithValue("@port", p.PortName);
        cmd.Parameters.AddWithValue("@driver", p.DriverName);
        cmd.Parameters.AddWithValue("@pnp", (object?)p.PnpDeviceId ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@vid", (object?)p.UsbVid ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@pid", (object?)p.UsbPid ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@serial", (object?)p.UsbSerial ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@mac", (object?)p.MacAddress ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@type", (int)p.Type);
        cmd.Parameters.AddWithValue("@duplex", p.SupportsDuplex ? 1 : 0);
        cmd.Parameters.AddWithValue("@color", p.SupportsColor ? 1 : 0);
        cmd.Parameters.AddWithValue("@sizes", p.PaperSizes);
        cmd.Parameters.AddWithValue("@langs", p.SupportedLanguages);
        cmd.Parameters.AddWithValue("@online", p.IsOnline ? 1 : 0);
        cmd.Parameters.AddWithValue("@status", p.StatusDetail);
        cmd.Parameters.AddWithValue("@seen", p.LastSeenUtc.ToString("O"));
        cmd.ExecuteNonQuery();
    }

    public List<PhysicalPrinter> GetAllPhysicalPrinters()
    {
        var list = new List<PhysicalPrinter>();
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT printer_id, friendly_name, manufacturer, model, connection,
                   host_node_id, host_ip, windows_queue_name, port_name, driver_name,
                   pnp_device_id, usb_vid, usb_pid, usb_serial, mac_address,
                   type, supports_duplex, supports_color, paper_sizes, supported_languages,
                   is_online, status_detail, last_seen_utc
            FROM physical_printers;
        ";
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            list.Add(new PhysicalPrinter
            {
                PrinterId = reader.GetString(0),
                FriendlyName = reader.GetString(1),
                Manufacturer = reader.IsDBNull(2) ? "" : reader.GetString(2),
                Model = reader.IsDBNull(3) ? "" : reader.GetString(3),
                Connection = (ConnectionType)reader.GetInt32(4),
                HostNodeId = reader.IsDBNull(5) ? "" : reader.GetString(5),
                HostIp = reader.IsDBNull(6) ? "" : reader.GetString(6),
                WindowsQueueName = reader.GetString(7),
                PortName = reader.GetString(8),
                DriverName = reader.GetString(9),
                PnpDeviceId = reader.IsDBNull(10) ? null : reader.GetString(10),
                UsbVid = reader.IsDBNull(11) ? null : reader.GetString(11),
                UsbPid = reader.IsDBNull(12) ? null : reader.GetString(12),
                UsbSerial = reader.IsDBNull(13) ? null : reader.GetString(13),
                MacAddress = reader.IsDBNull(14) ? null : reader.GetString(14),
                Type = (PrinterType)reader.GetInt32(15),
                SupportsDuplex = reader.GetInt32(16) == 1,
                SupportsColor = reader.GetInt32(17) == 1,
                PaperSizes = reader.GetString(18),
                SupportedLanguages = reader.GetString(19),
                IsOnline = reader.GetInt32(20) == 1,
                StatusDetail = reader.GetString(21),
                LastSeenUtc = DateTime.Parse(reader.GetString(22))
            });
        }
        return list;
    }

    public void UpsertLogicalPrinter(LogicalPrinter lp)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            INSERT INTO logical_printers (id, display_name, required_type, requires_duplex, default_fallback_id)
            VALUES (@id, @name, @type, @duplex, @fallback)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                required_type = excluded.required_type,
                requires_duplex = excluded.requires_duplex,
                default_fallback_id = excluded.default_fallback_id;
        ";
        cmd.Parameters.AddWithValue("@id", lp.Id);
        cmd.Parameters.AddWithValue("@name", lp.DisplayName);
        cmd.Parameters.AddWithValue("@type", (int)lp.RequiredType);
        cmd.Parameters.AddWithValue("@duplex", lp.RequiresDuplex ? 1 : 0);
        cmd.Parameters.AddWithValue("@fallback", (object?)lp.DefaultFallbackLogicalId ?? DBNull.Value);
        cmd.ExecuteNonQuery();
    }

    public void SetBinding(PrinterBinding binding)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            INSERT INTO printer_bindings (logical_id, physical_printer_id, primary_host_node_id, fallback_logical_id, is_active, updated_at_utc)
            VALUES (@logId, @physId, @hostNode, @fallback, @active, @updated)
            ON CONFLICT(logical_id) DO UPDATE SET
                physical_printer_id = excluded.physical_printer_id,
                primary_host_node_id = excluded.primary_host_node_id,
                fallback_logical_id = excluded.fallback_logical_id,
                is_active = excluded.is_active,
                updated_at_utc = excluded.updated_at_utc;
        ";
        cmd.Parameters.AddWithValue("@logId", binding.LogicalId);
        cmd.Parameters.AddWithValue("@physId", binding.PhysicalPrinterId);
        cmd.Parameters.AddWithValue("@hostNode", binding.PrimaryHostNodeId);
        cmd.Parameters.AddWithValue("@fallback", (object?)binding.FallbackLogicalId ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@active", binding.IsActive ? 1 : 0);
        cmd.Parameters.AddWithValue("@updated", DateTime.UtcNow.ToString("O"));
        cmd.ExecuteNonQuery();
    }

    public PrinterBinding? GetBinding(string logicalId)
    {
        using var conn = _db.CreateConnection();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT logical_id, physical_printer_id, primary_host_node_id, fallback_logical_id, is_active, updated_at_utc FROM printer_bindings WHERE logical_id = @id AND is_active = 1;";
        cmd.Parameters.AddWithValue("@id", logicalId);
        using var reader = cmd.ExecuteReader();
        if (!reader.Read()) return null;

        return new PrinterBinding
        {
            LogicalId = reader.GetString(0),
            PhysicalPrinterId = reader.GetString(1),
            PrimaryHostNodeId = reader.GetString(2),
            FallbackLogicalId = reader.IsDBNull(3) ? null : reader.GetString(3),
            IsActive = reader.GetInt32(4) == 1,
            UpdatedAtUtc = DateTime.Parse(reader.GetString(5))
        };
    }
}

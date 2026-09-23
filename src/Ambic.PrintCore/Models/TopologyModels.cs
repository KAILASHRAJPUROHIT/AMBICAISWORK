namespace Ambic.PrintCore.Models;

public class PhysicalPrinter
{
    public string PrinterId { get; set; } = string.Empty;
    public string FriendlyName { get; set; } = string.Empty;
    public string Manufacturer { get; set; } = string.Empty;
    public string Model { get; set; } = string.Empty;
    public ConnectionType Connection { get; set; } = ConnectionType.Unknown;
    public string HostNodeId { get; set; } = string.Empty;
    public string HostIp { get; set; } = string.Empty;
    public string WindowsQueueName { get; set; } = string.Empty;
    public string PortName { get; set; } = string.Empty;
    public string DriverName { get; set; } = string.Empty;

    // Hardware fingerprints
    public string? PnpDeviceId { get; set; }
    public string? UsbVid { get; set; }
    public string? UsbPid { get; set; }
    public string? UsbSerial { get; set; }
    public string? MacAddress { get; set; }

    // Capabilities
    public PrinterType Type { get; set; } = PrinterType.Unknown;
    public bool SupportsDuplex { get; set; }
    public bool SupportsColor { get; set; }
    public string PaperSizes { get; set; } = "A4";
    public string SupportedLanguages { get; set; } = "RAW";

    public bool IsOnline { get; set; } = true;
    public string StatusDetail { get; set; } = "Ready";
    public DateTime LastSeenUtc { get; set; } = DateTime.UtcNow;
}

public class LogicalPrinter
{
    public string Id { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public PrinterType RequiredType { get; set; } = PrinterType.Unknown;
    public bool RequiresDuplex { get; set; }
    public string? DefaultFallbackLogicalId { get; set; }
}

public class PrinterBinding
{
    public string LogicalId { get; set; } = string.Empty;
    public string PhysicalPrinterId { get; set; } = string.Empty;
    public string PrimaryHostNodeId { get; set; } = string.Empty;
    public string? FallbackLogicalId { get; set; }
    public bool IsActive { get; set; } = true;
    public DateTime UpdatedAtUtc { get; set; } = DateTime.UtcNow;
}

public class NodeInfo
{
    public string NodeId { get; set; } = string.Empty;
    public string FriendlyName { get; set; } = string.Empty;
    public string HostIp { get; set; } = string.Empty;
    public int Port { get; set; } = 8447;
    public string Role { get; set; } = "PrintNode";
    public string OsVersion { get; set; } = string.Empty;
    public string ServiceVersion { get; set; } = "1.0.0";
    public bool IsDellAuthority { get; set; }
    public bool IsOnline { get; set; } = true;
    public DateTime LastHeartbeatUtc { get; set; } = DateTime.UtcNow;
}

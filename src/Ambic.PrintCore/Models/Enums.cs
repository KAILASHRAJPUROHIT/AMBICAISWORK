namespace Ambic.PrintCore.Models;

public static class LogicalPrinterId
{
    public const string OfficeA4 = "OFFICE_A4";
    public const string CustomerA4 = "CUSTOMER_A4";
    public const string JewelleryLabel = "JEWELLERY_LABEL";
    public const string ProductLabel = "PRODUCT_LABEL";
    public const string EstimateThermal = "ESTIMATE_THERMAL";

    public static readonly IReadOnlyList<string> All = new[]
    {
        OfficeA4,
        CustomerA4,
        JewelleryLabel,
        ProductLabel,
        EstimateThermal
    };
}

public enum PrinterType
{
    Unknown = 0,
    A4MonoLaser = 1,
    A4DuplexLaser = 2,
    Label = 3,
    Receipt = 4
}

public enum ConnectionType
{
    Unknown = 0,
    Usb = 1,
    Network = 2,
    Virtual = 3
}

public enum JobState
{
    Received = 0,
    Validated = 1,
    Routed = 2,
    Transferred = 3,
    AcceptedByHost = 4,
    Spooled = 5,
    Completed = 6,
    Failed = 7,
    Held = 8,
    Cancelled = 9
}

public enum PayloadType
{
    Raw = 0,
    Pdf = 1,
    Text = 2,
    Image = 3,
    EscPos = 4,
    Zpl = 5,
    Tspl = 6
}

public enum UncertainRouteAction
{
    SafeFallbackOrHold = 0,
    Hold = 1,
    SafeFallback = 2,
    Reject = 3
}

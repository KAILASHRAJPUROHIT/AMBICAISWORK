namespace Ambic.PrintCore.Models;

public class PrintJob
{
    public string JobId { get; set; } = string.Empty;
    public string IdempotencyKey { get; set; } = string.Empty;
    public string DocumentType { get; set; } = "DOCUMENT";
    public string LogicalDestination { get; set; } = string.Empty;
    public string? TargetPhysicalPrinterId { get; set; }
    public string SourceNodeId { get; set; } = string.Empty;
    public string SourceProcess { get; set; } = string.Empty;
    public string SourceUser { get; set; } = string.Empty;
    public int Copies { get; set; } = 1;
    public PayloadType PayloadType { get; set; } = PayloadType.Raw;
    public string? PayloadFilePath { get; set; }
    public byte[]? PayloadData { get; set; }
    public string? Sha256Hash { get; set; }
    public JobState State { get; set; } = JobState.Received;
    public string? StateDetail { get; set; }
    public string? MatchedRuleId { get; set; }
    public string? RuleVersion { get; set; }
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAtUtc { get; set; } = DateTime.UtcNow;
}

public class JobEvent
{
    public long EventId { get; set; }
    public string JobId { get; set; } = string.Empty;
    public DateTime TimestampUtc { get; set; } = DateTime.UtcNow;
    public JobState State { get; set; }
    public string NodeId { get; set; } = string.Empty;
    public string Detail { get; set; } = string.Empty;
}

public class IdempotencyRecord
{
    public string Key { get; set; } = string.Empty;
    public string SourceNodeId { get; set; } = string.Empty;
    public string JobId { get; set; } = string.Empty;
    public string LogicalDestination { get; set; } = string.Empty;
    public DateTime CreatedAtUtc { get; set; } = DateTime.UtcNow;
    public DateTime ExpiresAtUtc { get; set; } = DateTime.UtcNow.AddDays(7);
}

public class RuleSourceCriteria
{
    public string? Process { get; set; }
    public string? Screen { get; set; }
    public string? Voucher { get; set; }
    public int? Copies { get; set; }
    public string? DocumentType { get; set; }
}

public class RuleAction
{
    public int CopyNumber { get; set; }
    public string Destination { get; set; } = string.Empty; // LogicalPrinterId
    public string? Transform { get; set; } // e.g. CUSTOMER_LETTERHEAD_DUPLEX
    public bool Duplex { get; set; }
}

public class RoutingRule
{
    public string Id { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string Description
    {
        get => string.IsNullOrEmpty(Name) ? _description : Name;
        set { _description = value; if (string.IsNullOrEmpty(Name)) Name = value; }
    }
    private string _description = string.Empty;

    public string TargetProgram { get; set; } = "ONX.exe"; // e.g. ONX.exe, chrome.exe, AcroRd32.exe, *
    public string WindowTitleMatch { get; set; } = "*";    // e.g. Voucher Print, Invoice, *
    public int RequiredCopies { get; set; } = 2;          // 0 = any
    public string ReferenceTemplate { get; set; } = string.Empty; // e.g. office-sales-voucher-format-reference.png
    public string Copy1Printer { get; set; } = "(use configured default)";
    public string LaterPrinter { get; set; } = "(use configured default)";
    public string LetterheadOverlay { get; set; } = "DUPLEX_FRONT_BACK"; // DUPLEX_FRONT_BACK, FRONT_ONLY, NONE
    public bool Duplex { get; set; } = true;
    public bool Enabled { get; set; } = true;
    public string OnMismatch { get; set; } = "P355_ONLY"; // P355_ONLY, HOLD, PROCEED_DEFAULT

    public RuleSourceCriteria Source { get; set; } = new();
    public List<RuleAction> Actions { get; set; } = new();
    public UncertainRouteAction OnUncertain { get; set; } = UncertainRouteAction.SafeFallbackOrHold;
    public string? SafeFallbackDestination { get; set; }
}

public class RouterHubConfig
{
    public bool MasterEnabled { get; set; } = true;
    public bool MasterRoutingEnabled { get => MasterEnabled; set => MasterEnabled = value; }

    public string PcRole { get; set; } = "PC2 (Hub)";
    public string WorkstationRole { get => PcRole; set => PcRole = value; }

    public string Copy1Printer { get; set; } = "P1007 (via PC2)";
    public string DefaultCopy1Printer { get => Copy1Printer; set => Copy1Printer = value; }

    public string Copy2Printer { get; set; } = "355 Letterhead Capture";
    public string DefaultCopy2Printer { get => Copy2Printer; set => Copy2Printer = value; }

    public string BothMode { get; set; } = "Auto (default split: copy 1 -> P1007, copy 2 -> 355)";
    public string BothCopiesMode { get => BothMode; set => BothMode = value; }

    public string ForceCopy1Printer { get; set; } = "";
    public string ForceCopy2Printer { get; set; } = "";
    public List<RoutingRule> Rules { get; set; } = new();
}

public class RulesetConfig
{
    public string Version { get; set; } = "2026.09.22.001";
    public DateTime PublishedAtUtc { get; set; } = DateTime.UtcNow;
    public string PublisherNodeId { get; set; } = "SRV01";
    public Dictionary<string, LogicalPrinter> LogicalPrinters { get; set; } = new();
    public List<RoutingRule> Rules { get; set; } = new();
    public RouterHubConfig? HubSettings { get; set; }
    public string? Signature { get; set; }
}

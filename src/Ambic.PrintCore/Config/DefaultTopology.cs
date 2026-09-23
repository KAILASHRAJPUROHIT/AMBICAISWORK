using Ambic.PrintCore.Models;

namespace Ambic.PrintCore.Config;

public static class DefaultTopology
{
    public const string DellServerNodeId = "SRV01";
    public const string BillingPc1NodeId = "BILL01";
    public const string BillingPc2NodeId = "BILL02";
    public const string DevLaptopNodeId = "DEV01";
    public const string GoldPcNodeId = "GOLD01";

    public static List<NodeInfo> GetNodes() => new()
    {
        new NodeInfo { NodeId = DellServerNodeId, FriendlyName = "Dell Server", HostIp = "192.168.0.100", Role = "ManagementAuthority", IsDellAuthority = true },
        new NodeInfo { NodeId = BillingPc1NodeId, FriendlyName = "Billing PC1", HostIp = "192.168.0.13", Role = "PrintNode" },
        new NodeInfo { NodeId = BillingPc2NodeId, FriendlyName = "Billing PC2", HostIp = "192.168.0.11", Role = "BillingWorkstation" },
        new NodeInfo { NodeId = DevLaptopNodeId, FriendlyName = "Development Laptop", HostIp = "192.168.0.4", Role = "StagingCanary" },
        new NodeInfo { NodeId = GoldPcNodeId, FriendlyName = "Gold Testing PC", HostIp = "192.168.0.15", Role = "PrintNode" },
    };

    public static List<PhysicalPrinter> GetPhysicalPrinters() => new()
    {
        new PhysicalPrinter
        {
            PrinterId = "PRN-P1007",
            FriendlyName = "Office HP P1007",
            Manufacturer = "HP",
            Model = "LaserJet P1007",
            Connection = ConnectionType.Usb,
            HostNodeId = BillingPc1NodeId,
            HostIp = "192.168.0.13",
            WindowsQueueName = "HP LaserJet P1007",
            PortName = "USB001",
            DriverName = "HP LaserJet P1007",
            Type = PrinterType.A4MonoLaser,
            SupportsDuplex = false,
            PaperSizes = "A4",
            SupportedLanguages = "RAW,GDI"
        },
        new PhysicalPrinter
        {
            PrinterId = "PRN-HP355",
            FriendlyName = "Customer HP 355sdnw",
            Manufacturer = "HP",
            Model = "Laser MFP 330/355",
            Connection = ConnectionType.Network,
            HostNodeId = "", // Direct network printer
            HostIp = "192.168.0.14",
            WindowsQueueName = "HP Laser MFP 330",
            PortName = "192.168.0.14",
            DriverName = "HP Laser MFP 330",
            Type = PrinterType.A4DuplexLaser,
            SupportsDuplex = true,
            PaperSizes = "A4",
            SupportedLanguages = "RAW,PCL,PDF"
        },
        new PhysicalPrinter
        {
            PrinterId = "PRN-ZEBRA",
            FriendlyName = "Jewellery Zebra Label",
            Manufacturer = "Zebra",
            Model = "Zebra Label Printer",
            Connection = ConnectionType.Usb,
            HostNodeId = BillingPc1NodeId,
            HostIp = "192.168.0.13",
            WindowsQueueName = "Zebra",
            PortName = "USB002",
            DriverName = "Zebra ZPL Driver",
            Type = PrinterType.Label,
            SupportedLanguages = "ZPL,RAW"
        },
        new PhysicalPrinter
        {
            PrinterId = "PRN-TSC244",
            FriendlyName = "Product TSC TE244",
            Manufacturer = "TSC",
            Model = "TE244",
            Connection = ConnectionType.Usb,
            HostNodeId = DevLaptopNodeId,
            HostIp = "192.168.0.4",
            WindowsQueueName = "TSC TE244",
            PortName = "USB001",
            DriverName = "TSC TE244",
            UsbVid = "1203",
            UsbPid = "0272",
            PnpDeviceId = @"USB\VID_1203&PID_0272",
            Type = PrinterType.Label,
            SupportedLanguages = "TSPL,RAW"
        },
        new PhysicalPrinter
        {
            PrinterId = "PRN-THERMAL",
            FriendlyName = "Estimate Thermal Printer",
            Manufacturer = "Thermal",
            Model = "ESC/POS Receipt 80mm",
            Connection = ConnectionType.Usb,
            HostNodeId = GoldPcNodeId,
            HostIp = "192.168.0.15",
            WindowsQueueName = "Thermal Printer",
            PortName = "USB001",
            DriverName = "Generic / Text Only",
            Type = PrinterType.Receipt,
            SupportedLanguages = "ESC_POS,RAW"
        }
    };

    public static RulesetConfig CreateDefaultRuleset()
    {
        var config = new RulesetConfig
        {
            Version = "2026.09.22.001",
            PublishedAtUtc = DateTime.UtcNow,
            PublisherNodeId = DellServerNodeId,
            LogicalPrinters = new()
            {
                [LogicalPrinterId.OfficeA4] = new LogicalPrinter
                {
                    Id = LogicalPrinterId.OfficeA4,
                    DisplayName = "Office A4 (Pre-printed letterhead)",
                    RequiredType = PrinterType.A4MonoLaser,
                    RequiresDuplex = false,
                    DefaultFallbackLogicalId = LogicalPrinterId.CustomerA4
                },
                [LogicalPrinterId.CustomerA4] = new LogicalPrinter
                {
                    Id = LogicalPrinterId.CustomerA4,
                    DisplayName = "Customer A4 (Duplex with T&C)",
                    RequiredType = PrinterType.A4DuplexLaser,
                    RequiresDuplex = true
                },
                [LogicalPrinterId.JewelleryLabel] = new LogicalPrinter
                {
                    Id = LogicalPrinterId.JewelleryLabel,
                    DisplayName = "Jewellery Label",
                    RequiredType = PrinterType.Label
                },
                [LogicalPrinterId.ProductLabel] = new LogicalPrinter
                {
                    Id = LogicalPrinterId.ProductLabel,
                    DisplayName = "Product Label (TSC)",
                    RequiredType = PrinterType.Label
                },
                [LogicalPrinterId.EstimateThermal] = new LogicalPrinter
                {
                    Id = LogicalPrinterId.EstimateThermal,
                    DisplayName = "Estimate Thermal (Tablet)",
                    RequiredType = PrinterType.Receipt
                }
            },
            Rules = CreateDefaultRules(),
            HubSettings = CreateDefaultHubConfig()
        };

        return config;
    }

    public static List<RoutingRule> CreateDefaultRules() => new()
    {
        new RoutingRule
        {
            Id = "ORNATE-GST-SALE-001",
            Name = "GST Sales Voucher (A4) Shree Aradhana",
            TargetProgram = "ONX.exe",
            WindowTitleMatch = "Voucher Print",
            RequiredCopies = 2,
            ReferenceTemplate = "office-sales-voucher-format-reference.png",
            Copy1Printer = "(use configured default)",
            LaterPrinter = "(use configured default)",
            LetterheadOverlay = "DUPLEX_FRONT_BACK",
            Duplex = true,
            Enabled = true,
            OnMismatch = "P355_ONLY",
            Source = new RuleSourceCriteria
            {
                Process = "ONX.exe",
                Screen = "Voucher Print",
                Voucher = "GST Sales Voucher",
                Copies = 2
            },
            Actions = new()
            {
                new RuleAction { CopyNumber = 1, Destination = LogicalPrinterId.OfficeA4 },
                new RuleAction { CopyNumber = 2, Destination = LogicalPrinterId.CustomerA4, Transform = "CUSTOMER_LETTERHEAD_DUPLEX", Duplex = true }
            },
            OnUncertain = UncertainRouteAction.SafeFallbackOrHold,
            SafeFallbackDestination = LogicalPrinterId.CustomerA4
        },
        new RoutingRule
        {
            Id = "TABLET-ESTIMATE-001",
            Name = "Tablet Estimate Thermal Receipt Print",
            TargetProgram = "*",
            WindowTitleMatch = "*",
            RequiredCopies = 1,
            ReferenceTemplate = "",
            Copy1Printer = "(use configured default)",
            LaterPrinter = "(use configured default)",
            LetterheadOverlay = "NONE",
            Duplex = false,
            Enabled = true,
            Source = new RuleSourceCriteria
            {
                DocumentType = "ESTIMATE"
            },
            Actions = new()
            {
                new RuleAction { CopyNumber = 1, Destination = LogicalPrinterId.EstimateThermal }
            },
            OnUncertain = UncertainRouteAction.Hold
        },
        new RoutingRule
        {
            Id = "JEWELLERY-LABEL-001",
            Name = "Jewellery Barcode Tag (Zebra)",
            TargetProgram = "ZebraLabel",
            WindowTitleMatch = "*",
            RequiredCopies = 1,
            ReferenceTemplate = "",
            Copy1Printer = "(use configured default)",
            LaterPrinter = "(use configured default)",
            LetterheadOverlay = "NONE",
            Duplex = false,
            Enabled = true,
            Source = new RuleSourceCriteria
            {
                DocumentType = "JEWELLERY_LABEL"
            },
            Actions = new()
            {
                new RuleAction { CopyNumber = 1, Destination = LogicalPrinterId.JewelleryLabel }
            },
            OnUncertain = UncertainRouteAction.Hold
        },
        new RoutingRule
        {
            Id = "PRODUCT-LABEL-001",
            Name = "Product Barcode Tag (TSC TE244)",
            TargetProgram = "TSCLabel",
            WindowTitleMatch = "*",
            RequiredCopies = 1,
            ReferenceTemplate = "",
            Copy1Printer = "(use configured default)",
            LaterPrinter = "(use configured default)",
            LetterheadOverlay = "NONE",
            Duplex = false,
            Enabled = true,
            Source = new RuleSourceCriteria
            {
                DocumentType = "PRODUCT_LABEL"
            },
            Actions = new()
            {
                new RuleAction { CopyNumber = 1, Destination = LogicalPrinterId.ProductLabel }
            },
            OnUncertain = UncertainRouteAction.Hold
        },
        new RoutingRule
        {
            Id = "GENERIC-DOC-001",
            Name = "Generic A4 Document",
            TargetProgram = "*",
            WindowTitleMatch = "*",
            RequiredCopies = 1,
            ReferenceTemplate = "",
            Copy1Printer = "(use configured default)",
            LaterPrinter = "(use configured default)",
            LetterheadOverlay = "NONE",
            Duplex = true,
            Enabled = true,
            Source = new RuleSourceCriteria
            {
                Process = "*",
                DocumentType = "DOCUMENT"
            },
            Actions = new()
            {
                new RuleAction { CopyNumber = 1, Destination = LogicalPrinterId.CustomerA4, Duplex = true }
            },
            OnUncertain = UncertainRouteAction.SafeFallbackOrHold,
            SafeFallbackDestination = LogicalPrinterId.CustomerA4
        }
    };

    public static RouterHubConfig CreateDefaultHubConfig() => new()
    {
        MasterEnabled = true,
        PcRole = "PC2 (Hub)",
        Copy1Printer = "P1007 (via PC2)",
        Copy2Printer = "355 Letterhead Capture",
        BothMode = "SPLIT",
        ForceCopy1Printer = "",
        ForceCopy2Printer = "",
        Rules = CreateDefaultRules()
    };
}

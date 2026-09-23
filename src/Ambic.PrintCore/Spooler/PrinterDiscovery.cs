using System.Runtime.InteropServices;
using Ambic.PrintCore.Models;

namespace Ambic.PrintCore.Spooler;

public class DiscoveredPrinter
{
    public string Name { get; set; } = string.Empty;
    public string PortName { get; set; } = string.Empty;
    public string DriverName { get; set; } = string.Empty;
    public bool IsDefault { get; set; }
    public bool IsNetwork { get; set; }
    public bool IsOnline { get; set; } = true;
    public string Status { get; set; } = "Ready";
}

public static class PrinterDiscovery
{
    [Flags]
    private enum PrinterEnumFlags : uint
    {
        PRINTER_ENUM_DEFAULT = 0x00000001,
        PRINTER_ENUM_LOCAL = 0x00000002,
        PRINTER_ENUM_CONNECTIONS = 0x00000004,
        PRINTER_ENUM_NAME = 0x00000008,
        PRINTER_ENUM_REMOTE = 0x00000010,
        PRINTER_ENUM_SHARED = 0x00000020,
        PRINTER_ENUM_NETWORK = 0x00000040
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private struct PRINTER_INFO_2
    {
        public string pServerName;
        public string pPrinterName;
        public string pShareName;
        public string pPortName;
        public string pDriverName;
        public string pComment;
        public string pLocation;
        public IntPtr pDevMode;
        public string pSepFile;
        public string pPrintProcessor;
        public string pDatatype;
        public string pParameters;
        public IntPtr pSecurityDescriptor;
        public uint Attributes;
        public uint Priority;
        public uint DefaultPriority;
        public uint StartTime;
        public uint UntilTime;
        public uint Status;
        public uint cJobs;
        public uint AveragePPM;
    }

    [DllImport("winspool.drv", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool EnumPrinters(PrinterEnumFlags flags, string? name, uint level, IntPtr pPrinterEnum, uint cbBuf, out uint pcbNeeded, out uint pcReturned);

    public static List<DiscoveredPrinter> DiscoverLocalPrinters()
    {
        var result = new List<DiscoveredPrinter>();
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            return result;

        const uint level = 2;
        var flags = PrinterEnumFlags.PRINTER_ENUM_LOCAL | PrinterEnumFlags.PRINTER_ENUM_CONNECTIONS;

        EnumPrinters(flags, null, level, IntPtr.Zero, 0, out var needed, out _);
        if (needed == 0) return result;

        var pBuffer = Marshal.AllocHGlobal((int)needed);
        try
        {
            if (EnumPrinters(flags, null, level, pBuffer, needed, out _, out var count))
            {
                var offset = pBuffer;
                var structSize = Marshal.SizeOf<PRINTER_INFO_2>();

                for (var i = 0; i < count; i++)
                {
                    var info = Marshal.PtrToStructure<PRINTER_INFO_2>(offset);
                    var isNet = (info.Attributes & 0x00000010) != 0 || info.pPortName.Contains('.') || info.pPortName.StartsWith(@"\\");
                    var isOff = (info.Status & 0x00000080) != 0 || (info.Attributes & 0x00000400) != 0; // PRINTER_STATUS_OFFLINE or WORK_OFFLINE

                    result.Add(new DiscoveredPrinter
                    {
                        Name = info.pPrinterName,
                        PortName = info.pPortName,
                        DriverName = info.pDriverName,
                        IsDefault = (info.Attributes & 0x00000004) != 0,
                        IsNetwork = isNet,
                        IsOnline = !isOff,
                        Status = isOff ? "Offline" : "Ready"
                    });

                    offset += structSize;
                }
            }
        }
        catch
        {
            // Logging or fallback handled by caller
        }
        finally
        {
            Marshal.FreeHGlobal(pBuffer);
        }

        return result;
    }
}

using System.Runtime.InteropServices;
using Ambic.PrintCore.Models;

namespace Ambic.PrintCore.Spooler;

public static class Win32Spooler
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    public struct DOCINFOA
    {
        [MarshalAs(UnmanagedType.LPStr)] public string pDocName;
        [MarshalAs(UnmanagedType.LPStr)] public string? pOutputFile;
        [MarshalAs(UnmanagedType.LPStr)] public string pDataType;
    }

    [DllImport("winspool.drv", EntryPoint = "OpenPrinterA", SetLastError = true, CharSet = CharSet.Ansi, ExactSpelling = true, CallingConvention = CallingConvention.StdCall)]
    public static extern bool OpenPrinter([MarshalAs(UnmanagedType.LPStr)] string szPrinter, out IntPtr hPrinter, IntPtr pd);

    [DllImport("winspool.drv", EntryPoint = "ClosePrinter", SetLastError = true, ExactSpelling = true, CallingConvention = CallingConvention.StdCall)]
    public static extern bool ClosePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", EntryPoint = "StartDocPrinterA", SetLastError = true, CharSet = CharSet.Ansi, ExactSpelling = true, CallingConvention = CallingConvention.StdCall)]
    public static extern int StartDocPrinter(IntPtr hPrinter, int level, [In] ref DOCINFOA di);

    [DllImport("winspool.drv", EntryPoint = "EndDocPrinter", SetLastError = true, ExactSpelling = true, CallingConvention = CallingConvention.StdCall)]
    public static extern bool EndDocPrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", EntryPoint = "StartPagePrinter", SetLastError = true, ExactSpelling = true, CallingConvention = CallingConvention.StdCall)]
    public static extern bool StartPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", EntryPoint = "EndPagePrinter", SetLastError = true, ExactSpelling = true, CallingConvention = CallingConvention.StdCall)]
    public static extern bool EndPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", EntryPoint = "WritePrinter", SetLastError = true, ExactSpelling = true, CallingConvention = CallingConvention.StdCall)]
    public static extern bool WritePrinter(IntPtr hPrinter, IntPtr pBytes, int dwCount, out int dwWritten);

    public static (bool Success, string? Error) SendRawBytes(string printerQueueName, byte[] data, string docName = "APC Print Job", string dataType = "RAW")
    {
        if (string.IsNullOrWhiteSpace(printerQueueName))
            return (false, "Printer queue name cannot be empty");

        if (!OpenPrinter(printerQueueName, out var hPrinter, IntPtr.Zero))
        {
            var err = Marshal.GetLastWin32Error();
            return (false, $"OpenPrinter failed for '{printerQueueName}' with error {err}");
        }

        try
        {
            var di = new DOCINFOA
            {
                pDocName = docName,
                pDataType = dataType
            };

            var job = StartDocPrinter(hPrinter, 1, ref di);
            if (job <= 0)
            {
                var err = Marshal.GetLastWin32Error();
                return (false, $"StartDocPrinter failed for '{printerQueueName}' with error {err}");
            }

            try
            {
                if (!StartPagePrinter(hPrinter))
                {
                    var err = Marshal.GetLastWin32Error();
                    return (false, $"StartPagePrinter failed with error {err}");
                }

                var pUnmanagedBytes = Marshal.AllocHGlobal(data.Length);
                try
                {
                    Marshal.Copy(data, 0, pUnmanagedBytes, data.Length);
                    if (!WritePrinter(hPrinter, pUnmanagedBytes, data.Length, out var written) || written != data.Length)
                    {
                        var err = Marshal.GetLastWin32Error();
                        return (false, $"WritePrinter wrote {written} of {data.Length} bytes with error {err}");
                    }
                }
                finally
                {
                    Marshal.FreeHGlobal(pUnmanagedBytes);
                    EndPagePrinter(hPrinter);
                }
            }
            finally
            {
                EndDocPrinter(hPrinter);
            }

            return (true, null);
        }
        finally
        {
            ClosePrinter(hPrinter);
        }
    }

    public static (bool Success, string? Error) SendRawFile(string printerQueueName, string filePath, string docName = "APC Print Job")
    {
        if (!File.Exists(filePath))
            return (false, $"File not found: {filePath}");

        try
        {
            var bytes = File.ReadAllBytes(filePath);
            return SendRawBytes(printerQueueName, bytes, docName);
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }
}

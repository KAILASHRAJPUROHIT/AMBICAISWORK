// Ornate Spool Observer — READ-ONLY diagnostic.
//
// Purpose: watch the real Windows print spooler (not the Voucher Print dialog)
// and log, for every job that lands on any local printer, the structured facts
// the spooler itself knows: document/job name, requested copy count (read from
// the job's DEVMODE, dmCopies — the same field GDI fills from the app's own
// print-dialog selection), submitter, and timing. This exists to validate —
// across many real copies/voucher/timing combinations — whether the spooler
// consistently reports the true copy count, as a candidate replacement for the
// fragile "scrape the Voucher Print dialog" approach.
//
// This process calls only OpenPrinter/EnumJobs/ClosePrinter (enumeration and
// read). It never calls SetJob, ScheduleJob, DeletePrinter, or anything that
// pauses, cancels, redirects, or modifies a job. It must run standalone,
// observing in parallel with the existing router, until its output has been
// checked against enough real bills to trust it. It is not installed, not
// auto-started, and not wired into any routing decision.
using System;
using System.Collections.Generic;
using System.Drawing.Printing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

internal static class OrnateSpoolObserver
{
    private const int PollIntervalMs = 500;
    private static readonly string LogPath = @"C:\PrintBridge\routing_diagnostics\spool_observer.log";
    private static readonly HashSet<string> SeenJobs = new HashSet<string>();
    private static readonly HashSet<string> LoggedSkips = new HashSet<string>();

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct JOB_INFO_2
    {
        public int JobId;
        public string pPrinterName;
        public string pMachineName;
        public string pUserName;
        public string pDocument;
        public string pNotifyName;
        public string pDatatype;
        public string pPrintProcessor;
        public string pParameters;
        public string pDriverName;
        public IntPtr pDevMode;
        public string pStatus;
        public IntPtr pSecurityDescriptor;
        public int Status;
        public int Priority;
        public int Position;
        public int StartTime;
        public int UntilTime;
        public int TotalPages;
        public int Size;
        public SYSTEMTIME Submitted;
        public int Time;
        public int PagesPrinted;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SYSTEMTIME
    {
        public short Year, Month, DayOfWeek, Day, Hour, Minute, Second, Milliseconds;
    }

    // Only the leading fields of DEVMODE, through dmCopies. PtrToStructure only
    // reads as many bytes as this struct declares, so the (much larger) real
    // DEVMODE buffer is left untouched; this is the standard minimal-read trick.
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct DEVMODE_COPIES
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public short dmOrientation;
        public short dmPaperSize;
        public short dmPaperLength;
        public short dmPaperWidth;
        public short dmScale;
        public short dmCopies;
    }

    [DllImport("winspool.drv", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool OpenPrinter(string pPrinterName, out IntPtr phPrinter, IntPtr pDefault);

    [DllImport("winspool.drv", SetLastError = true)]
    private static extern bool ClosePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool EnumJobs(IntPtr hPrinter, int firstJob, int noJobs, int level,
        IntPtr pJob, int cbBuf, out int pcbNeeded, out int pcReturned);

    private static int Main()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(LogPath));
        Log("=== Ornate Spool Observer starting (read-only; Ctrl+C to stop) ===");

        while (true)
        {
            try
            {
                foreach (string printerName in PrinterSettings.InstalledPrinters)
                {
                    PollPrinter(printerName);
                }
            }
            catch (Exception ex)
            {
                Log("OBSERVER ERROR (will retry): " + ex.Message);
            }
            Thread.Sleep(PollIntervalMs);
        }
    }

    private static void PollPrinter(string printerName)
    {
        IntPtr hPrinter;
        if (!OpenPrinter(printerName, out hPrinter, IntPtr.Zero))
        {
            if (LoggedSkips.Add(printerName))
                Log("PRINTER SKIP (cannot open, will not retry-log): " + printerName +
                    " err=" + Marshal.GetLastWin32Error());
            return;
        }

        try
        {
            int cbNeeded, jobCount;
            EnumJobs(hPrinter, 0, 256, 2, IntPtr.Zero, 0, out cbNeeded, out jobCount);
            if (cbNeeded <= 0) return; // No jobs currently queued.

            IntPtr buffer = Marshal.AllocHGlobal(cbNeeded);
            try
            {
                if (!EnumJobs(hPrinter, 0, 256, 2, buffer, cbNeeded, out cbNeeded, out jobCount))
                {
                    Log("ENUMJOBS FAILED printer=\"" + printerName + "\" err=" + Marshal.GetLastWin32Error());
                    return;
                }

                int structSize = Marshal.SizeOf(typeof(JOB_INFO_2));
                for (int i = 0; i < jobCount; i++)
                {
                    IntPtr entry = new IntPtr(buffer.ToInt64() + i * structSize);
                    JOB_INFO_2 job = (JOB_INFO_2)Marshal.PtrToStructure(entry, typeof(JOB_INFO_2));
                    LogJobIfNew(printerName, job);
                }
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
        finally
        {
            ClosePrinter(hPrinter);
        }
    }

    private static void LogJobIfNew(string printerName, JOB_INFO_2 job)
    {
        string key = printerName + "#" + job.JobId;
        if (!SeenJobs.Add(key)) return; // Already logged this job.

        string copies = "n/a (no DEVMODE)";
        if (job.pDevMode != IntPtr.Zero)
        {
            try
            {
                DEVMODE_COPIES dm = (DEVMODE_COPIES)Marshal.PtrToStructure(job.pDevMode, typeof(DEVMODE_COPIES));
                copies = dm.dmCopies.ToString();
            }
            catch (Exception ex)
            {
                copies = "error:" + ex.Message;
            }
        }

        string submitted;
        try
        {
            var dt = new DateTime(job.Submitted.Year, job.Submitted.Month, job.Submitted.Day,
                job.Submitted.Hour, job.Submitted.Minute, job.Submitted.Second, DateTimeKind.Utc);
            submitted = dt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
        }
        catch
        {
            submitted = "unknown";
        }

        Log(string.Format(
            "JOB printer=\"{0}\" jobId={1} document=\"{2}\" copies={3} pages={4} user=\"{5}\" submitted={6} status=0x{7:X}",
            printerName, job.JobId, job.pDocument ?? "", copies, job.TotalPages,
            job.pUserName ?? "", submitted, job.Status));
    }

    private static void Log(string line)
    {
        string stamped = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " | " + line;
        Console.WriteLine(stamped);
        try
        {
            File.AppendAllText(LogPath, stamped + Environment.NewLine);
        }
        catch
        {
            // Logging must never take down the observer.
        }
    }
}

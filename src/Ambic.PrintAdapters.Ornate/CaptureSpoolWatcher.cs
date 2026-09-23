using System.Diagnostics;
using System.IO;
using Ambic.PrintAdapters.Pdf;
using Ambic.PrintCore.Models;

namespace Ambic.PrintAdapters.Ornate;

public class CaptureSpoolWatcher : IDisposable
{
    private readonly List<string> _watchFolders = [];
    private readonly System.Timers.Timer _scanTimer;
    private readonly PdfOverlayService _overlayService;
    private readonly HashSet<string> _processingFiles = [];
    private readonly SemaphoreSlim _printLock = new(1, 1);
    private bool _isScanning;
    private RouterHubConfig? _currentConfig;

    private static string? _cachedSumatra;
    private static string? _cachedGhostscript;

    public event Action<string>? LogEvent;

    public CaptureSpoolWatcher(PdfOverlayService? overlayService = null)
    {
        _overlayService = overlayService ?? new PdfOverlayService();

        // Standard capture directories
        AddFolder(@"C:\PrintBridgeTest\incoming");
        AddFolder(@"C:\PrintBridge\incoming_355");
        AddFolder(@"C:\PrintBridge\incoming");
        AddFolder(@"C:\PrintBridge\incoming_1007relay");

        _scanTimer = new System.Timers.Timer(1000) { AutoReset = true };
        _scanTimer.Elapsed += (s, e) => ScanFolders();
    }

    public void Start(RouterHubConfig? config = null)
    {
        _currentConfig = config;
        EnsureDirectories();
        _scanTimer.Start();
        Log($"[CAPTURE WATCHER] Started watching {string.Join(", ", _watchFolders.Where(Directory.Exists))}");
    }

    public void Stop()
    {
        _scanTimer.Stop();
    }

    public void AddFolder(string path)
    {
        if (!_watchFolders.Contains(path, StringComparer.OrdinalIgnoreCase))
        {
            _watchFolders.Add(path);
        }
    }

    private void Log(string message) => LogEvent?.Invoke(message);

    private void EnsureDirectories()
    {
        foreach (var folder in _watchFolders)
        {
            try
            {
                if (!Directory.Exists(folder))
                    Directory.CreateDirectory(folder);
            }
            catch { }
        }
    }

    private void ScanFolders()
    {
        if (_isScanning) return;
        _isScanning = true;

        try
        {
            foreach (var folder in _watchFolders)
            {
                if (!Directory.Exists(folder)) continue;

                string[] files;
                try
                {
                    files = Directory.GetFiles(folder, "*.pdf");
                }
                catch
                {
                    continue;
                }

                foreach (var file in files)
                {
                    lock (_processingFiles)
                    {
                        if (_processingFiles.Contains(file)) continue;
                        _processingFiles.Add(file);
                    }

                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            await ProcessIncomingPdfAsync(file, folder);
                        }
                        finally
                        {
                            lock (_processingFiles)
                            {
                                _processingFiles.Remove(file);
                            }
                        }
                    });
                }
            }
        }
        catch (Exception ex)
        {
            Log($"[CAPTURE WATCHER ERROR] {ex.Message}");
        }
        finally
        {
            _isScanning = false;
        }
    }

    private async Task ProcessIncomingPdfAsync(string filePath, string sourceFolder)
    {
        // 1. Wait for file write completion (prevent processing half-written Bullzip files)
        if (!WaitForFileReady(filePath, TimeSpan.FromSeconds(8)))
        {
            Log($"[CAPTURE TIMEOUT] File still locked or changing: {Path.GetFileName(filePath)}");
            return;
        }

        var fileName = Path.GetFileName(filePath);
        Log($"[CAPTURE INCOMING] Picked up captured voucher: '{fileName}' ({new FileInfo(filePath).Length / 1024} KB)");

        try
        {
            // 2. Identify destination based on source folder or file name
            bool isRelay1007 = sourceFolder.Contains("1007", StringComparison.OrdinalIgnoreCase) ||
                               fileName.Contains("1007", StringComparison.OrdinalIgnoreCase);

            string pc2Share = @"\\PC2\PrintBridge\incoming";
            bool pc2Available = false;
            try { pc2Available = Directory.Exists(pc2Share); } catch { }

            if (isRelay1007)
            {
                // Relay Office Copy to PC2
                if (pc2Available)
                {
                    var dest = Path.Combine(pc2Share, $"{DateTime.Now:yyyyMMdd_HHmmss}_{fileName}");
                    File.Copy(filePath, dest, true);
                    Log($"[RELAY SUCCESS] Relayed Office Copy '{fileName}' -> PC2 Share: {dest}");
                }
                else
                {
                    // Local fallback
                    Log($"[RELAY NOTICE] PC2 share unavailable. Attempting local print for '{fileName}'...");
                    PrintPdfSilently(filePath, "HP LaserJet P1007", false);
                }

                ArchiveProcessedFile(filePath, sourceFolder);
                return;
            }

            // 3. Customer Copy (355 Letterhead Duplex)
            string target355Printer = ResolveTarget355Printer();
            string tempMerged = Path.Combine(Path.GetTempPath(), $"merged_{Guid.NewGuid():N}_{fileName}");

            Log($"[OVERLAY PROCESSING] Applying Letterhead Overlay to '{fileName}'...");
            var overlayResult = await _overlayService.ProcessAsync(filePath, tempMerged);

            string fileToPrint = filePath;
            bool duplex = false;

            if (overlayResult.Success && File.Exists(tempMerged))
            {
                fileToPrint = tempMerged;
                duplex = true;
                Log($"[OVERLAY SUCCESS] 2-page duplex voucher composed with official letterhead ({overlayResult.Duration.TotalMilliseconds:0}ms)");
            }
            else
            {
                Log($"[OVERLAY WARNING] Letterhead overlay failed: {overlayResult.ErrorMessage}. Printing original raw voucher as safety fallback.");
            }

            // 4. Print via SumatraPDF silently to physical printer (synchronized to prevent driver collisions)
            await _printLock.WaitAsync();
            bool printed = false;
            try
            {
                printed = PrintPdfSilently(fileToPrint, target355Printer, duplex);
            }
            finally
            {
                _printLock.Release();
            }

            if (printed)
            {
                Log($"[PRINT DISPATCH SUCCESS] Physical print job submitted to '{target355Printer}' (Duplex={duplex})");
                ArchiveProcessedFile(filePath, sourceFolder);
            }
            else
            {
                Log($"[PRINT DISPATCH ERROR] Failed submitting to '{target355Printer}'. File remains in incoming.");
            }

            // Clean up temp
            if (File.Exists(tempMerged))
            {
                try { File.Delete(tempMerged); } catch { }
            }
        }
        catch (Exception ex)
        {
            Log($"[PROCESS EXCEPTION] Error processing '{fileName}': {ex.Message}");
        }
    }

    private string ResolveTarget355Printer()
    {
        if (!string.IsNullOrEmpty(_currentConfig?.DefaultCopy2Printer) && 
            !_currentConfig.DefaultCopy2Printer.Contains("Capture", StringComparison.OrdinalIgnoreCase))
        {
            return _currentConfig.DefaultCopy2Printer;
        }

        // Check standard hardware queues (prefer direct TCP/IP queue over WSD)
        string[] candidates = [
            "HP Laser MFP 330",
            "HPF8EDFC0532A7(HP Laser MFP 330)",
            "HP Laser MFP 355sdnw (05:32:A7)"
        ];

        try
        {
            var installed = Ambic.PrintCore.Spooler.PrinterDiscovery.DiscoverLocalPrinters()
                .Select(p => p.Name)
                .ToList();

            foreach (var c in candidates)
            {
                if (installed.Contains(c, StringComparer.OrdinalIgnoreCase))
                    return c;
            }
        }
        catch { }

        return "HP Laser MFP 330";
    }

    private bool PrintPdfSilently(string pdfPath, string printerName, bool duplex)
    {
        var sumatra = ResolveSumatra();
        if (string.IsNullOrEmpty(sumatra) || !File.Exists(sumatra))
        {
            Log($"[PRINT ERROR] SumatraPDF executable not found! Cannot print silently to '{printerName}'");
            return false;
        }

        try
        {
            var args = duplex
                ? $"-print-to \"{printerName}\" -print-settings \"duplex\" -silent \"{pdfPath}\""
                : $"-print-to \"{printerName}\" -silent \"{pdfPath}\"";

            Log($"[PRINT SPOOLING] Dispatching to '{printerName}' (Duplex={duplex}) via SumatraPDF...");

            var psi = new ProcessStartInfo
            {
                FileName = sumatra,
                Arguments = args,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };

            using var p = Process.Start(psi);
            if (p != null)
            {
                bool exited = p.WaitForExit(30000);
                if (!exited)
                {
                    try { p.Kill(true); } catch { }
                    Log($"[PRINT TIMEOUT] SumatraPDF timed out after 30s while spooling to '{printerName}'");
                    return false;
                }
                return p.ExitCode == 0;
            }
            return false;
        }
        catch (Exception ex)
        {
            Log($"[PRINT ERROR] Sumatra invocation error: {ex.Message}");
            return false;
        }
    }

    private void ArchiveProcessedFile(string filePath, string sourceFolder)
    {
        try
        {
            string doneDir = Path.Combine(Path.GetDirectoryName(sourceFolder) ?? @"C:\PrintBridgeTest", "done");
            Directory.CreateDirectory(doneDir);
            string dest = Path.Combine(doneDir, $"{DateTime.Now:yyyyMMdd_HHmmss}_{Path.GetFileName(filePath)}");
            File.Move(filePath, dest, true);
        }
        catch { }
    }

    private static bool WaitForFileReady(string path, TimeSpan timeout)
    {
        var sw = Stopwatch.StartNew();
        long lastSize = -1;

        while (sw.Elapsed < timeout)
        {
            if (!File.Exists(path)) return false;

            try
            {
                var info = new FileInfo(path);
                long curSize = info.Length;

                if (curSize > 0 && curSize == lastSize)
                {
                    // Check if file is readable
                    using (var fs = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                    {
                        if (fs.Length > 0) return true;
                    }
                }
                lastSize = curSize;
            }
            catch { }

            Thread.Sleep(500);
        }

        return false;
    }

    public static string ResolveSumatra()
    {
        if (_cachedSumatra != null && File.Exists(_cachedSumatra)) return _cachedSumatra;

        string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string progFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);

        string[] candidates = [
            Path.Combine(localApp, @"SumatraPDF\SumatraPDF.exe"),
            Path.Combine(progFiles, @"SumatraPDF\SumatraPDF.exe"),
            @"C:\Program Files\SumatraPDF\SumatraPDF.exe"
        ];

        foreach (var c in candidates)
        {
            if (File.Exists(c))
            {
                _cachedSumatra = c;
                return c;
            }
        }

        return @"C:\Program Files\SumatraPDF\SumatraPDF.exe";
    }

    public void Dispose()
    {
        _scanTimer.Dispose();
    }
}

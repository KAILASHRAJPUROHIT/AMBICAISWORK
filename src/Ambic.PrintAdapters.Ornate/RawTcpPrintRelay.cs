using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;

namespace Ambic.PrintAdapters.Ornate;

public class RawTcpPrintRelay : IDisposable
{
    private readonly int _port;
    private readonly string _targetIncomingDir;
    private TcpListener? _listener;
    private CancellationTokenSource? _cts;
    private static string? _cachedGsPath;

    public event Action<string>? LogEvent;

    public RawTcpPrintRelay(int port = 9101, string targetIncomingDir = @"C:\PrintBridgeTest\incoming")
    {
        _port = port;
        _targetIncomingDir = targetIncomingDir;
    }

    private void Log(string message) => LogEvent?.Invoke(message);

    public void Start()
    {
        if (_listener != null) return;

        try
        {
            _cts = new CancellationTokenSource();
            _listener = new TcpListener(IPAddress.Loopback, _port);
            _listener.Start();
            Log($"[TCP RELAY] RAW TCP Spooler listening on 127.0.0.1:{_port} for 'P1007 (via PC2)'");

            _ = Task.Run(() => ListenLoopAsync(_cts.Token));
        }
        catch (Exception ex)
        {
            Log($"[TCP RELAY ERROR] Could not bind to 127.0.0.1:{_port}: {ex.Message}");
        }
    }

    private async Task ListenLoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested && _listener != null)
        {
            try
            {
                var client = await _listener.AcceptTcpClientAsync(ct);
                _ = Task.Run(() => HandleClientAsync(client, ct), ct);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                Log($"[TCP RELAY ACCEPT ERROR] {ex.Message}");
            }
        }
    }

    private async Task HandleClientAsync(TcpClient client, CancellationToken ct)
    {
        using (client)
        {
            string tempPs = Path.Combine(Path.GetTempPath(), $"p1007_{Guid.NewGuid():N}.ps");
            string tempPdf = Path.Combine(Path.GetTempPath(), $"p1007_{Guid.NewGuid():N}.pdf");

            try
            {
                Log("[TCP RELAY INCOMING] Client connected from Windows Spooler on port 9101");
                using (var stream = client.GetStream())
                using (var fileStream = File.Create(tempPs))
                {
                    byte[] buffer = new byte[65536];
                    int bytesRead;
                    long totalBytes = 0;

                    while ((bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length, ct)) > 0)
                    {
                        await fileStream.WriteAsync(buffer, 0, bytesRead, ct);
                        totalBytes += bytesRead;
                    }

                    await fileStream.FlushAsync(ct);
                    Log($"[TCP RELAY STREAM COMPLETE] Received {totalBytes} bytes PostScript from Spooler");

                    if (totalBytes == 0) return;
                }

                // Convert PostScript to PDF via Ghostscript
                string gsExe = ResolveGhostscript();
                if (!File.Exists(gsExe))
                {
                    Log($"[TCP RELAY ERROR] Ghostscript not found at '{gsExe}'! Cannot convert PS to PDF.");
                    return;
                }

                var psi = new ProcessStartInfo
                {
                    FileName = gsExe,
                    Arguments = $"-dNOPAUSE -dBATCH -dSAFER -sDEVICE=pdfwrite -o\"{tempPdf}\" \"{tempPs}\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardError = true,
                    RedirectStandardOutput = true
                };

                using (var proc = Process.Start(psi))
                {
                    if (proc != null)
                    {
                        var outTask = proc.StandardOutput.ReadToEndAsync(ct);
                        var errTask = proc.StandardError.ReadToEndAsync(ct);
                        await proc.WaitForExitAsync(ct);
                        var gsOut = await outTask;
                        var gsErr = await errTask;

                        if (proc.ExitCode == 0 && File.Exists(tempPdf) && new FileInfo(tempPdf).Length > 0)
                        {
                            Log($"[TCP RELAY PS->PDF SUCCESS] Converted to PDF ({new FileInfo(tempPdf).Length / 1024} KB)");

                            // Deliver directly to PC2 incoming or local incoming folder
                            string pc2Share = @"\\PC2\PrintBridge\incoming";
                            string targetFile;

                            if (Directory.Exists(pc2Share))
                            {
                                targetFile = Path.Combine(pc2Share, $"1007relay_{DateTime.Now:yyyyMMdd_HHmmss}.pdf");
                                File.Copy(tempPdf, targetFile, true);
                                Log($"[TCP RELAY DISPATCHED] Forwarded P1007 Office Copy directly to PC2: {targetFile}");
                            }
                            else
                            {
                                Directory.CreateDirectory(_targetIncomingDir);
                                targetFile = Path.Combine(_targetIncomingDir, $"1007relay_{DateTime.Now:yyyyMMdd_HHmmss}.pdf");
                                File.Copy(tempPdf, targetFile, true);
                                Log($"[TCP RELAY SAVED] PC2 offline; saved to local capture queue: {targetFile}");
                            }
                        }
                        else
                        {
                            var saveDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
                            var debugPs = Path.Combine(saveDir, "failed_spool.ps");
                            try { File.Copy(tempPs, debugPs, true); } catch { }
                            Log($"[TCP RELAY GS ERROR] Ghostscript failed (Exit {proc.ExitCode}). Out: {gsOut.Trim()} | Err: {gsErr.Trim()}");
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log($"[TCP RELAY CLIENT ERROR] {ex.Message}");
            }
            finally
            {
                try { if (File.Exists(tempPs)) File.Delete(tempPs); } catch { }
                try { if (File.Exists(tempPdf)) File.Delete(tempPdf); } catch { }
            }
        }
    }

    public static string ResolveGhostscript()
    {
        if (_cachedGsPath != null && File.Exists(_cachedGsPath)) return _cachedGsPath;

        string progFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string gsBase = Path.Combine(progFiles, "gs");

        if (Directory.Exists(gsBase))
        {
            foreach (var dir in Directory.GetDirectories(gsBase))
            {
                var exe = Path.Combine(dir, "bin", "gswin64c.exe");
                if (File.Exists(exe))
                {
                    _cachedGsPath = exe;
                    return exe;
                }
            }
        }

        return @"C:\Program Files\gs\gs10.07.1\bin\gswin64c.exe";
    }

    public void Stop()
    {
        try
        {
            _cts?.Cancel();
            _listener?.Stop();
            _listener = null;
        }
        catch { }
    }

    public void Dispose()
    {
        Stop();
        _cts?.Dispose();
    }
}

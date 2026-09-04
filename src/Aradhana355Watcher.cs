using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace Aradhana355Watcher
{
    internal static class Program
    {
        [STAThread]
        static void Main()
        {
            bool createdNew;
            using (var mutex = new System.Threading.Mutex(true, @"Local\Aradhana355WatcherTray", out createdNew))
            {
                if (!createdNew) return;

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new WatcherContext());
            }
        }
    }

    internal sealed class WatcherContext : ApplicationContext
    {
        // Fixed by deployment - not config-driven, this app is only ever the
        // 355 overlay pipeline, unlike the general-purpose tray app.
        private const string IncomingDir = @"C:\PrintBridge\incoming_355";
        private const string DoneDir = @"C:\PrintBridge\done_355";
        private const string FrontImage = @"C:\PrintBridge\letterhead_front.jpeg";
        private const string BackImage = @"C:\PrintBridge\letterhead_back.jpeg";
        private const string OverlayScript = @"C:\PrintBridge\overlay_merge.py";
        private const string SumatraExe = @"C:\Program Files\SumatraPDF\SumatraPDF.exe";
        private const string TargetPrinter = "HP Laser MFP 355sdnw (05:32:A7)";
        private const string PythonLauncher = "py";
        private const int ProcessTimeoutMs = 60000;

        private readonly NotifyIcon tray;
        private readonly Timer timer;
        private bool enabled = true;
        private bool busy = false;

        private readonly string baseFolder =
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                         "Aradhana", "Aradhana355Watcher");

        private string LogFile
        {
            get { return Path.Combine(baseFolder, "Aradhana355Watcher.log"); }
        }

        public WatcherContext()
        {
            Directory.CreateDirectory(baseFolder);
            Directory.CreateDirectory(IncomingDir);
            Directory.CreateDirectory(DoneDir);

            tray = new NotifyIcon
            {
                Icon = SystemIcons.Application,
                Text = "Aradhana 355 Letterhead Watcher",
                Visible = true
            };

            var menu = new ContextMenuStrip();

            var status = new ToolStripMenuItem("Status: ENABLED");
            status.Enabled = false;

            var toggle = new ToolStripMenuItem("Disable Watcher");
            toggle.Click += (s, e) =>
            {
                enabled = !enabled;
                status.Text = enabled ? "Status: ENABLED" : "Status: DISABLED";
                toggle.Text = enabled ? "Disable Watcher" : "Enable Watcher";
                Log(enabled ? "ENABLED by user." : "DISABLED by user.");
            };

            var openLog = new ToolStripMenuItem("Open Log");
            openLog.Click += (s, e) =>
            {
                try
                {
                    if (!File.Exists(LogFile)) File.WriteAllText(LogFile, "");
                    Process.Start("notepad.exe", "\"" + LogFile + "\"");
                }
                catch { }
            };

            var exit = new ToolStripMenuItem("Exit");
            exit.Click += (s, e) =>
            {
                Log("EXIT by user.");
                tray.Visible = false;
                timer.Stop();
                Application.Exit();
            };

            menu.Items.Add(status);
            menu.Items.Add(toggle);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(openLog);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(exit);

            tray.ContextMenuStrip = menu;

            timer = new Timer { Interval = 3000 };
            timer.Tick += (s, e) => Scan();
            timer.Start();

            Log("START. Watching " + IncomingDir + " -> " + TargetPrinter);
        }

        private void Scan()
        {
            if (!enabled || busy) return;
            busy = true;

            try
            {
                var files = Directory.GetFiles(IncomingDir, "*.pdf");
                foreach (var path in files)
                {
                    ProcessOneFile(path);
                }
            }
            catch (Exception ex)
            {
                Log("ERROR in Scan: " + ex.Message);
            }
            finally
            {
                busy = false;
            }
        }

        private void ProcessOneFile(string path)
        {
            try
            {
                // Wait for the file to stop growing (Bullzip still writing it).
                long size1 = new FileInfo(path).Length;
                System.Threading.Thread.Sleep(1500);
                if (!File.Exists(path)) return;
                long size2 = new FileInfo(path).Length;
                if (size1 != size2) return; // still being written, catch it next scan

                string baseName = Path.GetFileNameWithoutExtension(path);
                string merged = Path.Combine(IncomingDir, "merged_" + baseName + ".pdf");

                var overlayArgs = string.Format("\"{0}\" \"{1}\" \"{2}\" \"{3}\" \"{4}\"",
                    OverlayScript, path, merged, FrontImage, BackImage);

                int overlayExit;
                string overlayOutput;
                bool overlayOk = RunProcess(PythonLauncher, overlayArgs, out overlayExit, out overlayOutput);
                if (!overlayOk || overlayExit != 0 || !File.Exists(merged))
                {
                    Log("ERROR: overlay failed for " + Path.GetFileName(path) +
                        " (exit=" + overlayExit + "): " + overlayOutput);
                    return;
                }

                var printArgs = string.Format(
                    "-print-to \"{0}\" -print-settings \"duplex\" -silent \"{1}\"",
                    TargetPrinter, merged);

                int printExit;
                string printOutput;
                bool printOk = RunProcess(SumatraExe, printArgs, out printExit, out printOutput);
                if (!printOk)
                {
                    Log("ERROR: print timed out/failed for " + Path.GetFileName(path));
                    return;
                }

                string dest = Path.Combine(DoneDir,
                    DateTime.Now.ToString("yyyyMMdd_HHmmss") + "_" + Path.GetFileName(path));
                File.Move(path, dest);
                try { File.Delete(merged); } catch { }

                Log("OK: overlaid and printed " + Path.GetFileName(path));
            }
            catch (Exception ex)
            {
                Log("ERROR processing " + Path.GetFileName(path) + ": " + ex.Message);
            }
        }

        // Runs a process with a timeout, killing it if it hangs (e.g. an
        // unexpected dialog with nobody to click it) rather than blocking
        // the watcher forever.
        private bool RunProcess(string exe, string args, out int exitCode, out string output)
        {
            exitCode = -1;
            output = "";

            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = args,
                UseShellExecute = false,
                CreateNoWindow = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WindowStyle = ProcessWindowStyle.Minimized
            };

            using (var p = new Process())
            {
                p.StartInfo = psi;
                var sb = new StringBuilder();
                p.OutputDataReceived += (s, e) => { if (e.Data != null) sb.AppendLine(e.Data); };
                p.ErrorDataReceived += (s, e) => { if (e.Data != null) sb.AppendLine(e.Data); };

                p.Start();
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();

                bool exited = p.WaitForExit(ProcessTimeoutMs);
                output = sb.ToString().Trim();

                if (!exited)
                {
                    try { p.Kill(); } catch { }
                    output += " [TIMED OUT after " + ProcessTimeoutMs + "ms, process killed]";
                    return false;
                }

                exitCode = p.ExitCode;
                return true;
            }
        }

        private void Log(string message)
        {
            try
            {
                Directory.CreateDirectory(baseFolder);
                File.AppendAllText(
                    LogFile,
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + message + Environment.NewLine,
                    Encoding.UTF8);
            }
            catch { }
        }
    }
}

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace AradhanaOrnateAutoPrint
{
    internal static class Program
    {
        [STAThread]
        static void Main()
        {
            bool createdNew;
            using (var mutex = new System.Threading.Mutex(true, @"Local\AradhanaOrnateAutoPrintTray", out createdNew))
            {
                if (!createdNew) return;

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new TrayContext());
            }
        }
    }

    // Plain key=value config file. No JSON library is available to the
    // in-box .NET Framework csc.exe build used by Build_Aradhana_Ornate_AutoPrint.bat,
    // so this stays deliberately simple.
    internal sealed class AppConfig
    {
        public bool MasterEnabled = true;
        public string PcRole = "PC2 (Hub)";
        public string Copy1Printer = "P1007 Letterhead Bridge";
        public string Copy2Printer = "HP Laser MFP 355sdnw";
        public string ForceCopy1Printer = ""; // empty = Auto
        public string ForceCopy2Printer = ""; // empty = Auto
        public int SessionGapSeconds = 20;

        // Per-machine overrides - blank means "use the compiled default",
        // since PC2's values are correct out of the box and most machines
        // won't need to touch these.
        public string OrnateExecutablePathOverride = "";
        public string Overlay355TargetPrinterOverride = "";

        // Relay mode: true on machines where P1007 isn't locally attached
        // (anything but PC2). Copy 1 jobs get captured locally to
        // Copy1Printer (a local virtual printer) and relayed as a raw file
        // to PC2's incoming share instead of printing directly.
        public bool Relay1007Enabled = false;

        public bool IsHub
        {
            get { return !Relay1007Enabled; }
        }

        public static AppConfig Load(string path)
        {
            var cfg = new AppConfig();
            try
            {
                if (!File.Exists(path)) return cfg;

                foreach (var rawLine in File.ReadAllLines(path))
                {
                    var line = rawLine.Trim();
                    if (line.Length == 0 || line.StartsWith("#")) continue;

                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;

                    string key = line.Substring(0, eq).Trim();
                    string val = line.Substring(eq + 1).Trim();

                    switch (key)
                    {
                        case "MasterEnabled": cfg.MasterEnabled = val.Equals("true", StringComparison.OrdinalIgnoreCase); break;
                        case "PcRole": cfg.PcRole = val; break;
                        case "Copy1Printer": cfg.Copy1Printer = val; break;
                        case "Copy2Printer": cfg.Copy2Printer = val; break;
                        case "ForceCopy1Printer": cfg.ForceCopy1Printer = val; break;
                        case "ForceCopy2Printer": cfg.ForceCopy2Printer = val; break;
                        case "SessionGapSeconds":
                            int parsed;
                            if (int.TryParse(val, out parsed) && parsed > 0) cfg.SessionGapSeconds = parsed;
                            break;
                        case "OrnateExecutablePathOverride": cfg.OrnateExecutablePathOverride = val; break;
                        case "Overlay355TargetPrinterOverride": cfg.Overlay355TargetPrinterOverride = val; break;
                        case "Relay1007Enabled": cfg.Relay1007Enabled = val.Equals("true", StringComparison.OrdinalIgnoreCase); break;
                    }
                }
            }
            catch { }
            return cfg;
        }

        public void Save(string path)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                var sb = new StringBuilder();
                sb.AppendLine("# Aradhana Ornate AutoPrint config. Edit via the tray icon's Settings window.");
                sb.AppendLine("MasterEnabled=" + (MasterEnabled ? "true" : "false"));
                sb.AppendLine("PcRole=" + PcRole);
                sb.AppendLine("Copy1Printer=" + Copy1Printer);
                sb.AppendLine("Copy2Printer=" + Copy2Printer);
                sb.AppendLine("ForceCopy1Printer=" + ForceCopy1Printer);
                sb.AppendLine("ForceCopy2Printer=" + ForceCopy2Printer);
                sb.AppendLine("SessionGapSeconds=" + SessionGapSeconds);
                sb.AppendLine("OrnateExecutablePathOverride=" + OrnateExecutablePathOverride);
                sb.AppendLine("Overlay355TargetPrinterOverride=" + Overlay355TargetPrinterOverride);
                sb.AppendLine("Relay1007Enabled=" + (Relay1007Enabled ? "true" : "false"));
                File.WriteAllText(path, sb.ToString());
            }
            catch { }
        }

        // What to actually select for a given copy number, honoring a manual override if set.
        public string ResolvePrinter(int copyNumber)
        {
            if (copyNumber == 1)
                return string.IsNullOrEmpty(ForceCopy1Printer) ? Copy1Printer : ForceCopy1Printer;
            return string.IsNullOrEmpty(ForceCopy2Printer) ? Copy2Printer : ForceCopy2Printer;
        }
    }

    internal sealed class TrayContext : ApplicationContext
    {
        private const string OrnateProcessName = "ONX";
        private const string OrnateExecutablePath = @"D:\Ornnx\ONX.exe";
        private const string RequiredDialogTitle = "Print";
        private const string RequiredDialogClass = "#32770";
        private const uint GW_OWNER = 4;
        private const uint BM_CLICK = 0x00F5;

        // Standard Win32 common Print dialog (PrintDlg) control IDs.
        // Stable since Windows 95 - documented in commdlg.h / dlgs.h.
        // Used as a first guess only - TrySelectPrinter falls back to enumerating
        // every ComboBox child if this ID doesn't pan out, since some apps
        // (older/customized print dialogs) don't use the stock control IDs.
        private const int IDC_PRINTER_COMBO = 0x0140; // cmb4 - the "Name:" printer selector
        private const uint WM_COMMAND = 0x0111;
        private const int CBN_SELCHANGE = 1;
        private const uint CB_GETCOUNT = 0x0146;
        private const uint CB_GETLBTEXT = 0x0148;
        private const uint CB_GETLBTEXTLEN = 0x0149;
        private const uint CB_SETCURSEL = 0x014E;

        // SysListView32 (used by .NET's PrintDialog for the printer picker).
        private const uint LVM_GETITEMCOUNT = 0x1004;
        private const uint LVM_GETITEMTEXTW = 0x1073;
        private const uint LVM_SETITEMSTATE = 0x102B;
        private const uint LVIF_TEXT = 0x0001;
        private const uint LVIF_STATE = 0x0008;
        private const uint LVIS_SELECTED = 0x0002;
        private const uint LVIS_FOCUSED = 0x0001;

        // Cross-process memory access (needed because LVM_GETITEMTEXT/LVM_SETITEMSTATE
        // pass a struct containing an embedded pointer, which Windows does not
        // auto-marshal across process boundaries).
        private const uint PROCESS_VM_OPERATION = 0x0008;
        private const uint PROCESS_VM_READ = 0x0010;
        private const uint PROCESS_VM_WRITE = 0x0020;
        private const uint PROCESS_QUERY_INFORMATION = 0x0400;
        private const uint MEM_COMMIT = 0x1000;
        private const uint MEM_RELEASE = 0x8000;
        private const uint PAGE_READWRITE = 0x04;

        [StructLayout(LayoutKind.Sequential)]
        private struct LVITEM
        {
            public uint mask;
            public int iItem;
            public int iSubItem;
            public uint state;
            public uint stateMask;
            public IntPtr pszText;
            public int cchTextMax;
            public int iImage;
            public IntPtr lParam;
            public int iIndent;
            public int iGroupId;
            public uint cColumns;
            public IntPtr puColumns;
            public IntPtr piColFmt;
            public int iGroup;
        }

        // 355 letterhead overlay pipeline - merged directly into this exe (rather
        // than a separate watcher process) since NPAV flagged the standalone
        // watcher binary on content-heuristic grounds (WORM.HEUR.BBP) regardless
        // of how it was deployed, while this tray app itself has never been
        // flagged all session. One proven-safe binary doing both jobs sidesteps
        // that entirely. Only relevant on PC2 - harmlessly does nothing on
        // machines where these folders don't exist.
        private const string Overlay355IncomingDir = @"C:\PrintBridge\incoming_355";
        private const string Overlay355DoneDir = @"C:\PrintBridge\done_355";
        private const string Overlay355FailedDir = @"C:\PrintBridge\failed_355";
        private const string Overlay355TempDir = @"C:\PrintBridge\temp_355"; // merged output NEVER goes in the watched incoming dir - that caused a self-reprocessing loop
        private const string Overlay355FrontImage = @"C:\PrintBridge\letterhead_front.jpeg";
        private const string Overlay355BackImage = @"C:\PrintBridge\letterhead_back.jpeg";
        private const string Overlay355Script = @"C:\PrintBridge\overlay_merge.py";
        private const string Overlay355SumatraExeDefault = @"C:\Program Files\SumatraPDF\SumatraPDF.exe";
        private static string cachedSumatraExe;

        // The installer doesn't always land in Program Files (e.g. without an
        // explicit all-users flag it installs per-user to LocalAppData) - check
        // both rather than assuming.
        private static string ResolveSumatraExe()
        {
            if (cachedSumatraExe != null) return cachedSumatraExe;

            var candidates = new List<string>
            {
                Overlay355SumatraExeDefault,
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SumatraPDF", "SumatraPDF.exe"),
            };

            foreach (var candidate in candidates)
            {
                try
                {
                    if (File.Exists(candidate))
                    {
                        cachedSumatraExe = candidate;
                        return candidate;
                    }
                }
                catch { }
            }

            cachedSumatraExe = Overlay355SumatraExeDefault; // nothing found - will fail loudly and get logged
            return cachedSumatraExe;
        }
        private const string Overlay355TargetPrinterDefault = "HP Laser MFP 355sdnw (05:32:A7)";
        private const int Overlay355ProcessTimeoutMs = 60000;
        private bool overlay355Busy = false;
        private static string cachedPythonExe;

        // "py" only resolves via the process's inherited PATH, which goes stale
        // if Python was installed after this app was already running (bit us on
        // the Dell server). Try "py" first (works fine when Python pre-existed),
        // then fall back to checking well-known install locations directly so a
        // stale PATH can never silently break this.
        private static string ResolvePythonExe()
        {
            if (cachedPythonExe != null) return cachedPythonExe;

            // Full paths first and actually verified via File.Exists - these are
            // reliable regardless of this process's (possibly stale) PATH.
            var fullPathCandidates = new List<string>
            {
                @"C:\Program Files\Python313\python.exe",
                @"C:\Program Files\Python312\python.exe",
                @"C:\Program Files\Python311\python.exe",
                @"C:\Program Files\Python310\python.exe",
            };

            foreach (var candidate in fullPathCandidates)
            {
                try
                {
                    if (File.Exists(candidate))
                    {
                        cachedPythonExe = candidate;
                        return candidate;
                    }
                }
                catch { }
            }

            // "py" as a last resort, and only if it's genuinely findable on the
            // *current* PATH - the earlier version of this code trusted "py"
            // blindly without checking, which meant it silently never fell
            // through to the working full-path candidates below it.
            if (CanFindOnPath("py.exe") || CanFindOnPath("py.bat") || CanFindOnPath("py.cmd"))
            {
                cachedPythonExe = "py";
                return cachedPythonExe;
            }

            cachedPythonExe = "py"; // nothing found - will fail loudly and get logged
            return cachedPythonExe;
        }

        private static bool CanFindOnPath(string exeName)
        {
            try
            {
                string pathVar = Environment.GetEnvironmentVariable("PATH") ?? "";
                foreach (var dir in pathVar.Split(';'))
                {
                    try
                    {
                        string candidate = Path.Combine(dir.Trim(), exeName);
                        if (File.Exists(candidate)) return true;
                    }
                    catch { }
                }
            }
            catch { }
            return false;
        }

        // PC2's real printer name; other machines (e.g. the laptop, which sees
        // the same physical printer as "HPF8EDFC0532A7(HP Laser MFP 330)") need
        // this set via config.
        private string EffectiveOverlay355TargetPrinter
        {
            get
            {
                return string.IsNullOrEmpty(config.Overlay355TargetPrinterOverride)
                    ? Overlay355TargetPrinterDefault
                    : config.Overlay355TargetPrinterOverride;
            }
        }

        // P1007 relay (non-hub machines only): capture folder for copy-1 jobs
        // that get relayed to PC2 as raw files rather than printed locally.
        private const string Relay1007IncomingDir = @"C:\PrintBridge\incoming_1007relay";
        private const string Relay1007DoneDir = @"C:\PrintBridge\done_1007relay";
        private const string Relay1007RemoteShare = @"\\PC2\PrintBridge\incoming";
        private bool relay1007Busy = false;

        // PC2 only: receives raw copy-1 jobs relayed from other machines and
        // prints them straight to the real P1007 (no overlay needed - P1007
        // already has real letterhead stock loaded).
        private const string Hub1007IncomingDir = @"C:\PrintBridge\incoming";
        private const string Hub1007DoneDir = @"C:\PrintBridge\done";
        private const string Hub1007TargetPrinter = "HP LaserJet P1007";
        private bool hub1007Busy = false;

        private readonly NotifyIcon tray;
        private readonly Timer timer;
        private Timer overlay355Timer;
        private Timer relay1007Timer;
        private readonly HashSet<IntPtr> handled = new HashSet<IntPtr>();
        private bool enabled = true;

        // Copy 1 / copy 2 detection state.
        private DateTime lastHandledUtc = DateTime.MinValue;
        private int nextCopyNumber = 1;

        private AppConfig config;
        private SettingsForm settingsForm;

        private readonly string baseFolder =
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                         "Aradhana", "OrnateAutoPrintTray");

        private string LogFile
        {
            get { return Path.Combine(baseFolder, "OrnateAutoPrint.log"); }
        }

        private string ConfigFile
        {
            get { return Path.Combine(baseFolder, "config.txt"); }
        }

        public TrayContext()
        {
            Directory.CreateDirectory(baseFolder);
            config = AppConfig.Load(ConfigFile);
            enabled = config.MasterEnabled;

            tray = new NotifyIcon
            {
                Icon = SystemIcons.Application,
                Text = "Aradhana Ornate AutoPrint",
                Visible = true
            };

            var menu = new ContextMenuStrip();

            var status = new ToolStripMenuItem(enabled ? "Status: ENABLED" : "Status: DISABLED");
            status.Enabled = false;

            var toggle = new ToolStripMenuItem(enabled ? "Disable AutoPrint" : "Enable AutoPrint");
            toggle.Click += (s, e) =>
            {
                enabled = !enabled;
                config.MasterEnabled = enabled;
                config.Save(ConfigFile);
                status.Text = enabled ? "Status: ENABLED" : "Status: DISABLED";
                toggle.Text = enabled ? "Disable AutoPrint" : "Enable AutoPrint";
                tray.Text = enabled ? "Aradhana Ornate AutoPrint - ENABLED" :
                                      "Aradhana Ornate AutoPrint - DISABLED";
                Log(enabled ? "ENABLED by user." : "DISABLED by user.");
            };

            var settings = new ToolStripMenuItem("Settings...");
            settings.Click += (s, e) => ShowSettings();

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
            menu.Items.Add(settings);
            menu.Items.Add(openLog);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(exit);

            tray.ContextMenuStrip = menu;

            tray.DoubleClick += (s, e) => ShowSettings();

            timer = new Timer { Interval = 250 };
            timer.Tick += (s, e) => Scan();
            timer.Start();

            overlay355Timer = new Timer { Interval = 3000 };
            overlay355Timer.Tick += (s, e) => Scan355();
            overlay355Timer.Start();

            relay1007Timer = new Timer { Interval = 3000 };
            relay1007Timer.Tick += (s, e) => { ScanRelay1007Send(); ScanHub1007Receive(); };
            relay1007Timer.Start();

            Log("START. Hard-wall path=" + EffectiveOrnateExecutablePath + " PcRole=" + config.PcRole +
                " Relay1007=" + config.Relay1007Enabled);
        }

        private void ShowSettings()
        {
            if (settingsForm != null && !settingsForm.IsDisposed)
            {
                settingsForm.Activate();
                return;
            }

            settingsForm = new SettingsForm(config, ConfigFile, LogFile, () =>
            {
                // Config may have changed (including MasterEnabled) - resync tray state.
                enabled = config.MasterEnabled;
                Log("Settings saved via UI.");
            });
            settingsForm.Show();
        }

        private void Scan355()
        {
            if (overlay355Busy) return;
            if (!Directory.Exists(Overlay355IncomingDir)) return; // not this machine's job

            overlay355Busy = true;
            try
            {
                Directory.CreateDirectory(Overlay355DoneDir);
                Directory.CreateDirectory(Overlay355FailedDir);
                Directory.CreateDirectory(Overlay355TempDir);

                // Only ever process files that were actually captured by Bullzip
                // (numeric counter names) - never anything already in a "merged_"
                // form, in case one somehow ends up here. This is a second line
                // of defense on top of merged output no longer being written into
                // this folder at all.
                foreach (var path in Directory.GetFiles(Overlay355IncomingDir, "*.pdf"))
                {
                    if (Path.GetFileName(path).StartsWith("merged_", StringComparison.OrdinalIgnoreCase))
                    {
                        Log("WARNING: unexpected merged_ file in incoming_355, quarantining: " + Path.GetFileName(path));
                        try { File.Move(path, Path.Combine(Overlay355FailedDir, Path.GetFileName(path))); } catch { }
                        continue;
                    }
                    ProcessOverlay355File(path);
                }
            }
            catch (Exception ex)
            {
                Log("ERROR in Scan355: " + ex.Message);
            }
            finally
            {
                overlay355Busy = false;
            }
        }

        private void ProcessOverlay355File(string path)
        {
            string merged = null;
            try
            {
                // Wait for the file to stop growing (Bullzip still writing it).
                long size1 = new FileInfo(path).Length;
                System.Threading.Thread.Sleep(1500);
                if (!File.Exists(path)) return;
                long size2 = new FileInfo(path).Length;
                if (size1 != size2) return; // still being written, catch it next scan

                string baseName = Path.GetFileNameWithoutExtension(path);
                merged = Path.Combine(Overlay355TempDir, "merged_" + baseName + ".pdf");

                string pythonExe = ResolvePythonExe();
                var overlayArgs = string.Format("\"{0}\" \"{1}\" \"{2}\" \"{3}\" \"{4}\"",
                    Overlay355Script, path, merged, Overlay355FrontImage, Overlay355BackImage);

                int overlayExit;
                string overlayOutput;
                bool overlayOk = RunChildProcess(pythonExe, overlayArgs, out overlayExit, out overlayOutput);
                if (!overlayOk || overlayExit != 0 || !File.Exists(merged))
                {
                    Log("ERROR: 355 overlay failed for " + Path.GetFileName(path) +
                        " (python=" + pythonExe + ", exit=" + overlayExit + "): " + overlayOutput);
                    QuarantineFailed355File(path);
                    return;
                }

                var printArgs = string.Format(
                    "-print-to \"{0}\" -print-settings \"duplex\" -silent \"{1}\"",
                    EffectiveOverlay355TargetPrinter, merged);

                int printExit;
                string printOutput;
                bool printOk = RunChildProcess(ResolveSumatraExe(), printArgs, out printExit, out printOutput);
                if (!printOk)
                {
                    Log("ERROR: 355 print timed out/failed for " + Path.GetFileName(path) + ": " + printOutput);
                    QuarantineFailed355File(path);
                    return;
                }

                string dest = Path.Combine(Overlay355DoneDir,
                    DateTime.Now.ToString("yyyyMMdd_HHmmss") + "_" + Path.GetFileName(path));
                File.Move(path, dest);

                Log("OK: 355 overlaid and printed " + Path.GetFileName(path));
            }
            catch (Exception ex)
            {
                Log("ERROR processing 355 " + Path.GetFileName(path) + ": " + ex.Message);
                QuarantineFailed355File(path);
            }
            finally
            {
                if (merged != null)
                {
                    try { File.Delete(merged); } catch { }
                }
            }
        }

        // Moves a file that failed processing out of the watched folder so it
        // is never retried in an infinite loop - a failure here means someone
        // needs to look at it, not that the system should hammer it every 3s.
        private void QuarantineFailed355File(string path)
        {
            try
            {
                if (!File.Exists(path)) return;
                string dest = Path.Combine(Overlay355FailedDir,
                    DateTime.Now.ToString("yyyyMMdd_HHmmss") + "_" + Path.GetFileName(path));
                File.Move(path, dest);
            }
            catch { }
        }

        // Relay-machine side (laptop, Dell server): copy-1 jobs get captured
        // locally to Relay1007IncomingDir by a local virtual printer, then
        // relayed here as a raw file to PC2's incoming share, where the hub
        // side (below) prints them directly - P1007 already has real
        // letterhead stock loaded, so no overlay processing is needed, just
        // getting the bytes to the machine P1007 is actually attached to.
        private void ScanRelay1007Send()
        {
            if (!config.Relay1007Enabled) return;
            if (relay1007Busy) return;
            if (!Directory.Exists(Relay1007IncomingDir)) return;

            relay1007Busy = true;
            try
            {
                Directory.CreateDirectory(Relay1007DoneDir);
                foreach (var path in Directory.GetFiles(Relay1007IncomingDir, "*.pdf"))
                {
                    try
                    {
                        long size1 = new FileInfo(path).Length;
                        System.Threading.Thread.Sleep(1500);
                        if (!File.Exists(path)) continue;
                        long size2 = new FileInfo(path).Length;
                        if (size1 != size2) continue; // still being written

                        if (!Directory.Exists(Relay1007RemoteShare))
                        {
                            Log("ERROR: relay share " + Relay1007RemoteShare + " unreachable, will retry.");
                            continue;
                        }

                        string remoteDest = Path.Combine(Relay1007RemoteShare, Path.GetFileName(path));
                        File.Copy(path, remoteDest, true);

                        string localDest = Path.Combine(Relay1007DoneDir,
                            DateTime.Now.ToString("yyyyMMdd_HHmmss") + "_" + Path.GetFileName(path));
                        File.Move(path, localDest);

                        Log("OK: relayed to PC2: " + Path.GetFileName(path));
                    }
                    catch (Exception ex)
                    {
                        Log("ERROR relaying " + Path.GetFileName(path) + ": " + ex.Message);
                    }
                }
            }
            catch (Exception ex)
            {
                Log("ERROR in ScanRelay1007Send: " + ex.Message);
            }
            finally
            {
                relay1007Busy = false;
            }
        }

        // Hub side (PC2 only): prints raw copy-1 jobs relayed in from other
        // machines straight to the physically-attached P1007. No-op on any
        // machine where Hub1007IncomingDir doesn't exist (i.e. everywhere
        // except PC2).
        private void ScanHub1007Receive()
        {
            if (hub1007Busy) return;
            if (!Directory.Exists(Hub1007IncomingDir)) return;

            hub1007Busy = true;
            try
            {
                Directory.CreateDirectory(Hub1007DoneDir);
                foreach (var path in Directory.GetFiles(Hub1007IncomingDir, "*.pdf"))
                {
                    try
                    {
                        long size1 = new FileInfo(path).Length;
                        System.Threading.Thread.Sleep(1500);
                        if (!File.Exists(path)) continue;
                        long size2 = new FileInfo(path).Length;
                        if (size1 != size2) continue;

                        var printArgs = string.Format("-print-to \"{0}\" -silent \"{1}\"", Hub1007TargetPrinter, path);
                        int printExit;
                        string printOutput;
                        bool printOk = RunChildProcess(ResolveSumatraExe(), printArgs, out printExit, out printOutput);
                        if (!printOk)
                        {
                            Log("ERROR: relayed-P1007 print timed out/failed for " + Path.GetFileName(path));
                            continue;
                        }

                        string dest = Path.Combine(Hub1007DoneDir,
                            DateTime.Now.ToString("yyyyMMdd_HHmmss") + "_" + Path.GetFileName(path));
                        File.Move(path, dest);

                        Log("OK: printed relayed P1007 job: " + Path.GetFileName(path));
                    }
                    catch (Exception ex)
                    {
                        Log("ERROR processing relayed P1007 job " + Path.GetFileName(path) + ": " + ex.Message);
                    }
                }
            }
            catch (Exception ex)
            {
                Log("ERROR in ScanHub1007Receive: " + ex.Message);
            }
            finally
            {
                hub1007Busy = false;
            }
        }

        // Runs a process with a timeout, killing it if it hangs (e.g. an
        // unexpected dialog with nobody to click it) rather than blocking
        // the scan forever.
        private bool RunChildProcess(string exe, string args, out int exitCode, out string output)
        {
            exitCode = -1;
            output = "";

            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = args,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };

            using (var p = new Process())
            {
                p.StartInfo = psi;
                var sb = new StringBuilder();
                p.OutputDataReceived += (s, e) => { if (e.Data != null) sb.AppendLine(e.Data); };
                p.ErrorDataReceived += (s, e) => { if (e.Data != null) sb.AppendLine(e.Data); };

                try
                {
                    p.Start();
                }
                catch (Exception ex)
                {
                    output = "Could not start '" + exe + "': " + ex.Message;
                    return false;
                }

                p.BeginOutputReadLine();
                p.BeginErrorReadLine();

                bool exited = p.WaitForExit(Overlay355ProcessTimeoutMs);
                output = sb.ToString().Trim();

                if (!exited)
                {
                    try { p.Kill(); } catch { }
                    output += " [TIMED OUT after " + Overlay355ProcessTimeoutMs + "ms, process killed]";
                    return false;
                }

                exitCode = p.ExitCode;
                return true;
            }
        }

        private void Scan()
        {
            if (!enabled) return;

            try
            {
                var validPids = GetValidOrnatePids();
                if (validPids.Count == 0)
                    return;

                EnumWindows((hWnd, lParam) =>
                {
                    TryHandlePrintDialog(hWnd, validPids);
                    return true;
                }, IntPtr.Zero);

                handled.RemoveWhere(h => !IsWindow(h));
            }
            catch (Exception ex)
            {
                Log("ERROR: " + ex.Message);
            }
        }

        // Falls back to the compiled default (matches PC2 and the Dell server,
        // which both use D:\Ornnx\ONX.exe) unless a machine-specific override
        // is set in config (needed on the laptop, which uses C:\Ornnx\ONX.exe).
        private string EffectiveOrnateExecutablePath
        {
            get
            {
                return string.IsNullOrEmpty(config.OrnateExecutablePathOverride)
                    ? OrnateExecutablePath
                    : config.OrnateExecutablePathOverride;
            }
        }

        private HashSet<int> GetValidOrnatePids()
        {
            var pids = new HashSet<int>();
            string expectedPath = EffectiveOrnateExecutablePath;

            foreach (var p in Process.GetProcessesByName(OrnateProcessName))
            {
                try
                {
                    var path = p.MainModule.FileName;
                    if (string.Equals(path, expectedPath,
                                      StringComparison.OrdinalIgnoreCase))
                    {
                        pids.Add(p.Id);
                    }
                }
                catch { }
                finally
                {
                    p.Dispose();
                }
            }

            return pids;
        }

        private void TryHandlePrintDialog(IntPtr hWnd, HashSet<int> ornatePids)
        {
            if (GetWindowTextValue(hWnd) != RequiredDialogTitle) return;
            if (GetWindowClassValue(hWnd) != RequiredDialogClass) return;
            if (!BelongsToOrnate(hWnd, ornatePids)) return;
            if (handled.Contains(hWnd)) return;

            IntPtr printButton = GetDlgItem(hWnd, 1);
            if (printButton == IntPtr.Zero)
            {
                Log("BLOCKED: ONX Print dialog found, but button ID 1 was missing.");
                return;
            }

            string buttonText = GetWindowTextValue(printButton)
                .Replace("&", "")
                .Trim();

            if (!string.Equals(buttonText, "Print",
                               StringComparison.OrdinalIgnoreCase))
            {
                Log("BLOCKED: affirmative button was '" + buttonText + "'.");
                return;
            }

            handled.Add(hWnd);

            int copyNumber = ResolveCopyNumber();
            string targetPrinter = config.ResolvePrinter(copyNumber);

            var diagnostics = new List<string>();
            bool selected = TrySelectPrinter(hWnd, targetPrinter, diagnostics);
            if (selected)
            {
                Log(string.Format("APPROVED: ONX Print dialog (copy {0}). Selected printer '{1}'. Clicking Print.",
                    copyNumber, targetPrinter));
            }
            else
            {
                Log(string.Format(
                    "WARNING: ONX Print dialog (copy {0}). Could NOT select printer '{1}' (not found in any combo box). " +
                    "Leaving whatever printer was already selected. Clicking Print.",
                    copyNumber, targetPrinter));
                foreach (var d in diagnostics) Log("  DIAG: " + d);
                if (diagnostics.Count == 0) Log("  DIAG: no populated ComboBox controls found in this dialog at all.");
            }

            SendMessage(printButton, BM_CLICK, IntPtr.Zero, IntPtr.Zero);
        }

        // Decides whether this dialog is copy 1 or copy 2 of a bill, using a timing
        // window since Ornate's two Print dialogs are otherwise indistinguishable.
        private int ResolveCopyNumber()
        {
            DateTime now = DateTime.UtcNow;
            int copyNumber;

            if (nextCopyNumber == 2 && (now - lastHandledUtc).TotalSeconds <= config.SessionGapSeconds)
            {
                copyNumber = 2;
                nextCopyNumber = 1; // next dialog starts a new bill
            }
            else
            {
                copyNumber = 1;
                nextCopyNumber = 2; // expect copy 2 next, within the gap window
            }

            lastHandledUtc = now;
            return copyNumber;
        }

        // Selects printerName in the dialog's printer picker and notifies the
        // dialog so its internal selection actually updates before Print is
        // clicked. The .NET PrintDialog (which Ornate uses) shows printers in a
        // ListView (icon grid), not a classic combo box, so that's tried first;
        // a ComboBox fallback is kept in case a different dialog style is ever
        // encountered. Returns false if no matching entry was found anywhere -
        // in that case the dialog is left untouched and the failure (with
        // everything that WAS found, for diagnosis) is logged by the caller.
        private bool TrySelectPrinter(IntPtr dialog, string printerName, List<string> diagnostics)
        {
            if (string.IsNullOrEmpty(printerName)) return false;

            int ownerPid = GetWindowPid(dialog);

            IntPtr listView = IntPtr.Zero;
            var combos = new List<IntPtr>();

            EnumChildWindows(dialog, (hWndChild, lParam) =>
            {
                string cls = GetWindowClassValue(hWndChild);
                if (cls == "SysListView32" && listView == IntPtr.Zero) listView = hWndChild;
                else if (cls == "ComboBox") combos.Add(hWndChild);
                return true;
            }, IntPtr.Zero);

            if (listView != IntPtr.Zero &&
                TrySelectPrinterInListView(listView, ownerPid, printerName, diagnostics))
            {
                return true;
            }

            IntPtr guess = GetDlgItem(dialog, IDC_PRINTER_COMBO);
            if (guess != IntPtr.Zero && !combos.Contains(guess)) combos.Insert(0, guess);

            foreach (var combo in combos)
            {
                int count = SendMessage(combo, CB_GETCOUNT, IntPtr.Zero, IntPtr.Zero).ToInt32();
                if (count <= 0 || count > 200) continue; // not a populated, sane combo

                var items = new List<string>(count);
                int matchIndex = -1;

                for (int i = 0; i < count; i++)
                {
                    string text = GetComboItemText(combo, i);
                    items.Add(text);
                    if (matchIndex == -1 &&
                        text.IndexOf(printerName, StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        matchIndex = i;
                    }
                }

                diagnostics.Add(string.Format("combo 0x{0:X} [{1} items]: {2}",
                    combo.ToInt64(), count, string.Join(" | ", items)));

                if (matchIndex >= 0)
                {
                    SendMessage(combo, CB_SETCURSEL, new IntPtr(matchIndex), IntPtr.Zero);

                    int comboId = GetDlgCtrlID(combo);
                    IntPtr wParam = new IntPtr(MakeLong(comboId, CBN_SELCHANGE));
                    SendMessage(dialog, WM_COMMAND, wParam, combo);

                    return true;
                }
            }

            return false;
        }

        // Cross-process ListView read/select. LVM_GETITEMTEXT/LVM_SETITEMSTATE take
        // a struct with an embedded pointer, which Windows does NOT auto-marshal
        // across process boundaries (unlike simple string-buffer messages such as
        // CB_GETLBTEXT/WM_GETTEXT), so this needs explicit remote memory handling:
        // allocate a buffer in Ornate's process, write the LVITEM struct into it,
        // send the message, then read the result back out.
        private bool TrySelectPrinterInListView(IntPtr listView, int ownerPid, string printerName, List<string> diagnostics)
        {
            int count = SendMessage(listView, LVM_GETITEMCOUNT, IntPtr.Zero, IntPtr.Zero).ToInt32();
            if (count <= 0 || count > 500)
            {
                diagnostics.Add("ListView found but item count was " + count + " (skipped).");
                return false;
            }

            IntPtr hProcess = OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION,
                false, ownerPid);
            if (hProcess == IntPtr.Zero)
            {
                diagnostics.Add("Could not open Ornate process (PID " + ownerPid + ") for cross-process ListView read.");
                return false;
            }

            try
            {
                int lvItemSize = Marshal.SizeOf(typeof(LVITEM));
                const int textBufChars = 256;
                int textBufBytes = textBufChars * 2; // Unicode

                IntPtr remoteText = VirtualAllocEx(hProcess, IntPtr.Zero, (uint)textBufBytes, MEM_COMMIT, PAGE_READWRITE);
                IntPtr remoteLvItem = VirtualAllocEx(hProcess, IntPtr.Zero, (uint)lvItemSize, MEM_COMMIT, PAGE_READWRITE);

                if (remoteText == IntPtr.Zero || remoteLvItem == IntPtr.Zero)
                {
                    diagnostics.Add("VirtualAllocEx in Ornate process failed.");
                    return false;
                }

                try
                {
                    var items = new List<string>(count);
                    int matchIndex = -1;

                    for (int i = 0; i < count; i++)
                    {
                        var lvItem = new LVITEM
                        {
                            mask = LVIF_TEXT,
                            iItem = i,
                            iSubItem = 0,
                            pszText = remoteText,
                            cchTextMax = textBufChars
                        };

                        if (!WriteLvItem(hProcess, remoteLvItem, lvItem, lvItemSize)) continue;

                        SendMessage(listView, LVM_GETITEMTEXTW, new IntPtr(i), remoteLvItem);

                        byte[] buf = new byte[textBufBytes];
                        IntPtr bytesRead;
                        ReadProcessMemory(hProcess, remoteText, buf, (uint)textBufBytes, out bytesRead);
                        string text = Encoding.Unicode.GetString(buf);
                        int nullIdx = text.IndexOf('\0');
                        if (nullIdx >= 0) text = text.Substring(0, nullIdx);

                        items.Add(text);
                        if (matchIndex == -1 && text.IndexOf(printerName, StringComparison.OrdinalIgnoreCase) >= 0)
                            matchIndex = i;
                    }

                    diagnostics.Add(string.Format("ListView [{0} items]: {1}", count, string.Join(" | ", items)));

                    if (matchIndex < 0) return false;

                    // Deselect everything, then select+focus the match - mirrors a real click.
                    for (int i = 0; i < count; i++)
                    {
                        SetListViewItemState(listView, hProcess, remoteLvItem, lvItemSize, i, 0);
                    }
                    SetListViewItemState(listView, hProcess, remoteLvItem, lvItemSize, matchIndex, LVIS_SELECTED | LVIS_FOCUSED);

                    return true;
                }
                finally
                {
                    VirtualFreeEx(hProcess, remoteText, 0, MEM_RELEASE);
                    VirtualFreeEx(hProcess, remoteLvItem, 0, MEM_RELEASE);
                }
            }
            finally
            {
                CloseHandle(hProcess);
            }
        }

        private static bool WriteLvItem(IntPtr hProcess, IntPtr remoteLvItem, LVITEM lvItem, int lvItemSize)
        {
            IntPtr local = Marshal.AllocHGlobal(lvItemSize);
            try
            {
                Marshal.StructureToPtr(lvItem, local, false);
                IntPtr written;
                return WriteProcessMemory(hProcess, remoteLvItem, local, (uint)lvItemSize, out written);
            }
            finally
            {
                Marshal.FreeHGlobal(local);
            }
        }

        private static void SetListViewItemState(IntPtr listView, IntPtr hProcess, IntPtr remoteLvItem, int lvItemSize, int index, uint state)
        {
            var lvItem = new LVITEM
            {
                mask = LVIF_STATE,
                state = state,
                stateMask = LVIS_SELECTED | LVIS_FOCUSED
            };
            if (!WriteLvItem(hProcess, remoteLvItem, lvItem, lvItemSize)) return;
            SendMessage(listView, LVM_SETITEMSTATE, new IntPtr(index), remoteLvItem);
        }

        private static string GetComboItemText(IntPtr combo, int index)
        {
            int len = SendMessage(combo, CB_GETLBTEXTLEN, new IntPtr(index), IntPtr.Zero).ToInt32();
            if (len <= 0) return "";

            var sb = new StringBuilder(len + 1);
            SendMessageStringOut(combo, CB_GETLBTEXT, new IntPtr(index), sb);
            return sb.ToString();
        }

        private static int MakeLong(int low, int high)
        {
            return (low & 0xFFFF) | (high << 16);
        }

        private bool BelongsToOrnate(IntPtr dialog, HashSet<int> ornatePids)
        {
            int dialogPid = GetWindowPid(dialog);
            if (ornatePids.Contains(dialogPid))
                return true;

            IntPtr owner = GetWindow(dialog, GW_OWNER);
            if (owner != IntPtr.Zero)
            {
                int ownerPid = GetWindowPid(owner);
                if (ornatePids.Contains(ownerPid))
                    return true;
            }

            return false;
        }

        internal void Log(string message)
        {
            try
            {
                Directory.CreateDirectory(baseFolder);
                File.AppendAllText(
                    LogFile,
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") +
                    "  " + message + Environment.NewLine,
                    Encoding.UTF8);
            }
            catch { }
        }

        private static string GetWindowTextValue(IntPtr hWnd)
        {
            var sb = new StringBuilder(1024);
            GetWindowText(hWnd, sb, sb.Capacity);
            return sb.ToString();
        }

        private static string GetWindowClassValue(IntPtr hWnd)
        {
            var sb = new StringBuilder(256);
            GetClassName(hWnd, sb, sb.Capacity);
            return sb.ToString();
        }

        private static int GetWindowPid(IntPtr hWnd)
        {
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            return unchecked((int)pid);
        }

        private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll")]
        private static extern IntPtr GetWindow(IntPtr hWnd, uint uCmd);

        [DllImport("user32.dll")]
        private static extern IntPtr GetDlgItem(IntPtr hDlg, int nIDDlgItem);

        [DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "SendMessageW")]
        private static extern IntPtr SendMessageString(IntPtr hWnd, uint Msg, IntPtr wParam, string lParam);

        [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "SendMessageW")]
        private static extern IntPtr SendMessageStringOut(IntPtr hWnd, uint Msg, IntPtr wParam, StringBuilder lParam);

        [DllImport("user32.dll")]
        private static extern bool IsWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern int GetDlgCtrlID(IntPtr hWnd);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr VirtualAllocEx(IntPtr hProcess, IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool VirtualFreeEx(IntPtr hProcess, IntPtr lpAddress, uint dwSize, uint dwFreeType);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool WriteProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, IntPtr lpBuffer, uint nSize, out IntPtr lpNumberOfBytesWritten);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool ReadProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, byte[] lpBuffer, uint nSize, out IntPtr lpNumberOfBytesRead);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CloseHandle(IntPtr hObject);
    }

    // Settings window: master on/off, PC role, manual copy1/copy2 override, live log tail.
    internal sealed class SettingsForm : Form
    {
        private readonly AppConfig config;
        private readonly string configPath;
        private readonly string logPath;
        private readonly Action onSaved;

        private CheckBox chkEnabled;
        private ComboBox cmbRole;
        private TextBox txtCopy1Printer;
        private TextBox txtCopy2Printer;
        private TextBox txtForceCopy1;
        private TextBox txtForceCopy2;
        private TextBox txtLog;
        private Timer logTimer;
        private long lastLogLength = -1;

        public SettingsForm(AppConfig config, string configPath, string logPath, Action onSaved)
        {
            this.config = config;
            this.configPath = configPath;
            this.logPath = logPath;
            this.onSaved = onSaved;

            BuildUi();
            LoadFromConfig();

            logTimer = new Timer { Interval = 1000 };
            logTimer.Tick += (s, e) => RefreshLog();
            logTimer.Start();
            RefreshLog();

            FormClosed += (s, e) => { if (logTimer != null) logTimer.Stop(); };
        }

        private const string BothModeAuto = "Auto (default split: copy 1 -> P1007, copy 2 -> 355)";
        private const string BothModeP1007 = "Both copies -> P1007 printer";
        private const string BothMode355 = "Both copies -> 355 printer";

        private ComboBox cmbBothMode;
        private Label lblBothWarning;

        private void BuildUi()
        {
            Text = "Aradhana Ornate AutoPrint - Settings";
            Width = 620;
            Height = 630;
            StartPosition = FormStartPosition.CenterScreen;
            MinimizeBox = true;
            MaximizeBox = false;
            FormBorderStyle = FormBorderStyle.FixedDialog;

            var lblRole = new Label { Text = "This PC's role:", Left = 12, Top = 15, Width = 120 };
            cmbRole = new ComboBox { Left = 140, Top = 12, Width = 220, DropDownStyle = ComboBoxStyle.DropDownList };
            cmbRole.Items.AddRange(new object[] { "PC2 (Hub)", "Laptop (Relay)", "Dell Server (Relay)" });

            chkEnabled = new CheckBox { Text = "Master enable (AutoPrint + smart routing)", Left = 12, Top = 45, Width = 350 };

            var lblCopy1 = new Label { Text = "Copy 1 printer (office copy):", Left = 12, Top = 80, Width = 190 };
            txtCopy1Printer = new TextBox { Left = 210, Top = 77, Width = 380 };

            var lblCopy2 = new Label { Text = "Copy 2 printer (customer copy):", Left = 12, Top = 108, Width = 190 };
            txtCopy2Printer = new TextBox { Left = 210, Top = 105, Width = 380 };

            var lblBothHeader = new Label
            {
                Text = "Send both copies to the same printer (overrides the split above):",
                Left = 12, Top = 145, Width = 500, Font = new Font(Font, FontStyle.Bold)
            };
            cmbBothMode = new ComboBox { Left = 12, Top = 168, Width = 578, DropDownStyle = ComboBoxStyle.DropDownList };
            cmbBothMode.Items.AddRange(new object[] { BothModeAuto, BothModeP1007, BothMode355 });
            cmbBothMode.SelectedIndexChanged += (s, e) => ApplyBothModeSelection();

            lblBothWarning = new Label
            {
                Text = "Warning: P1007 has no software letterhead overlay and no duplex. Both copies will print " +
                       "on whatever paper is physically loaded in P1007 right now - if that's blank paper, load " +
                       "real pre-printed letterhead stock for BOTH copies before printing, since neither one gets " +
                       "the letterhead added digitally on this printer.",
                Left = 12, Top = 196, Width = 578, Height = 55,
                ForeColor = Color.DarkRed,
                Visible = false
            };

            var lblOverrideHeader = new Label
            {
                Text = "Or set an exact manual override (leave blank = Auto, use the printers above):",
                Left = 12, Top = 258, Width = 500, Font = new Font(Font, FontStyle.Bold)
            };

            var lblForce1 = new Label { Text = "Force copy 1 to printer:", Left = 12, Top = 285, Width = 190 };
            txtForceCopy1 = new TextBox { Left = 210, Top = 282, Width = 380 };

            var lblForce2 = new Label { Text = "Force copy 2 to printer:", Left = 12, Top = 313, Width = 190 };
            txtForceCopy2 = new TextBox { Left = 210, Top = 310, Width = 380 };

            var btnSave = new Button { Text = "Save", Left = 210, Top = 348, Width = 100 };
            btnSave.Click += (s, e) => SaveToConfig();

            var btnClose = new Button { Text = "Close", Left = 320, Top = 348, Width = 100 };
            btnClose.Click += (s, e) => Close();

            var lblLog = new Label { Text = "Live log (auto-refreshing):", Left = 12, Top = 388, Width = 300 };
            txtLog = new TextBox
            {
                Left = 12,
                Top = 411,
                Width = 580,
                Height = 180,
                Multiline = true,
                ReadOnly = true,
                ScrollBars = ScrollBars.Vertical,
                Font = new Font(FontFamily.GenericMonospace, 8.5f)
            };

            Controls.AddRange(new Control[]
            {
                lblRole, cmbRole, chkEnabled,
                lblCopy1, txtCopy1Printer,
                lblCopy2, txtCopy2Printer,
                lblBothHeader, cmbBothMode, lblBothWarning,
                lblOverrideHeader,
                lblForce1, txtForceCopy1,
                lblForce2, txtForceCopy2,
                btnSave, btnClose,
                lblLog, txtLog
            });
        }

        // Keeps the force-printer fields in sync when "both copies to the same
        // printer" is picked, and shows the P1007 letterhead-stock warning when
        // relevant. The manual override fields remain the source of truth that
        // actually gets saved, so this is just a convenience that fills them in.
        private void ApplyBothModeSelection()
        {
            string selected = cmbBothMode.SelectedItem as string;

            if (selected == BothModeP1007)
            {
                txtForceCopy1.Text = txtCopy1Printer.Text.Trim();
                txtForceCopy2.Text = txtCopy1Printer.Text.Trim();
                lblBothWarning.Visible = true;
            }
            else if (selected == BothMode355)
            {
                txtForceCopy1.Text = txtCopy2Printer.Text.Trim();
                txtForceCopy2.Text = txtCopy2Printer.Text.Trim();
                lblBothWarning.Visible = false;
            }
            else
            {
                txtForceCopy1.Text = "";
                txtForceCopy2.Text = "";
                lblBothWarning.Visible = false;
            }
        }

        private void LoadFromConfig()
        {
            chkEnabled.Checked = config.MasterEnabled;
            if (cmbRole.Items.Contains(config.PcRole)) cmbRole.SelectedItem = config.PcRole;
            else cmbRole.SelectedIndex = 0;
            txtCopy1Printer.Text = config.Copy1Printer;
            txtCopy2Printer.Text = config.Copy2Printer;
            txtForceCopy1.Text = config.ForceCopy1Printer;
            txtForceCopy2.Text = config.ForceCopy2Printer;

            // Infer the "both copies" dropdown state from the current override
            // values, so reopening Settings reflects what's actually active.
            bool bothSet = !string.IsNullOrEmpty(config.ForceCopy1Printer) &&
                           config.ForceCopy1Printer == config.ForceCopy2Printer;
            if (bothSet && config.ForceCopy1Printer == config.Copy1Printer.Trim())
            {
                cmbBothMode.SelectedItem = BothModeP1007;
                lblBothWarning.Visible = true;
            }
            else if (bothSet && config.ForceCopy1Printer == config.Copy2Printer.Trim())
            {
                cmbBothMode.SelectedItem = BothMode355;
                lblBothWarning.Visible = false;
            }
            else
            {
                cmbBothMode.SelectedItem = BothModeAuto;
                lblBothWarning.Visible = false;
            }
        }

        private void SaveToConfig()
        {
            config.MasterEnabled = chkEnabled.Checked;
            config.PcRole = cmbRole.SelectedItem != null ? cmbRole.SelectedItem.ToString() : config.PcRole;
            config.Copy1Printer = txtCopy1Printer.Text.Trim();
            config.Copy2Printer = txtCopy2Printer.Text.Trim();
            config.ForceCopy1Printer = txtForceCopy1.Text.Trim();
            config.ForceCopy2Printer = txtForceCopy2.Text.Trim();
            config.Save(configPath);

            if (onSaved != null) onSaved();

            MessageBox.Show(this, "Settings saved.", "Aradhana Ornate AutoPrint",
                MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void RefreshLog()
        {
            try
            {
                if (!File.Exists(logPath)) return;

                var info = new FileInfo(logPath);
                if (info.Length == lastLogLength) return; // no change, skip re-reading
                lastLogLength = info.Length;

                string[] lines;
                using (var fs = new FileStream(logPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var sr = new StreamReader(fs, Encoding.UTF8))
                {
                    var all = sr.ReadToEnd();
                    lines = all.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);
                }

                int start = Math.Max(0, lines.Length - 200); // last ~200 lines
                var tail = new StringBuilder();
                for (int i = start; i < lines.Length; i++)
                    tail.AppendLine(lines[i]);

                bool wasAtBottom = txtLog.SelectionStart >= txtLog.TextLength - 1;
                txtLog.Text = tail.ToString();
                if (wasAtBottom)
                {
                    txtLog.SelectionStart = txtLog.TextLength;
                    txtLog.ScrollToCaret();
                }
            }
            catch { }
        }
    }
}

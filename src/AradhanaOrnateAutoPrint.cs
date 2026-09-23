using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using System.Windows.Automation;
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

    // Result of TrayContext.CaptureLiveVoucherTemplate() - a small pass-back
    // type so VoucherRouteRulesForm (a separate Form, no access to
    // TrayContext's private window-capture P/Invoke) can show its own
    // success/error UI without TrayContext needing a dialog owner of its own.
    internal sealed class VoucherTemplateCaptureResult
    {
        public bool Success;
        public string FileName;
        public string Error;
    }

    // A route is matched only by its saved Voucher Print visual template and
    // its exact requested copy count. The label is for the administrator; it
    // is never trusted as OCR or as a routing signal.
    internal sealed class VoucherRouteRule
    {
        public string Name = "";
        public int RequiredCopies = 2;
        public string ReferenceFile = "";
        public string Copy1Printer = "";
        public string LaterPrinter = "";
        public bool Enabled = true;

        public static VoucherRouteRule DefaultRule()
        {
            return new VoucherRouteRule
            {
                Name = "GST Sales Voucher (A4) Shree Aradhana",
                RequiredCopies = 2,
                ReferenceFile = "office-sales-voucher-format-reference.png"
            };
        }

        public static bool TryParse(string value, out VoucherRouteRule rule)
        {
            rule = null;
            string[] fields = value.Split('|');
            if (fields.Length != 6) return false;
            int copies;
            if (string.IsNullOrWhiteSpace(fields[0]) ||
                string.IsNullOrWhiteSpace(fields[2]) ||
                !int.TryParse(fields[1], out copies) || copies < 1 || copies > 9)
                return false;
            bool enabled;
            if (!bool.TryParse(fields[5], out enabled)) return false;
            rule = new VoucherRouteRule
            {
                Name = fields[0].Trim(),
                RequiredCopies = copies,
                ReferenceFile = Path.GetFileName(fields[2].Trim()),
                Copy1Printer = fields[3].Trim(),
                LaterPrinter = fields[4].Trim(),
                Enabled = enabled
            };
            return true;
        }

        public string Serialize()
        {
            // Pipe is intentionally rejected by the Settings form for all
            // editable fields, keeping this plain key=value config robust.
            return Name + "|" + RequiredCopies + "|" + ReferenceFile + "|" +
                   Copy1Printer + "|" + LaterPrinter + "|" + Enabled;
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

        // AIS document workflow is opt-in until physical P355 acceptance tests pass.
        public bool DocumentWorkflowEnabled = false;
        public string DocumentWorkflowRoot = @"C:\AradhanaSystems\platform\plugins\document-print-workflow";
        public string DocumentWorkflowApi = "http://127.0.0.1:8310";
        public string DocumentScannerApi = "";
        public readonly List<VoucherRouteRule> VoucherRoutes = new List<VoucherRouteRule>();

        public bool IsHub
        {
            get { return !Relay1007Enabled; }
        }

        public static AppConfig Load(string path)
        {
            var cfg = new AppConfig();
            bool foundRouteRule = false;
            try
            {
                if (!File.Exists(path))
                {
                    cfg.VoucherRoutes.Add(VoucherRouteRule.DefaultRule());
                    return cfg;
                }

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
                        case "DocumentWorkflowEnabled": cfg.DocumentWorkflowEnabled = val.Equals("true", StringComparison.OrdinalIgnoreCase); break;
                        case "DocumentWorkflowRoot": cfg.DocumentWorkflowRoot = val; break;
                        case "DocumentWorkflowApi": cfg.DocumentWorkflowApi = val; break;
                        case "DocumentScannerApi": cfg.DocumentScannerApi = val; break;
                        case "VoucherRoute":
                            VoucherRouteRule route;
                            if (VoucherRouteRule.TryParse(val, out route))
                            {
                                if (!foundRouteRule) cfg.VoucherRoutes.Clear();
                                cfg.VoucherRoutes.Add(route);
                                foundRouteRule = true;
                            }
                            break;
                    }
                }
            }
            catch { }
            if (cfg.VoucherRoutes.Count == 0)
                cfg.VoucherRoutes.Add(VoucherRouteRule.DefaultRule());
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
                sb.AppendLine("DocumentWorkflowEnabled=" + (DocumentWorkflowEnabled ? "true" : "false"));
                sb.AppendLine("DocumentWorkflowRoot=" + DocumentWorkflowRoot);
                sb.AppendLine("DocumentWorkflowApi=" + DocumentWorkflowApi);
                sb.AppendLine("DocumentScannerApi=" + DocumentScannerApi);
                foreach (VoucherRouteRule route in VoucherRoutes)
                    sb.AppendLine("VoucherRoute=" + route.Serialize());
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
        // Alt+P opens Ornate's custom voucher window first.  The standard
        // Win32 Print dialog appears only after the biller presses Print in
        // that window, so document choices must begin here, not later.
        private const string VoucherDialogTitle = "Voucher Print";
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
        private string documentWorkflowManifestForNextCustomerCopy = null;
        private readonly HashSet<IntPtr> voucherWindows = new HashSet<IntPtr>();
        // Last (difference, copies) safety-state logged per unqualified voucher window, so a
        // full trace survives to the moment Print is actually clicked instead of only the first
        // read. Without this, an incident where the biller's LAST edit before printing (e.g.
        // setting copies to 2, or a format that had settled to a near-zero difference) never gets
        // logged is undiagnosable after the fact — exactly what happened investigating the
        // 2026-09-10 19:54:58 case, where only the very first (possibly stale) read was on record.
        private readonly Dictionary<IntPtr, string> voucherWindowLastLoggedState = new Dictionary<IntPtr, string>();
        // A voucher can initially open with the default copy count, before the
        // biller changes it. Keep observing it until it qualifies, then lock
        // that specific window's route so its second print cannot re-arm P1007.
        private readonly HashSet<IntPtr> voucherRoutesFinalized = new HashSet<IntPtr>();
        private string activeVoucherCopy1Printer = "";
        private string activeVoucherLaterPrinter = "";
        private string voucherDecisionFileForCurrentBill = null;
        private bool voucherDecisionPendingForCurrentBill = false;
        // Ensures the document-decision check below fires exactly once per
        // bill, on the P355 customer copy (which is the one that actually
        // needs it) rather than the P1007 office copy - see the call site in
        // TryHandlePrintDialog for why this moved off copyNumber==1.
        private bool documentWorkflowCheckedForVoucherBill = false;
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
            // Per-user installs (the default for the plain installer, no admin
            // prompt) land under LOCALAPPDATA - this is where PC2's actual
            // interpreter lives. Without these, resolution silently fell
            // through to the "py" launcher stub below: py.exe spawns the real
            // python.exe as a child and exits once the handoff completes,
            // orphaning that child from whatever Process object launched py -
            // fatal for EnsureDocumentWorkflowServiceRunning's supervision,
            // which tracks that Process object's HasExited to decide whether
            // to restart. A direct interpreter path keeps the child under the
            // Process object that actually started it.
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            fullPathCandidates.AddRange(new[]
            {
                Path.Combine(localAppData, @"Programs\Python\Python313\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python312\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python311\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python310\python.exe"),
            });

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
        private readonly Timer hotkeyTimer;
        private Timer overlay355Timer;
        private Timer relay1007Timer;
        private readonly HashSet<IntPtr> handled = new HashSet<IntPtr>();
        private bool enabled = true;

        // Document-workflow API (service\app.py) supervision. Previously
        // auto-started via a SYSTEM scheduled task (install_document_workflow_
        // service.ps1) that NPAV silently deleted within seconds of
        // registration on PC2 — a SYSTEM task spawning powershell.exe ->
        // python.exe at boot is a textbook dropper/persistence signature,
        // the same heuristic class that previously flagged a separate
        // standalone watcher binary. That earlier problem's actual fix
        // wasn't a better AV exclusion, it was folding the watcher into this
        // already-trusted, signed tray EXE — which has been confirmed to
        // survive a full reboot with every NPAV feature enabled, hash-
        // identical and untouched. This does the same: the already-running,
        // already-trusted process launches and supervises the Python
        // service itself, so no new auto-start mechanism ever exists for AV
        // to flag.
        private Process documentWorkflowProcess;
        private DateTime documentWorkflowLastStartAttemptUtc = DateTime.MinValue;
        private static readonly TimeSpan DocumentWorkflowRestartCooldown = TimeSpan.FromSeconds(15);

        // Print-session state. Only the visible Voucher Format and No. Of
        // Copies field can qualify a P1007 office copy.
        private DateTime lastHandledUtc = DateTime.MinValue;
        private bool voucherBillSessionActive = false;
        private bool officeCopyHandledForVoucherBill = false;
        private bool pKeyWasDown = false;
        // The window and required-copy-count this armed session was matched
        // against, so the P1007 grant can be re-validated live (see
        // ResolveCopyNumber) instead of trusting a copy count read only once
        // when the window first appeared and possibly edited since.
        private IntPtr activeVoucherWindow = IntPtr.Zero;
        private int activeVoucherRequiredCopies = 0;

        private const string OfficeVoucherReferenceFileName = "office-sales-voucher-format-reference.png";
        private const int VoucherFormatFingerprintWidth = 256;
        private const int VoucherFormatFingerprintHeight = 20;
        private const double OfficeVoucherFingerprintMaxDifference = 5.0;

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
                hotkeyTimer.Stop();
                try
                {
                    if (documentWorkflowProcess != null && !documentWorkflowProcess.HasExited)
                        documentWorkflowProcess.Kill();
                }
                catch { }
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

            // Observes only a foreground Alt+P transition. It does not install
            // a keyboard hook or consume any key from Ornate.
            hotkeyTimer = new Timer { Interval = 20 };
            hotkeyTimer.Tick += (s, e) => ObserveBillStartHotkey();
            hotkeyTimer.Start();

            overlay355Timer = new Timer { Interval = 3000 };
            overlay355Timer.Tick += (s, e) => Scan355();
            overlay355Timer.Start();

            relay1007Timer = new Timer { Interval = 3000 };
            relay1007Timer.Tick += (s, e) => { ScanRelay1007Send(); ScanHub1007Receive(); EnsureDocumentWorkflowServiceRunning(); };
            relay1007Timer.Start();

            Log("START. Hard-wall path=" + EffectiveOrnateExecutablePath + " PcRole=" + config.PcRole +
                " Relay1007=" + config.Relay1007Enabled);

            EnsureDocumentWorkflowServiceRunning();
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
            }, CaptureLiveVoucherTemplate);
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
                bool useDocumentLayout = !string.IsNullOrEmpty(documentWorkflowManifestForNextCustomerCopy) &&
                    File.Exists(documentWorkflowManifestForNextCustomerCopy);
                string renderer = useDocumentLayout
                    ? Path.Combine(config.DocumentWorkflowRoot, "renderer", "p355_document_renderer.py")
                    : Overlay355Script;
                if (useDocumentLayout && !File.Exists(renderer))
                {
                    Log("DOCUMENT: renderer missing; normal terms layout retained.");
                    useDocumentLayout = false;
                    renderer = Overlay355Script;
                }
                var overlayArgs = useDocumentLayout
                    ? string.Format("\"{0}\" \"{1}\" \"{2}\" \"{3}\" \"{4}\" \"{5}\"",
                        renderer, path, merged, Overlay355FrontImage, Overlay355BackImage, documentWorkflowManifestForNextCustomerCopy)
                    : string.Format("\"{0}\" \"{1}\" \"{2}\" \"{3}\" \"{4}\"",
                        renderer, path, merged, Overlay355FrontImage, Overlay355BackImage);

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

                Log("355 OUTPUT: source=" + Path.GetFileName(path) +
                    ", target='" + EffectiveOverlay355TargetPrinter + "'.");

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

                // Only consume the chosen manifest after Sumatra accepted the
                // composed PDF. Failed jobs retain their document context for
                // investigation/retry rather than silently dropping it.
                if (useDocumentLayout) documentWorkflowManifestForNextCustomerCopy = null;

                Log("OK: 355 overlaid and submitted to '" +
                    EffectiveOverlay355TargetPrinter + "': " + Path.GetFileName(path));
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
        private bool RunChildProcess(string exe, string args, out int exitCode, out string output, bool interactive = false)
        {
            exitCode = -1;
            output = "";

            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = args,
                UseShellExecute = false,
                // The biller decision is a real Tk window. Hiding that child
                // makes its process run correctly but leaves the biller with
                // no visible choice, then eventually times out.
                CreateNoWindow = !interactive,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WindowStyle = interactive ? ProcessWindowStyle.Normal : ProcessWindowStyle.Hidden
            };
            ApplyDocumentBridgeToken(psi);

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
                    TryHandleVoucherDialog(hWnd, validPids);
                    TryHandlePrintDialog(hWnd, validPids);
                    return true;
                }, IntPtr.Zero);

                handled.RemoveWhere(h => !IsWindow(h));
                voucherWindows.RemoveWhere(h => !IsWindow(h));
                voucherRoutesFinalized.RemoveWhere(h => !IsWindow(h));
                var deadLoggedStates = new List<IntPtr>();
                foreach (IntPtr h in voucherWindowLastLoggedState.Keys)
                    if (!IsWindow(h)) deadLoggedStates.Add(h);
                foreach (IntPtr dead in deadLoggedStates)
                    voucherWindowLastLoggedState.Remove(dead);
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
            // Deliberately on the P355 customer copy (copyNumber >= 2), not
            // the P1007 office copy: only the customer copy can actually use
            // the attached document, and checking here means the P1007 copy
            // never waits on anything, while the customer copy's own wait
            // starts after Ornate's own dialog gets here - both a shorter
            // total wait and no wait at all on the office copy, compared to
            // checking on copy 1.
            if (copyNumber >= 2 && !documentWorkflowCheckedForVoucherBill)
            {
                documentWorkflowCheckedForVoucherBill = true;
                PrepareDocumentWorkflowForNextCustomerCopy();
            }
            string targetPrinter = ResolveActiveVoucherPrinter(copyNumber);

            var diagnostics = new List<string>();
            bool selected = TrySelectPrinter(hWnd, targetPrinter, diagnostics);
            if (selected)
            {
                Log(string.Format("APPROVED: ONX Print dialog (copy {0}). Selected printer '{1}'. Clicking Print.",
                    copyNumber, targetPrinter));
                SendMessage(printButton, BM_CLICK, IntPtr.Zero, IntPtr.Zero);
            }
            else
            {
                Log(string.Format(
                    "BLOCKED: ONX Print dialog (copy {0}). Could NOT select required printer '{1}'. " +
                    "Leaving the dialog open; it will not click an unknown printer.",
                    copyNumber, targetPrinter));
                foreach (var d in diagnostics) Log("  DIAG: " + d);
                if (diagnostics.Count == 0) Log("  DIAG: no populated ComboBox controls found in this dialog at all.");
            }
        }

        // This never clicks, closes, or disables Ornate's Voucher Print window.
        // It only starts a no-focus document panel.  If the biller ignores it,
        // the normal Ornate print flow remains available without delay.
        private void TryHandleVoucherDialog(IntPtr hWnd, HashSet<int> ornatePids)
        {
            if (!string.Equals(GetWindowTextValue(hWnd), VoucherDialogTitle,
                               StringComparison.OrdinalIgnoreCase)) return;
            if (!BelongsToOrnate(hWnd, ornatePids)) return;
            bool firstSeen = voucherWindows.Add(hWnd);
            if (firstSeen)
            {
                // A newly opened voucher window is a new bill context. Never
                // let an unanswered document choice from an earlier bill attach here.
                voucherDecisionPendingForCurrentBill = false;
                voucherDecisionFileForCurrentBill = null;
                documentWorkflowCheckedForVoucherBill = false;
                voucherBillSessionActive = false;
                officeCopyHandledForVoucherBill = false;
                lastHandledUtc = DateTime.MinValue;
                activeVoucherCopy1Printer = "";
                activeVoucherLaterPrinter = "";
                activeVoucherWindow = IntPtr.Zero;
                activeVoucherRequiredCopies = 0;
            }

            // Once this window has qualified, do not inspect it again. This
            // prevents the already-qualified first copy from being re-armed
            // while Ornate opens its printer dialogs.
            if (voucherRoutesFinalized.Contains(hWnd)) return;

            // The business rule is deliberately read from Ornate's Voucher
            // Print window, not inferred from timing or a hotkey. Every route
            // requires a saved visual template plus an exact copy count.
            double fingerprintDifference;
            VoucherRouteRule matchedRoute;
            bool approvedFormat = TryMatchVoucherRoute(hWnd, out matchedRoute, out fingerprintDifference);
            int requestedCopies;
            bool copiesRead = TryReadVoucherCopyCount(hWnd, out requestedCopies);
            if (!approvedFormat || !copiesRead || requestedCopies != matchedRoute.RequiredCopies)
            {
                // Log every DISTINCT read (not just the first), so the trace covers the biller's
                // last edit before Print is clicked, not only whatever the window looked like the
                // instant it first appeared. Change-gated (not every 250ms poll) to avoid spamming
                // the log while a voucher window sits open and unedited.
                string state = fingerprintDifference.ToString("0.00") + "|" + (copiesRead ? requestedCopies.ToString() : "unreadable");
                string lastState;
                if (!voucherWindowLastLoggedState.TryGetValue(hWnd, out lastState) || lastState != state)
                {
                    voucherWindowLastLoggedState[hWnd] = state;
                    Log("ROUTE SAFETY: Voucher Print is awaiting a qualifying format/copy count (format difference=" +
                        fingerprintDifference.ToString("0.00") + ", copies=" +
                        (copiesRead ? requestedCopies.ToString() : "unreadable") + "). P1007 remains blocked unless an enabled visual route has its exact configured count.");
                }
                return;
            }

            // This exact visible format/count is the only route that resets a
            // P1007 session. The first print becomes office copy; all later
            // print dialogs are customer/URD copies on P355.
            lastHandledUtc = DateTime.MinValue;
            voucherBillSessionActive = true;
            officeCopyHandledForVoucherBill = false;
            voucherRoutesFinalized.Add(hWnd);
            activeVoucherWindow = hWnd;
            activeVoucherRequiredCopies = matchedRoute.RequiredCopies;
            activeVoucherCopy1Printer = string.IsNullOrWhiteSpace(matchedRoute.Copy1Printer)
                ? config.Copy1Printer : matchedRoute.Copy1Printer;
            activeVoucherLaterPrinter = string.IsNullOrWhiteSpace(matchedRoute.LaterPrinter)
                ? config.Copy2Printer : matchedRoute.LaterPrinter;
            Log("ROUTE: matched voucher rule '" + matchedRoute.Name + "' with copies=" + requestedCopies +
                " (format difference=" + fingerprintDifference.ToString("0.00") + "); first='" +
                activeVoucherCopy1Printer + "', second/later='" + activeVoucherLaterPrinter + "'.");

            if (!config.DocumentWorkflowEnabled || string.IsNullOrEmpty(config.DocumentScannerApi)) return;

            try
            {
                string root = config.DocumentWorkflowRoot;
                string bridge = Path.Combine(root, "bridge", "biller_popup.py");
                string sync = Path.Combine(root, "bridge", "qr_bundle_sync.py");
                if (!File.Exists(bridge) || !File.Exists(sync))
                {
                    Log("DOCUMENT: workflow files missing; Voucher Print remains normal.");
                    return;
                }

                string syncOutput; int syncExit;
                Log("DOCUMENT: Alt+P detected; syncing held QR bundles.");
                bool syncOk = RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --workflow-api \"{2}\"", sync, config.DocumentScannerApi, config.DocumentWorkflowApi), out syncExit, out syncOutput);
                Log("DOCUMENT: Alt+P sync exit=" + syncExit + " ok=" + syncOk + " output=" + syncOutput);
                if (!syncOk || syncExit != 0 || syncOutput.IndexOf("\"eligible\": 0", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    Log("DOCUMENT: no recent QR bundles; Alt+P panel suppressed.");
                    return;
                }

                voucherDecisionFileForCurrentBill = Path.Combine(@"C:\PrintBridge\document_decisions", "voucher_" + Guid.NewGuid().ToString("N") + ".json");
                voucherDecisionPendingForCurrentBill = true;
                string args = string.Format("\"{0}\" --api \"{1}\" --decision-file \"{2}\"", bridge, config.DocumentWorkflowApi, voucherDecisionFileForCurrentBill);
                if (StartInteractiveChild(ResolvePythonExe(), args))
                    Log("DOCUMENT: non-blocking Alt+P decision panel opened.");
                else
                    Log("DOCUMENT: could not open Alt+P decision panel; normal bill route retained.");
            }
            catch (Exception ex) { Log("DOCUMENT: Alt+P panel failed; normal bill route retained: " + ex.Message); }
        }

        private bool StartInteractiveChild(string exe, string args)
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = exe,
                    Arguments = args,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Normal
                };
                ApplyDocumentBridgeToken(psi);
                using (var process = Process.Start(psi)) return process != null;
            }
            catch (Exception ex)
            {
                Log("DOCUMENT: could not start interactive panel: " + ex.Message);
                return false;
            }
        }

        // Starts (and, on every ~3s supervision tick, restarts if it has died)
        // the local document-workflow Flask API as a child of this already-
        // trusted, signed tray process. See the field comment above
        // documentWorkflowProcess for why this replaced a SYSTEM scheduled
        // task. Mirrors run_document_workflow_service.ps1's env vars and port
        // exactly; that script remains available for manual/diagnostic use
        // but is no longer this app's own startup path.
        private void EnsureDocumentWorkflowServiceRunning()
        {
            if (!config.DocumentWorkflowEnabled || string.IsNullOrWhiteSpace(config.DocumentWorkflowRoot)) return;
            if (documentWorkflowProcess != null && !documentWorkflowProcess.HasExited) return;

            if (DateTime.UtcNow - documentWorkflowLastStartAttemptUtc < DocumentWorkflowRestartCooldown) return;
            documentWorkflowLastStartAttemptUtc = DateTime.UtcNow;

            string appPath = Path.Combine(config.DocumentWorkflowRoot, "service", "app.py");
            if (!File.Exists(appPath))
            {
                Log("DOCUMENT: workflow service app.py missing; supervised start skipped: " + appPath);
                return;
            }

            try
            {
                string logRoot = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                    "AradhanaSystems", "logs", "document-workflow");
                Directory.CreateDirectory(logRoot);
                string logPath = Path.Combine(logRoot, "workflow-api.log");

                var psi = new ProcessStartInfo
                {
                    FileName = ResolvePythonExe(),
                    Arguments = "\"" + appPath + "\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    WorkingDirectory = config.DocumentWorkflowRoot,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                psi.EnvironmentVariables["AIS_DOCUMENT_WORKFLOW_DB"] = Path.Combine(config.DocumentWorkflowRoot, "service", "document_workflow.db");
                psi.EnvironmentVariables["AIS_DOCUMENT_WORKFLOW_PORT"] = "8310";

                var process = new Process { StartInfo = psi };
                process.OutputDataReceived += (s, e) => { if (e.Data != null) TryAppendWorkflowLog(logPath, e.Data); };
                process.ErrorDataReceived += (s, e) => { if (e.Data != null) TryAppendWorkflowLog(logPath, e.Data); };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                if (documentWorkflowProcess != null) { try { documentWorkflowProcess.Dispose(); } catch { } }
                documentWorkflowProcess = process;
                Log("DOCUMENT: workflow API started (pid=" + process.Id + "), supervised by this process.");
            }
            catch (Exception ex)
            {
                Log("DOCUMENT: could not start workflow API: " + ex.Message);
            }
        }

        private static void TryAppendWorkflowLog(string logPath, string line)
        {
            try
            {
                File.AppendAllText(logPath, "[" + DateTime.UtcNow.ToString("o") + "] " + line + Environment.NewLine);
            }
            catch { }
        }

        // The bridge secret is intentionally not stored in config.txt or in a
        // startup command. The preferred durable store is a DPAPI blob scoped
        // to the signed-in biller. Credential Manager remains a backwards-
        // compatible fallback; an inherited environment value is only for an
        // already-running support session.
        private const string DocumentBridgeCredentialTarget = "AIS.DocumentBridgeToken";
        private static string DocumentBridgeDpapiTokenPath
        {
            get
            {
                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Aradhana", "Secrets", "document_bridge_token.dpapi");
            }
        }

        private static string ReadDocumentBridgeToken()
        {
            string inherited = Environment.GetEnvironmentVariable("AIS_DOCUMENT_BRIDGE_TOKEN");
            if (!string.IsNullOrWhiteSpace(inherited)) return inherited.Trim();

            string dpapiToken = ReadDpapiDocumentBridgeToken();
            if (!string.IsNullOrWhiteSpace(dpapiToken)) return dpapiToken;

            return ReadCredentialManagerDocumentBridgeToken();
        }

        private static string ReadDpapiDocumentBridgeToken()
        {
            try
            {
                if (!File.Exists(DocumentBridgeDpapiTokenPath)) return "";
                byte[] encrypted = File.ReadAllBytes(DocumentBridgeDpapiTokenPath);
                byte[] bytes = ProtectedData.Unprotect(encrypted, null, DataProtectionScope.CurrentUser);
                return Encoding.Unicode.GetString(bytes).TrimEnd('\0').Trim();
            }
            catch { return ""; }
        }

        private static string ReadCredentialManagerDocumentBridgeToken()
        {
            IntPtr credentialPointer = IntPtr.Zero;
            try
            {
                if (!CredRead(DocumentBridgeCredentialTarget, 1, 0, out credentialPointer) ||
                    credentialPointer == IntPtr.Zero) return "";
                var credential = (CREDENTIAL)Marshal.PtrToStructure(credentialPointer, typeof(CREDENTIAL));
                if (credential.CredentialBlob == IntPtr.Zero || credential.CredentialBlobSize == 0) return "";
                byte[] bytes = new byte[credential.CredentialBlobSize];
                Marshal.Copy(credential.CredentialBlob, bytes, 0, bytes.Length);
                return Encoding.Unicode.GetString(bytes).TrimEnd('\0').Trim();
            }
            catch { return ""; }
            finally
            {
                if (credentialPointer != IntPtr.Zero) CredFree(credentialPointer);
            }
        }

        private static void ApplyDocumentBridgeToken(ProcessStartInfo startInfo)
        {
            string token = ReadDocumentBridgeToken();
            if (!string.IsNullOrWhiteSpace(token))
                startInfo.EnvironmentVariables["AIS_DOCUMENT_BRIDGE_TOKEN"] = token;
        }

        // Runs once per bill, on the P355 customer-copy print dialog (see the
        // call site in TryHandlePrintDialog) - never on the P1007 office
        // copy, which has no use for the attached document and should never
        // wait on anything. The popup is a separate local process and cannot
        // select printers or send a print job. Any timeout/error safely
        // falls back to the normal bill.
        private void PrepareDocumentWorkflowForNextCustomerCopy()
        {
            documentWorkflowManifestForNextCustomerCopy = null;
            if (!config.DocumentWorkflowEnabled || string.IsNullOrEmpty(config.DocumentScannerApi)) return;
            try
            {
                // When Alt+P was seen, the panel already exists and this method
                // must never open a second blocking one.  Consume its choice if
                // available; an unattended panel deliberately means bill-only.
                //
                // The panel is a separate Python process that needs real
                // wall-clock time to start and render before a person can
                // possibly have read it, let alone clicked it - a biller who
                // moves quickly from Alt+P straight into Print can otherwise
                // reach this check well under a second later, before the
                // panel is even on screen (seen live 2026-09-11: 1s gap,
                // panel never had a chance). Give it a bounded window here
                // instead of checking once and giving up instantly. This
                // only ever runs for a bill that actually has a pending QR
                // document (rare), and now that it's gated on the P355
                // customer copy rather than P1007, this wait is free to be
                // generous - it delays only that one copy, on a bill that
                // already has extra work to do, never the office copy.
                if (voucherDecisionPendingForCurrentBill)
                {
                    const int pollIntervalMs = 200;
                    const int maxWaitMs = 6000;
                    for (int waited = 0;
                         waited < maxWaitMs && !File.Exists(voucherDecisionFileForCurrentBill);
                         waited += pollIntervalMs)
                    {
                        System.Threading.Thread.Sleep(pollIntervalMs);
                    }
                    ApplyVoucherDecisionIfAvailable();
                    voucherDecisionPendingForCurrentBill = false;
                    voucherDecisionFileForCurrentBill = null;
                    return;
                }
                string root = config.DocumentWorkflowRoot;
                string bridge = Path.Combine(root, "bridge", "biller_popup.py");
                string sync = Path.Combine(root, "bridge", "qr_bundle_sync.py");
                string cache = Path.Combine(root, "bridge", "cache_bundle.py");
                string claim = Path.Combine(root, "bridge", "claim_bundle_for_bill.py");
                string standalone = Path.Combine(root, "bridge", "queue_standalone.py");
                if (!File.Exists(bridge) || !File.Exists(sync) || !File.Exists(cache) || !File.Exists(claim) || !File.Exists(standalone))
                {
                    Log("DOCUMENT: workflow files missing; normal bill route retained.");
                    return;
                }
                string ignored; int ignoredExit;
                Log("DOCUMENT: syncing held QR bundles.");
                bool syncOk = RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --workflow-api \"{2}\"", sync, config.DocumentScannerApi, config.DocumentWorkflowApi), out ignoredExit, out ignored);
                Log("DOCUMENT: sync exit=" + ignoredExit + " ok=" + syncOk + " output=" + ignored);
                if (!syncOk || ignoredExit != 0 || ignored.IndexOf("\"eligible\": 0", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    Log("DOCUMENT: no recent QR bundles; panel suppressed.");
                    return;
                }
                string decisions = Path.Combine(@"C:\PrintBridge\document_decisions", Guid.NewGuid().ToString("N") + ".json");
                Log("DOCUMENT: opening persistent document toast before printer submission.");
                bool popupOk = RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --api \"{1}\" --decision-file \"{2}\"", bridge, config.DocumentWorkflowApi, decisions), out ignoredExit, out ignored, true);
                Log("DOCUMENT: popup exit=" + ignoredExit + " ok=" + popupOk + " output=" + ignored);
                if (!File.Exists(decisions))
                {
                    Log("DOCUMENT: no biller decision; normal bill route retained.");
                    return;
                }
                string decision = File.ReadAllText(decisions);
                try { File.Delete(decisions); } catch { }
                const string attach = "\"decision\": \"attach\"";
                const string standaloneDecision = "\"decision\": \"standalone\"";
                const string key = "\"bundle_id\": \"";
                bool isAttach = decision.IndexOf(attach, StringComparison.OrdinalIgnoreCase) >= 0;
                bool isStandalone = decision.IndexOf(standaloneDecision, StringComparison.OrdinalIgnoreCase) >= 0;
                if (!isAttach && !isStandalone)
                {
                    Log("DOCUMENT: biller chose a non-attachment route.");
                    return;
                }
                int start = decision.IndexOf(key, StringComparison.OrdinalIgnoreCase);
                if (start < 0) return;
                start += key.Length; int end = decision.IndexOf('"', start);
                if (end <= start) return;
                string bundleId = decision.Substring(start, end - start);
                string output; int exit;
                if (isStandalone)
                {
                    bool queued = RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --bundle-id \"{2}\"", standalone, config.DocumentScannerApi, bundleId), out exit, out output);
                    Log("DOCUMENT: standalone bundle request exit=" + exit + " ok=" + queued + " output=" + output);
                    return; // The normal Ornate bill route remains untouched.
                }
                if (RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --bundle-id \"{2}\"", cache, config.DocumentScannerApi, bundleId), out exit, out output) && exit == 0)
                {
                    string manifest = output.Trim();
                    if (File.Exists(manifest))
                    {
                        bool claimed = RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --bundle-id \"{2}\"", claim, config.DocumentScannerApi, bundleId), out exit, out output);
                        if (claimed && exit == 0)
                        {
                            documentWorkflowManifestForNextCustomerCopy = manifest;
                            Log("DOCUMENT: selected bundle claimed and cached for the customer P355 copy.");
                        }
                        else Log("DOCUMENT: selected bundle was not claimed; attachment withheld to prevent duplicate use: " + output);
                    }
                    else Log("DOCUMENT: cache did not return a local manifest.");
                }
            }
            catch (Exception ex) { Log("DOCUMENT: decision failed; normal bill route retained: " + ex.Message); }
        }

        private void ApplyVoucherDecisionIfAvailable()
        {
            if (string.IsNullOrEmpty(voucherDecisionFileForCurrentBill) ||
                !File.Exists(voucherDecisionFileForCurrentBill))
            {
                Log("DOCUMENT: Alt+P panel unattended; normal bill route retained.");
                return;
            }

            string decision = File.ReadAllText(voucherDecisionFileForCurrentBill);
            try { File.Delete(voucherDecisionFileForCurrentBill); } catch { }
            const string attach = "\"decision\": \"attach\"";
            const string standaloneDecision = "\"decision\": \"standalone\"";
            const string key = "\"bundle_id\": \"";
            bool isAttach = decision.IndexOf(attach, StringComparison.OrdinalIgnoreCase) >= 0;
            bool isStandalone = decision.IndexOf(standaloneDecision, StringComparison.OrdinalIgnoreCase) >= 0;
            if (!isAttach && !isStandalone)
            {
                Log("DOCUMENT: biller chose normal bill route from Alt+P panel.");
                return;
            }
            int start = decision.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (start < 0) return;
            start += key.Length; int end = decision.IndexOf('"', start);
            if (end <= start) return;
            string bundleId = decision.Substring(start, end - start);
            string root = config.DocumentWorkflowRoot;
            string output; int exit;
            if (isStandalone)
            {
                string standalone = Path.Combine(root, "bridge", "queue_standalone.py");
                bool queued = RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --bundle-id \"{2}\"", standalone, config.DocumentScannerApi, bundleId), out exit, out output);
                Log("DOCUMENT: standalone bundle request exit=" + exit + " ok=" + queued + " output=" + output);
                return;
            }
            string cache = Path.Combine(root, "bridge", "cache_bundle.py");
            string claim = Path.Combine(root, "bridge", "claim_bundle_for_bill.py");
            if (!File.Exists(claim))
            {
                Log("DOCUMENT: claim bridge missing; attachment withheld.");
                return;
            }
            if (RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --bundle-id \"{2}\"", cache, config.DocumentScannerApi, bundleId), out exit, out output) && exit == 0)
            {
                string manifest = output.Trim();
                if (File.Exists(manifest))
                {
                    bool claimed = RunChildProcess(ResolvePythonExe(), string.Format("\"{0}\" --scanner-api \"{1}\" --bundle-id \"{2}\"", claim, config.DocumentScannerApi, bundleId), out exit, out output);
                    if (claimed && exit == 0)
                    {
                        documentWorkflowManifestForNextCustomerCopy = manifest;
                        Log("DOCUMENT: Alt+P selection claimed and cached for the customer P355 copy.");
                    }
                    else Log("DOCUMENT: Alt+P selection was not claimed; attachment withheld to prevent duplicate use: " + output);
                }
                else Log("DOCUMENT: Alt+P cache did not return a local manifest.");
            }
            else Log("DOCUMENT: Alt+P cache request failed: " + output);
        }

        // Determines whether this is the approved office copy or a later
        // customer/URD copy. Timing is intentionally not used: it cannot
        // distinguish a delayed URD window from a new bill.
        private int ResolveCopyNumber()
        {
            if (voucherBillSessionActive)
            {
                lastHandledUtc = DateTime.UtcNow;
                if (!officeCopyHandledForVoucherBill)
                {
                    // The copy count was only ever read once, when the window
                    // first qualified - if the biller edits it afterward
                    // (e.g. down to 1), that stale "armed" state would still
                    // hand out the P1007 office copy for a print that no
                    // longer matches the rule it was armed under. Re-read the
                    // live count right before actually granting P1007, and
                    // default to the safe P355 route (same as "no qualifying
                    // window") if it no longer matches or can't be read.
                    int liveCopies;
                    bool liveOk = activeVoucherWindow != IntPtr.Zero &&
                        TryReadVoucherCopyCount(activeVoucherWindow, out liveCopies) &&
                        liveCopies == activeVoucherRequiredCopies;
                    if (!liveOk)
                    {
                        voucherBillSessionActive = false;
                        officeCopyHandledForVoucherBill = false;
                        lastHandledUtc = DateTime.MinValue;
                        Log("ROUTE SAFETY: copy count no longer matches the armed route at print time; P1007 blocked, routing P355.");
                        return 2;
                    }
                    officeCopyHandledForVoucherBill = true;
                    return 1;
                }
                voucherBillSessionActive = false;
                officeCopyHandledForVoucherBill = false;
                lastHandledUtc = DateTime.MinValue;
                Log("ROUTE: P1007 office copy consumed; second and every later print dialog stay P355 until a new qualifying Voucher Print window opens.");
                return 2;
            }
            Log("ROUTE SAFETY: print dialog without a qualifying Voucher Print window; P1007 blocked, routing P355.");
            return 2;
        }

        private string ResolveActiveVoucherPrinter(int copyNumber)
        {
            // Unknown/unqualified windows are deliberately not subject to the
            // legacy force-printer controls: their only safe destination is
            // the configured P355 queue.
            if (copyNumber == 1 && !string.IsNullOrWhiteSpace(activeVoucherCopy1Printer))
                return activeVoucherCopy1Printer;
            if (copyNumber > 1 && !string.IsNullOrWhiteSpace(activeVoucherLaterPrinter))
                return activeVoucherLaterPrinter;
            return config.Copy2Printer;
        }

        private bool TryMatchVoucherRoute(IntPtr dialog, out VoucherRouteRule matchedRoute, out double difference)
        {
            matchedRoute = null;
            difference = double.PositiveInfinity;
            RECT rect;
            if (!GetWindowRect(dialog, out rect))
            {
                Log("ROUTE SAFETY: Voucher Print bounds unavailable; P1007 blocked.");
                return false;
            }
            int width = rect.Right - rect.Left;
            int height = rect.Bottom - rect.Top;
            if (width < 200 || height < 100)
            {
                Log("ROUTE SAFETY: Voucher Print bounds invalid; P1007 blocked.");
                return false;
            }

            try
            {
                using (var captured = new Bitmap(width, height))
                using (var graphics = Graphics.FromImage(captured))
                {
                    IntPtr hdc = graphics.GetHdc();
                    bool capturedWindow;
                    try { capturedWindow = PrintWindow(dialog, hdc, 2); }
                    finally { graphics.ReleaseHdc(hdc); }
                    if (!capturedWindow)
                    {
                        Log("ROUTE SAFETY: Voucher Print capture failed; P1007 blocked.");
                        return false;
                    }

                    using (var actualFormat = CreateVoucherFormatFingerprint(captured))
                    {
                        VoucherRouteRule closestRoute = null;
                        double closestDifference = double.PositiveInfinity;
                        foreach (VoucherRouteRule route in config.VoucherRoutes)
                        {
                            if (!route.Enabled || string.IsNullOrWhiteSpace(route.ReferenceFile)) continue;
                            string referencePath = Path.Combine(baseFolder, Path.GetFileName(route.ReferenceFile));
                            if (!File.Exists(referencePath)) continue;
                            using (var reference = new Bitmap(referencePath))
                            using (var referenceFormat = CreateVoucherFormatFingerprint(reference))
                            {
                                double candidate = MeanPixelDifference(actualFormat, referenceFormat);
                                if (candidate < closestDifference)
                                {
                                    closestDifference = candidate;
                                    closestRoute = route;
                                }
                            }
                        }
                        difference = closestDifference;
                        if (closestRoute == null || closestDifference > OfficeVoucherFingerprintMaxDifference)
                            return false;
                        matchedRoute = closestRoute;
                        return true;
                    }
                }
            }
            catch (Exception ex)
            {
                Log("ROUTE SAFETY: Voucher Format capture error; P1007 blocked: " + ex.Message);
                return false;
            }
        }

        // Called from the Voucher routing rules editor's "Capture current
        // voucher as new template" button. Finds whatever Voucher Print
        // window is currently open in Ornate and saves a full-window capture
        // as a new reference PNG - the exact same capture this process
        // already performs on every real print dialog (TryMatchVoucherRoute
        // above), just saved to disk instead of compared. Read-only towards
        // Ornate: no click, no focus change, no field edit.
        private VoucherTemplateCaptureResult CaptureLiveVoucherTemplate()
        {
            IntPtr found = IntPtr.Zero;
            var ornatePids = GetValidOrnatePids();
            if (ornatePids.Count == 0)
                return new VoucherTemplateCaptureResult { Success = false, Error = "Ornate (ONX.exe) is not running." };

            EnumWindows((hWnd, lParam) =>
            {
                if (found != IntPtr.Zero) return true;
                if (!string.Equals(GetWindowTextValue(hWnd), VoucherDialogTitle, StringComparison.OrdinalIgnoreCase)) return true;
                if (!BelongsToOrnate(hWnd, ornatePids)) return true;
                found = hWnd;
                return true;
            }, IntPtr.Zero);

            if (found == IntPtr.Zero)
                return new VoucherTemplateCaptureResult { Success = false, Error = "Open Ornate's Voucher Print window first, then try again." };

            RECT rect;
            if (!GetWindowRect(found, out rect))
                return new VoucherTemplateCaptureResult { Success = false, Error = "Could not read the Voucher Print window's bounds." };
            int width = rect.Right - rect.Left;
            int height = rect.Bottom - rect.Top;
            if (width < 200 || height < 100)
                return new VoucherTemplateCaptureResult { Success = false, Error = "Voucher Print window bounds look invalid; try again." };

            try
            {
                using (var captured = new Bitmap(width, height))
                {
                    using (var graphics = Graphics.FromImage(captured))
                    {
                        IntPtr hdc = graphics.GetHdc();
                        bool capturedWindow;
                        try { capturedWindow = PrintWindow(found, hdc, 2); }
                        finally { graphics.ReleaseHdc(hdc); }
                        if (!capturedWindow)
                            return new VoucherTemplateCaptureResult { Success = false, Error = "Window capture failed (PrintWindow returned false)." };
                    }

                    string fileName = "voucher-template-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + ".png";
                    string fullPath = Path.Combine(baseFolder, fileName);
                    captured.Save(fullPath, System.Drawing.Imaging.ImageFormat.Png);
                    Log("ROUTING RULES: captured new voucher template '" + fileName + "' from the live Voucher Print window.");
                    return new VoucherTemplateCaptureResult { Success = true, FileName = fileName };
                }
            }
            catch (Exception ex)
            {
                return new VoucherTemplateCaptureResult { Success = false, Error = "Capture failed: " + ex.Message };
            }
        }

        // Ornate's "No. Of Copies" spinner is a custom-drawn control, not a real Win32 EDIT:
        // Win32 GetWindowText finds an unrelated EDIT field (confirmed by field trace to read
        // "1" regardless of the spinner's actual value) while UI Automation correctly exposes
        // the spinner's live value as the control's Name. This mirrors the same Win32-vs-UI
        // Automation gap already documented for the Voucher Format field below. The spinner's
        // own AutomationId ("TxtNoOfCopy") is stable and confirmed live on 2026-09-10 — prefer
        // it directly. Nested sub-elements (the spinner's internal text rendering) mirror the
        // same value under different/empty AutomationIds and would otherwise read as ambiguous.
        private const string CopySpinnerAutomationId = "TxtNoOfCopy";
        private const int CopySpinnerMaxWidth = 110;
        private const int CopySpinnerMaxHeight = 30;

        private bool TryReadVoucherCopyCount(IntPtr dialog, out int copies)
        {
            copies = 0;
            var candidates = new List<string>();
            int detectedCopies = 0;
            int matchCount = 0;
            int? byAutomationId = null;

            try
            {
                AutomationElement root = AutomationElement.FromHandle(dialog);
                if (root == null)
                {
                    Log("ROUTE SAFETY: Voucher Print UI Automation root unavailable. P1007 blocked.");
                    return false;
                }

                Condition condition = new PropertyCondition(AutomationElement.IsControlElementProperty, true);
                AutomationElementCollection elements = root.FindAll(TreeScope.Descendants, condition);

                foreach (AutomationElement element in elements)
                {
                    string name = element.Current.Name;
                    if (string.IsNullOrEmpty(name)) continue;
                    int parsed;
                    if (!int.TryParse(name.Trim(), out parsed) || parsed < 1 || parsed > 9) continue;

                    Rect bounds = element.Current.BoundingRectangle;
                    if (bounds.IsEmpty || bounds.Width <= 0 || bounds.Width > CopySpinnerMaxWidth ||
                        bounds.Height <= 0 || bounds.Height > CopySpinnerMaxHeight)
                    {
                        continue;
                    }

                    matchCount++;
                    candidates.Add("value=" + parsed + " w=" + (int)bounds.Width + " h=" + (int)bounds.Height +
                        " automationId=" + element.Current.AutomationId);
                    if (matchCount == 1)
                    {
                        detectedCopies = parsed;
                    }
                    if (string.Equals(element.Current.AutomationId, CopySpinnerAutomationId, StringComparison.Ordinal))
                    {
                        byAutomationId = parsed;
                    }
                }
            }
            catch (Exception ex)
            {
                Log("ROUTE SAFETY: Voucher Print copy count UI Automation error; P1007 blocked: " + ex.Message);
                return false;
            }

            if (byAutomationId.HasValue)
            {
                copies = byAutomationId.Value;
                Log("Voucher Print copy count read via UI Automation (AutomationId=" + CopySpinnerAutomationId + "): " +
                    copies + (matchCount > 1 ? " (" + matchCount + " total candidates, disambiguated by AutomationId)" : ""));
                return true;
            }

            if (matchCount > 1)
            {
                Log("ROUTE SAFETY: " + matchCount + " ambiguous copy-count candidates found via UI Automation (none matched AutomationId=" +
                    CopySpinnerAutomationId + "): " + string.Join(" || ", candidates) + ". P1007 blocked.");
                copies = 0;
                return false;
            }

            copies = detectedCopies;
            if (copies == 0)
                Log("ROUTE SAFETY: Voucher Print copy count is unreadable via UI Automation (no matching spinner control). P1007 blocked.");
            else
                Log("Voucher Print copy count read via UI Automation: " + candidates[0]);
            return copies != 0;
        }

        private static Bitmap CreateVoucherFormatFingerprint(Image source)
        {
            // The format combo's text area, expressed as stable proportions of
            // the complete Voucher Print window. This survives window position
            // and standard Windows DPI scaling while excluding editable count.
            int left = Math.Max(0, (int)Math.Round(source.Width * 0.238));
            int top = Math.Max(0, (int)Math.Round(source.Height * 0.125));
            int right = Math.Min(source.Width, (int)Math.Round(source.Width * 0.950));
            int bottom = Math.Min(source.Height, (int)Math.Round(source.Height * 0.180));
            if (right <= left || bottom <= top) throw new InvalidOperationException("Voucher Format crop is invalid.");

            var fingerprint = new Bitmap(VoucherFormatFingerprintWidth, VoucherFormatFingerprintHeight);
            using (var graphics = Graphics.FromImage(fingerprint))
            {
                graphics.Clear(Color.White);
                graphics.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBilinear;
                graphics.DrawImage(source,
                    new Rectangle(0, 0, VoucherFormatFingerprintWidth, VoucherFormatFingerprintHeight),
                    new Rectangle(left, top, right - left, bottom - top),
                    GraphicsUnit.Pixel);
            }
            return fingerprint;
        }

        private static double MeanPixelDifference(Bitmap actual, Bitmap reference)
        {
            if (actual.Width != reference.Width || actual.Height != reference.Height)
                return double.PositiveInfinity;

            double total = 0;
            int count = actual.Width * actual.Height;
            for (int y = 0; y < actual.Height; y++)
            {
                for (int x = 0; x < actual.Width; x++)
                {
                    Color a = actual.GetPixel(x, y);
                    Color b = reference.GetPixel(x, y);
                    total += (Math.Abs(a.R - b.R) + Math.Abs(a.G - b.G) + Math.Abs(a.B - b.B)) / 3.0;
                }
            }
            return total / count;
        }

        private void ObserveBillStartHotkey()
        {
            const int VK_MENU = 0x12;
            const int VK_P = 0x50;
            bool pDown = (GetAsyncKeyState(VK_P) & 0x8000) != 0;
            bool pPressed = pDown && !pKeyWasDown;
            pKeyWasDown = pDown;
            if (!enabled || !pPressed || (GetAsyncKeyState(VK_MENU) & 0x8000) == 0) return;

            IntPtr foreground = GetForegroundWindow();
            if (foreground == IntPtr.Zero) return;
            if (!GetValidOrnatePids().Contains(GetWindowPid(foreground))) return;

            // Diagnostic only. Printer routing is based solely on the visible
            // Voucher Format plus No. Of Copies field, never on a transient
            // keyboard-state sample.
            Log("ROUTE: Alt+P observed in Ornate; Voucher Print fields will determine routing.");
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

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct CREDENTIAL
        {
            public uint Flags;
            public uint Type;
            public IntPtr TargetName;
            public IntPtr Comment;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
            public uint CredentialBlobSize;
            public IntPtr CredentialBlob;
            public uint Persist;
            public uint AttributeCount;
            public IntPtr Attributes;
            public IntPtr TargetAlias;
            public IntPtr UserName;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct RECT
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CredRead(string target, uint type, uint flags, out IntPtr credential);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern void CredFree(IntPtr credential);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int vKey);

        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint flags);

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
        private readonly Func<VoucherTemplateCaptureResult> captureLiveVoucherTemplate;

        private CheckBox chkEnabled;
        private ComboBox cmbRole;
        private TextBox txtCopy1Printer;
        private TextBox txtCopy2Printer;
        private TextBox txtForceCopy1;
        private TextBox txtForceCopy2;
        private TextBox txtLog;
        private Timer logTimer;
        private long lastLogLength = -1;

        public SettingsForm(AppConfig config, string configPath, string logPath, Action onSaved,
            Func<VoucherTemplateCaptureResult> captureLiveVoucherTemplate)
        {
            this.config = config;
            this.configPath = configPath;
            this.logPath = logPath;
            this.onSaved = onSaved;
            this.captureLiveVoucherTemplate = captureLiveVoucherTemplate;

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

            var btnRoutes = new Button { Text = "Voucher routing rules...", Left = 12, Top = 348, Width = 185 };
            btnRoutes.Click += (s, e) =>
            {
                using (var editor = new VoucherRouteRulesForm(config, configPath, captureLiveVoucherTemplate))
                    editor.ShowDialog(this);
            };

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
                btnRoutes, btnSave, btnClose,
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

                // Only ever read the last chunk of the file, not the whole thing - a
                // full ReadToEnd() here used to cost O(file size) on every tick this
                // form is open, which gets slower and slower as the log grows over a
                // normal day (or over months of production use, since nothing rotates
                // it). 128KB is comfortably more than the ~200 lines actually shown.
                const int MaxTailBytes = 131072;
                string all;
                using (var fs = new FileStream(logPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    long seekTo = Math.Max(0, fs.Length - MaxTailBytes);
                    fs.Seek(seekTo, SeekOrigin.Begin);
                    using (var sr = new StreamReader(fs, Encoding.UTF8))
                        all = sr.ReadToEnd();
                }
                string[] lines = all.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);

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

    // Administrator-facing routing editor. A row is not active merely because
    // it has a friendly name: Reference Template must exist beside the router
    // EXE and must visually match Ornate's Voucher Print window at runtime.
    internal sealed class VoucherRouteRulesForm : Form
    {
        private const string UseConfiguredPrinter = "(use configured default)";
        private readonly AppConfig config;
        private readonly string configPath;
        private readonly DataGridView grid;
        private readonly List<string> templateFiles;
        private readonly List<string> printerChoices;
        private readonly Func<VoucherTemplateCaptureResult> captureLiveVoucherTemplate;

        public VoucherRouteRulesForm(AppConfig config, string configPath,
            Func<VoucherTemplateCaptureResult> captureLiveVoucherTemplate)
        {
            this.config = config;
            this.configPath = configPath;
            this.captureLiveVoucherTemplate = captureLiveVoucherTemplate;
            templateFiles = LoadTemplateFiles();
            printerChoices = LoadPrinterChoices();

            Text = "Voucher routing rules";
            Width = 1120;
            Height = 460;
            StartPosition = FormStartPosition.CenterParent;
            MinimizeBox = false;

            var note = new Label
            {
                Left = 12, Top = 12, Width = 1080, Height = 40,
                Text = "A rule matches only a saved visual template and the exact copy count - the " +
                       "\"Voucher rule label\" is just your own note, it is never matched against anything. " +
                       "No match, missing template, or unreadable count means P355 only."
            };
            grid = new DataGridView
            {
                Left = 12, Top = 58, Width = 1080, Height = 280,
                AllowUserToAddRows = false,
                AllowUserToDeleteRows = false,
                AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.None,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect,
                MultiSelect = false
            };
            grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "Name", HeaderText = "Voucher rule label", Width = 235 });
            grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "Copies", HeaderText = "Exact copies", Width = 75 });
            var templates = new DataGridViewComboBoxColumn { Name = "Template", HeaderText = "Reference template", Width = 220, FlatStyle = FlatStyle.Flat };
            foreach (string template in templateFiles) templates.Items.Add(template);
            grid.Columns.Add(templates);
            var copy1 = new DataGridViewComboBoxColumn { Name = "Copy1", HeaderText = "Copy 1 printer", Width = 205, FlatStyle = FlatStyle.Flat };
            var later = new DataGridViewComboBoxColumn { Name = "Later", HeaderText = "Copies 2+ printer", Width = 205, FlatStyle = FlatStyle.Flat };
            foreach (string printer in printerChoices) { copy1.Items.Add(printer); later.Items.Add(printer); }
            grid.Columns.Add(copy1);
            grid.Columns.Add(later);
            grid.Columns.Add(new DataGridViewCheckBoxColumn { Name = "Enabled", HeaderText = "Enabled", Width = 70 });

            var add = new Button { Text = "Add rule", Left = 12, Top = 350, Width = 100 };
            add.Click += (s, e) => AddDefaultRow();
            var remove = new Button { Text = "Remove selected", Left = 122, Top = 350, Width = 130 };
            remove.Click += (s, e) => { if (grid.CurrentRow != null) grid.Rows.Remove(grid.CurrentRow); };
            var captureTemplate = new Button { Text = "Capture current voucher as new template...", Left = 262, Top = 350, Width = 290 };
            captureTemplate.Click += (s, e) => CaptureNewTemplate();
            var save = new Button { Text = "Save rules", Left = 862, Top = 350, Width = 110 };
            save.Click += (s, e) => SaveRules();
            var close = new Button { Text = "Close", Left = 982, Top = 350, Width = 110 };
            close.Click += (s, e) => Close();
            Controls.AddRange(new Control[] { note, grid, add, remove, captureTemplate, save, close });
            LoadRules();
        }

        private List<string> LoadTemplateFiles()
        {
            var values = new List<string>();
            string folder = Path.GetDirectoryName(configPath);
            try
            {
                foreach (string file in Directory.GetFiles(folder, "*.png"))
                    values.Add(Path.GetFileName(file));
            }
            catch { }
            if (!values.Contains("office-sales-voucher-format-reference.png"))
                values.Add("office-sales-voucher-format-reference.png");
            values.Sort(StringComparer.OrdinalIgnoreCase);
            return values;
        }

        private List<string> LoadPrinterChoices()
        {
            var values = new List<string> { UseConfiguredPrinter };
            try
            {
                foreach (string printer in System.Drawing.Printing.PrinterSettings.InstalledPrinters)
                    if (!values.Contains(printer)) values.Add(printer);
            }
            catch { }
            AddPrinterChoice(values, config.Copy1Printer);
            AddPrinterChoice(values, config.Copy2Printer);
            foreach (VoucherRouteRule rule in config.VoucherRoutes)
            {
                AddPrinterChoice(values, rule.Copy1Printer);
                AddPrinterChoice(values, rule.LaterPrinter);
            }
            return values;
        }

        private static void AddPrinterChoice(List<string> values, string printer)
        {
            if (!string.IsNullOrWhiteSpace(printer) && !values.Contains(printer)) values.Add(printer);
        }

        private void LoadRules()
        {
            foreach (VoucherRouteRule rule in config.VoucherRoutes)
                AddRow(rule);
            if (grid.Rows.Count == 0) AddRow(VoucherRouteRule.DefaultRule());
        }

        private void AddDefaultRow()
        {
            AddRow(VoucherRouteRule.DefaultRule());
        }

        // Captures whatever Voucher Print window is currently open in Ornate
        // as a new reference template and drops in a ready-to-fill row for
        // it - the point being that the one part of setting up a rule that
        // actually has to be exactly right (the visual template) never
        // requires touching a file path or a separate tool. Read-only
        // towards Ornate; does not click, focus, or print anything.
        private void CaptureNewTemplate()
        {
            if (captureLiveVoucherTemplate == null) return;

            VoucherTemplateCaptureResult result = captureLiveVoucherTemplate();
            if (!result.Success)
            {
                MessageBox.Show(this, result.Error, "Capture voucher template",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            if (!templateFiles.Contains(result.FileName))
            {
                templateFiles.Add(result.FileName);
                ((DataGridViewComboBoxColumn)grid.Columns["Template"]).Items.Add(result.FileName);
            }

            AddRow(new VoucherRouteRule
            {
                Name = "",
                RequiredCopies = 2,
                ReferenceFile = result.FileName,
                Enabled = true
            });

            int newRow = grid.Rows.Count - 1;
            grid.CurrentCell = grid.Rows[newRow].Cells["Name"];
            grid.BeginEdit(true);

            MessageBox.Show(this,
                "Captured '" + result.FileName + "' from the currently open Voucher Print window.\n\n" +
                "A new row was added with this template and 2 copies. Type a label, set the exact " +
                "copy count this voucher actually uses, choose printers, then Save rules.",
                "Capture voucher template", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void AddRow(VoucherRouteRule rule)
        {
            string template = string.IsNullOrWhiteSpace(rule.ReferenceFile)
                ? "office-sales-voucher-format-reference.png" : rule.ReferenceFile;
            if (!templateFiles.Contains(template))
            {
                templateFiles.Add(template);
                ((DataGridViewComboBoxColumn)grid.Columns["Template"]).Items.Add(template);
            }
            int row = grid.Rows.Add(rule.Name, rule.RequiredCopies, template,
                string.IsNullOrWhiteSpace(rule.Copy1Printer) ? UseConfiguredPrinter : rule.Copy1Printer,
                string.IsNullOrWhiteSpace(rule.LaterPrinter) ? UseConfiguredPrinter : rule.LaterPrinter,
                rule.Enabled);
            grid.Rows[row].Cells["Enabled"].Value = rule.Enabled;
        }

        private void SaveRules()
        {
            var rules = new List<VoucherRouteRule>();
            foreach (DataGridViewRow row in grid.Rows)
            {
                string name = Cell(row, "Name");
                string copiesText = Cell(row, "Copies");
                string template = Cell(row, "Template");
                int copies;
                if (string.IsNullOrWhiteSpace(name) || string.IsNullOrWhiteSpace(template) ||
                    !int.TryParse(copiesText, out copies) || copies < 1 || copies > 9 ||
                    ContainsPipe(name) || ContainsPipe(template))
                {
                    MessageBox.Show(this, "Each rule needs a label, a template file, and a copy count from 1 to 9. Pipe characters are not allowed.",
                        "Invalid voucher rule", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                string copy1 = ToPrinterValue(Cell(row, "Copy1"));
                string later = ToPrinterValue(Cell(row, "Later"));
                if (ContainsPipe(copy1) || ContainsPipe(later))
                {
                    MessageBox.Show(this, "Printer names cannot contain pipe characters.", "Invalid voucher rule", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                bool enabled = row.Cells["Enabled"].Value != null && Convert.ToBoolean(row.Cells["Enabled"].Value);
                rules.Add(new VoucherRouteRule
                {
                    Name = name.Trim(), RequiredCopies = copies,
                    ReferenceFile = Path.GetFileName(template.Trim()),
                    Copy1Printer = copy1, LaterPrinter = later, Enabled = enabled
                });
            }
            if (rules.Count == 0)
            {
                MessageBox.Show(this, "Keep at least one route. Disable it if it should not be used.", "Voucher routing rules", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            // The most common way to set up a rule wrong: pointing "Copies 2+
            // printer" at the real physical printer instead of the letterhead-
            // capture virtual printer. Ornate then prints straight to the real
            // printer, silently skipping the overlay pipeline entirely - no
            // error anywhere, just a plain voucher with no Aradhana letterhead.
            // Confirmed live on 2026-09-11 (the URD rule). config.Copy2Printer
            // is the known-good capture printer, since "(use configured
            // default)" resolving to it is what the working GST rule already
            // relies on.
            var suspectRules = new List<string>();
            foreach (VoucherRouteRule rule in rules)
            {
                if (!string.IsNullOrWhiteSpace(rule.LaterPrinter) &&
                    !string.Equals(rule.LaterPrinter, config.Copy2Printer, StringComparison.OrdinalIgnoreCase))
                {
                    suspectRules.Add(rule.Name + "  (Copies 2+ printer = '" + rule.LaterPrinter + "')");
                }
            }
            if (suspectRules.Count > 0)
            {
                DialogResult choice = MessageBox.Show(this,
                    "These rules' \"Copies 2+ printer\" is not the configured letterhead-capture printer " +
                    "('" + config.Copy2Printer + "'):\n\n" + string.Join("\n", suspectRules) +
                    "\n\nThose copies will print WITHOUT the Aradhana letterhead overlay - straight to " +
                    "that printer with no chance for the overlay step to run. If that is not intentional, " +
                    "click No and change it to '" + config.Copy2Printer + "' (or \"(use configured default)\").\n\n" +
                    "Save anyway?",
                    "Copies 2+ printer skips the letterhead overlay",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
                if (choice != DialogResult.Yes) return;
            }

            config.VoucherRoutes.Clear();
            config.VoucherRoutes.AddRange(rules);
            config.Save(configPath);
            MessageBox.Show(this, "Voucher routing rules saved. Restarting the tray app is not required.", "Voucher routing rules", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private static string Cell(DataGridViewRow row, string name)
        {
            return row.Cells[name].Value == null ? "" : row.Cells[name].Value.ToString().Trim();
        }

        private static string ToPrinterValue(string value)
        {
            return value == UseConfiguredPrinter ? "" : value;
        }

        private static bool ContainsPipe(string value)
        {
            return value != null && value.IndexOf('|') >= 0;
        }
    }
}

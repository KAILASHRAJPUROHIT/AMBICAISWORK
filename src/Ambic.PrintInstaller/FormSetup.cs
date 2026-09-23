using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.IO.Compression;
using System.Text.Json;
using Ambic.Print.Storage.Database;
using Ambic.Print.Storage.Repositories;
using Ambic.PrintAdapters.Ornate;
using Ambic.PrintCore.Config;

namespace Ambic.PrintInstaller;

public partial class FormSetup : Form
{
    private int _currentStep = 0; // 0: Welcome, 1: Options, 2: Progress, 3: Complete

    private Panel _pnlSidebar = null!;
    private Panel _pnlContent = null!;
    private Panel _pnlFooter = null!;
    private Button _btnBack = null!;
    private Button _btnNext = null!;
    private Button _btnCancel = null!;

    // Step 1 controls
    private TextBox _txtInstallDir = null!;
    private CheckBox _chkDesktopShortcut = null!;
    private CheckBox _chkStartMenuShortcut = null!;
    private CheckBox _chkMigrate = null!;
    private CheckBox _chkService = null!;
    private CheckBox _chkWin11Fix = null!;
    private CheckBox _chkFirewall = null!;
    private CheckBox _chkAutoStart = null!;

    // Step 2 (Progress) controls
    private ProgressBar _progressBar = null!;
    private Label _lblProgressStatus = null!;
    private TextBox _txtProgressLog = null!;

    // Step 3 (Complete) controls
    private CheckBox _chkLaunchConsole = null!;

    private readonly string _defaultInstallDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
        "AMBIC DIGITAL",
        "Print Server"
    );

    public FormSetup()
    {
        InitializeUi();
        ShowStep(0);
    }

    private void InitializeUi()
    {
        Text = "Print Server Setup  •  AMBIC DIGITAL";
        Size = new Size(720, 520);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9f, FontStyle.Regular);
        BackColor = Color.White;

        try
        {
            var ext = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            if (ext != null) Icon = ext;
        }
        catch { }

        // Sidebar
        _pnlSidebar = new Panel
        {
            Dock = DockStyle.Left,
            Width = 190,
            BackColor = Color.FromArgb(18, 28, 48)
        };
        _pnlSidebar.Paint += (s, e) =>
        {
            using var brush = new LinearGradientBrush(_pnlSidebar.ClientRectangle, Color.FromArgb(15, 23, 42), Color.FromArgb(30, 48, 80), 90f);
            e.Graphics.FillRectangle(brush, _pnlSidebar.ClientRectangle);

            using var logoFont = new Font("Segoe UI", 12f, FontStyle.Bold);
            using var subFont = new Font("Segoe UI", 8.25f, FontStyle.Regular);
            using var textBrush = new SolidBrush(Color.White);
            using var subBrush = new SolidBrush(Color.FromArgb(145, 165, 195));

            e.Graphics.DrawString("PRINT SERVER", logoFont, textBrush, new PointF(20, 35));
            e.Graphics.DrawString("Enterprise Spooler\nby AMBIC DIGITAL", subFont, subBrush, new PointF(20, 68));

            // Bullet steps
            string[] steps = ["1. Welcome", "2. Components", "3. Installation", "4. Complete"];
            for (int i = 0; i < steps.Length; i++)
            {
                bool isCurrent = i == _currentStep;
                using var stepFont = new Font("Segoe UI", 9f, isCurrent ? FontStyle.Bold : FontStyle.Regular);
                using var stepBrush = new SolidBrush(isCurrent ? Color.FromArgb(70, 195, 255) : Color.FromArgb(120, 140, 165));
                e.Graphics.DrawString(steps[i], stepFont, stepBrush, new PointF(20, 150 + (i * 32)));
            }
        };

        // Footer Panel
        _pnlFooter = new Panel
        {
            Dock = DockStyle.Bottom,
            Height = 60,
            BackColor = Color.FromArgb(244, 246, 249),
            Padding = new Padding(16, 12, 16, 12)
        };
        _pnlFooter.Paint += (s, e) =>
        {
            using var pen = new Pen(Color.FromArgb(220, 225, 235));
            e.Graphics.DrawLine(pen, 0, 0, _pnlFooter.Width, 0);
        };

        _btnCancel = new Button
        {
            Text = "Cancel",
            Size = new Size(88, 34),
            Location = new Point(_pnlFooter.Width - 105, 13),
            Anchor = AnchorStyles.Bottom | AnchorStyles.Right,
            FlatStyle = FlatStyle.System
        };
        _btnCancel.Click += (s, e) => Close();

        _btnNext = new Button
        {
            Text = "Next >",
            Size = new Size(95, 34),
            Location = new Point(_pnlFooter.Width - 210, 13),
            Anchor = AnchorStyles.Bottom | AnchorStyles.Right,
            FlatStyle = FlatStyle.System
        };
        _btnNext.Click += OnNextClicked;

        _btnBack = new Button
        {
            Text = "< Back",
            Size = new Size(88, 34),
            Location = new Point(_pnlFooter.Width - 305, 13),
            Anchor = AnchorStyles.Bottom | AnchorStyles.Right,
            Enabled = false,
            FlatStyle = FlatStyle.System
        };
        _btnBack.Click += (s, e) => ShowStep(_currentStep - 1);

        _pnlFooter.Controls.AddRange([_btnBack, _btnNext, _btnCancel]);

        // Content Panel
        _pnlContent = new Panel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(28, 24, 28, 16),
            BackColor = Color.White
        };

        Controls.Add(_pnlContent);
        Controls.Add(_pnlSidebar);
        Controls.Add(_pnlFooter);
    }

    private void ShowStep(int step)
    {
        _currentStep = step;
        _pnlContent.Controls.Clear();
        _pnlSidebar.Invalidate();

        switch (step)
        {
            case 0:
                RenderWelcomeStep();
                _btnBack.Enabled = false;
                _btnNext.Text = "Next >";
                _btnNext.Enabled = true;
                break;
            case 1:
                RenderOptionsStep();
                _btnBack.Enabled = true;
                _btnNext.Text = "Install";
                _btnNext.Enabled = true;
                break;
            case 2:
                RenderProgressStep();
                _btnBack.Enabled = false;
                _btnNext.Enabled = false;
                _btnCancel.Enabled = false;
                _ = ExecuteInstallationAsync();
                break;
            case 3:
                RenderCompleteStep();
                _btnBack.Enabled = false;
                _btnNext.Text = "Finish";
                _btnNext.Enabled = true;
                _btnCancel.Visible = false;
                break;
        }
    }

    private void RenderWelcomeStep()
    {
        var lblTitle = new Label
        {
            Text = "Welcome to Print Server Setup",
            Font = new Font("Segoe UI", 13f, FontStyle.Bold),
            ForeColor = Color.FromArgb(20, 30, 48),
            AutoSize = true,
            Location = new Point(0, 0)
        };

        var lblDesc = new Label
        {
            Text = "This wizard will install and configure Print Server on your computer.\n\n" +
                   "Print Server is an enterprise distributed print router engineered by AMBIC DIGITAL. " +
                   "It unifies showroom billing vouchers, customer duplex letterhead overlay printing, " +
                   "tablet estimate thermal receipts, and barcode label printing into a resilient, " +
                   "fault-tolerant Windows print cluster.\n\n" +
                   "Features configured automatically:\n" +
                   " • Automatic legacy discovery and transactional backup snapshot\n" +
                   " • Background Windows Service with delayed auto-start\n" +
                   " • Windows 11 Classic Print Dialog enforcement (#32770 compatibility)\n" +
                   " • Windows Firewall rules for secure LAN inter-node communication\n" +
                   " • Offline SQLite local queue caching ensuring 100% printing uptime\n\n" +
                   "Click Next to choose installation components and destination.",
            Font = new Font("Segoe UI", 9.25f),
            ForeColor = Color.FromArgb(55, 65, 80),
            Size = new Size(470, 320),
            Location = new Point(2, 40)
        };

        _pnlContent.Controls.AddRange([lblTitle, lblDesc]);
    }

    private void RenderOptionsStep()
    {
        var lblTitle = new Label
        {
            Text = "Installation Options & Components",
            Font = new Font("Segoe UI", 12.5f, FontStyle.Bold),
            ForeColor = Color.FromArgb(20, 30, 48),
            AutoSize = true,
            Location = new Point(0, 0)
        };

        // Path
        var lblDir = new Label
        {
            Text = "Destination Folder:",
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            AutoSize = true,
            Location = new Point(2, 38)
        };

        _txtInstallDir = new TextBox
        {
            Text = _defaultInstallDir,
            Size = new Size(370, 26),
            Location = new Point(4, 60),
            Font = new Font("Segoe UI", 9.25f)
        };

        var btnBrowse = new Button
        {
            Text = "Browse...",
            Size = new Size(80, 28),
            Location = new Point(382, 59),
            FlatStyle = FlatStyle.System
        };
        btnBrowse.Click += (s, e) =>
        {
            using var fbd = new FolderBrowserDialog { SelectedPath = _txtInstallDir.Text };
            if (fbd.ShowDialog() == DialogResult.OK)
            {
                _txtInstallDir.Text = fbd.SelectedPath;
            }
        };

        // Components
        var grpComp = new GroupBox
        {
            Text = "Components & System Configuration",
            Size = new Size(462, 235),
            Location = new Point(2, 105),
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            ForeColor = Color.FromArgb(30, 45, 65)
        };

        _chkMigrate = new CheckBox
        {
            Text = "Auto-delete & decommission old print routers, relays & PrintBridge",
            Checked = true,
            AutoSize = true,
            Location = new Point(16, 26),
            Font = new Font("Segoe UI", 9f)
        };

        _chkService = new CheckBox
        {
            Text = "Install & start background Windows Service (AmbicPrintServerNode)",
            Checked = true,
            AutoSize = true,
            Location = new Point(16, 54),
            Font = new Font("Segoe UI", 9f)
        };

        _chkWin11Fix = new CheckBox
        {
            Text = "Enforce Windows 11 Classic Print Dialog (#32770 Win32 compatibility)",
            Checked = true,
            AutoSize = true,
            Location = new Point(16, 82),
            Font = new Font("Segoe UI", 9f)
        };

        _chkFirewall = new CheckBox
        {
            Text = "Configure Windows Firewall rule for Fleet Port 8447",
            Checked = true,
            AutoSize = true,
            Location = new Point(16, 110),
            Font = new Font("Segoe UI", 9f)
        };

        _chkDesktopShortcut = new CheckBox
        {
            Text = "Create Desktop Shortcut (Print Server Console)",
            Checked = true,
            AutoSize = true,
            Location = new Point(16, 138),
            Font = new Font("Segoe UI", 9f)
        };

        _chkStartMenuShortcut = new CheckBox
        {
            Text = "Create Start Menu Program Group Shortcut",
            Checked = true,
            AutoSize = true,
            Location = new Point(16, 166),
            Font = new Font("Segoe UI", 9f)
        };

        _chkAutoStart = new CheckBox
        {
            Text = "Auto-start Print Server in system tray on Windows logon",
            Checked = true,
            AutoSize = true,
            Location = new Point(16, 194),
            Font = new Font("Segoe UI", 9f)
        };

        grpComp.Controls.AddRange([_chkMigrate, _chkService, _chkWin11Fix, _chkFirewall, _chkDesktopShortcut, _chkStartMenuShortcut, _chkAutoStart]);

        _pnlContent.Controls.AddRange([lblTitle, lblDir, _txtInstallDir, btnBrowse, grpComp]);
    }

    private void RenderProgressStep()
    {
        var lblTitle = new Label
        {
            Text = "Installing Print Server...",
            Font = new Font("Segoe UI", 12.5f, FontStyle.Bold),
            ForeColor = Color.FromArgb(20, 30, 48),
            AutoSize = true,
            Location = new Point(0, 0)
        };

        _lblProgressStatus = new Label
        {
            Text = "Preparing installation environment...",
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            ForeColor = Color.FromArgb(40, 85, 175),
            AutoSize = true,
            Location = new Point(2, 38)
        };

        _progressBar = new ProgressBar
        {
            Size = new Size(462, 24),
            Location = new Point(4, 62),
            Style = ProgressBarStyle.Continuous,
            Value = 5
        };

        _txtProgressLog = new TextBox
        {
            Size = new Size(462, 260),
            Location = new Point(4, 98),
            Multiline = true,
            ScrollBars = ScrollBars.Vertical,
            ReadOnly = true,
            BackColor = Color.FromArgb(248, 250, 253),
            ForeColor = Color.FromArgb(40, 50, 65),
            Font = new Font("Consolas", 8.75f)
        };

        _pnlContent.Controls.AddRange([lblTitle, _lblProgressStatus, _progressBar, _txtProgressLog]);
    }

    private void RenderCompleteStep()
    {
        var lblTitle = new Label
        {
            Text = "Installation Successfully Completed!",
            Font = new Font("Segoe UI", 13f, FontStyle.Bold),
            ForeColor = Color.FromArgb(22, 115, 55),
            AutoSize = true,
            Location = new Point(0, 0)
        };

        var lblMsg = new Label
        {
            Text = "Print Server has been successfully installed and configured.\n\n" +
                   "• The background fleet spooler service (AmbicPrintServerNode) is active and running.\n" +
                   "• Local SQLite database initialized with store cluster topology.\n" +
                   "• Windows 11 classic print dialog enforced for Ornate (#32770 Win32 dialog).\n" +
                   "  (Important: If Ornate is currently open, please close and reopen it)\n" +
                   "• Firewall port 8447 open for tablet and billing node print jobs.\n\n" +
                   "You can manage your print fleet and view live spooling activity through the console.",
            Font = new Font("Segoe UI", 9.25f),
            ForeColor = Color.FromArgb(50, 60, 75),
            Size = new Size(470, 200),
            Location = new Point(2, 40)
        };

        _chkLaunchConsole = new CheckBox
        {
            Text = "Launch Print Server Console now",
            Checked = true,
            Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
            ForeColor = Color.FromArgb(20, 30, 48),
            AutoSize = true,
            Location = new Point(4, 260)
        };

        _pnlContent.Controls.AddRange([lblTitle, lblMsg, _chkLaunchConsole]);
    }

    private void UpdateProgress(int percent, string status, string? logMessage = null)
    {
        if (InvokeRequired)
        {
            Invoke(() => UpdateProgress(percent, status, logMessage));
            return;
        }

        _progressBar.Value = Math.Clamp(percent, 0, 100);
        _lblProgressStatus.Text = status;
        if (!string.IsNullOrEmpty(logMessage))
        {
            _txtProgressLog.AppendText($"[{DateTime.Now:HH:mm:ss}] {logMessage}\r\n");
        }
    }

    private async Task ExecuteInstallationAsync()
    {
        try
        {
            var targetDir = _txtInstallDir.Text.Trim();
            Directory.CreateDirectory(targetDir);

            // 1. Migrate, Backup & Decommission Old Print Routers
            if (_chkMigrate.Checked)
            {
                UpdateProgress(10, "Performing transactional backup of legacy components...", "Discovering legacy PrintBridge and Ornate scripts...");
                Program.RunMigrationBackup();
                UpdateProgress(20, "Legacy backup snapshot preserved.", "Backup saved to MigrationBackup directory.");

                UpdateProgress(24, "Decommissioning and auto-deleting old print routers...", "Removing old processes, tasks, registry run keys, and PrintBridge...");
                Program.DecommissionLegacyPrintRouters(msg => UpdateProgress(27, "Decommissioning old print routers...", msg));
                UpdateProgress(30, "Old print routers successfully decommissioned and deleted.", "System cleaned of old print router dependencies.");
            }

            // 2. Initialize ProgramData storage & topology
            UpdateProgress(35, "Initializing local database & fleet topology...", "Creating C:\\ProgramData\\AMBIC DIGITAL\\Print Server...");
            Program.InitTopologyAndStorage();
            UpdateProgress(50, "SQLite topology seeded with 5 nodes & 5 logical printers.", "Topology rules cache configured.");

            // 3. Stop running services and processes before deploying binaries
            UpdateProgress(55, "Stopping active Print Server services...", "Releasing file locks...");
            Program.StopRunningServicesAndProcesses();

            UpdateProgress(60, "Deploying application binaries to Program Files...", $"Copying files to {targetDir}...");
            await Task.Run(() => DeployBinaries(targetDir));
            UpdateProgress(70, "Binaries deployed.", "Files successfully installed.");

            // 4. Setup 355 Letterhead Capture printer & letterhead pipeline
            UpdateProgress(72, "Setting up 355 Letterhead Capture printer...", "Configuring virtual capture printer, spool folders, and letterhead assets...");
            Program.SetupCapturePrinter();

            // 5. Windows 11 Classic Print Dialog Fix
            if (_chkWin11Fix.Checked)
            {
                UpdateProgress(75, "Configuring Windows 11 print dialog compatibility...", "Enforcing classic Win32 #32770 dialog in registry...");
                Program.FixWindows11PrintDialog();
            }

            // 5. Windows Firewall
            if (_chkFirewall.Checked)
            {
                UpdateProgress(80, "Configuring Windows Firewall...", "Adding inbound rule for TCP 8447...");
                Program.ConfigureFirewall();
            }

            // 6. Windows Service
            if (_chkService.Checked)
            {
                UpdateProgress(85, "Registering AmbicPrintNode Windows Service...", "Installing delayed-auto service...");
                Program.InstallWindowsService(targetDir);
            }

            // 7. Shortcuts
            if (_chkDesktopShortcut.Checked || _chkStartMenuShortcut.Checked)
            {
                UpdateProgress(90, "Creating application shortcuts...", "Creating Start Menu and Desktop shortcuts...");
                CreateShortcuts(targetDir);
            }

            // 8. Tray Auto-start on logon
            if (_chkAutoStart.Checked)
            {
                UpdateProgress(93, "Configuring system tray auto-start on logon...", "Registering Print Server in Windows Run startup...");
                Program.ConfigureAutoStartConsole(targetDir, true);
            }

            // 9. Health verification
            UpdateProgress(96, "Verifying local service health...", "Pinging http://127.0.0.1:8447/health...");
            await Program.VerifyHealthAsync();

            UpdateProgress(100, "Installation complete!", "Ready.");
            await Task.Delay(800);

            Invoke(() => ShowStep(3));
        }
        catch (Exception ex)
        {
            UpdateProgress(100, "Installation encountered an issue.", $"ERROR: {ex.Message}");
            MessageBox.Show($"Installation error: {ex.Message}", "Setup Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Invoke(() =>
            {
                _btnBack.Enabled = true;
                _btnNext.Text = "Retry";
                _btnNext.Enabled = true;
            });
        }
    }

    private void DeployBinaries(string targetDir)
    {
        Directory.CreateDirectory(targetDir);

        // 1. Try embedded zip resource first (true standalone deployment)
        var assembly = typeof(FormSetup).Assembly;
        var resourceName = assembly.GetManifestResourceNames().FirstOrDefault(n => n.EndsWith("payload.zip", StringComparison.OrdinalIgnoreCase));
        if (resourceName != null)
        {
            using var stream = assembly.GetManifestResourceStream(resourceName);
            if (stream != null)
            {
                using var archive = new System.IO.Compression.ZipArchive(stream);
                foreach (var entry in archive.Entries)
                {
                    if (string.IsNullOrEmpty(entry.Name))
                    {
                        var dirPath = Path.Combine(targetDir, entry.FullName.Replace('/', Path.DirectorySeparatorChar));
                        Directory.CreateDirectory(dirPath);
                        continue;
                    }

                    string relPath = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                    string destPath = Path.Combine(targetDir, relPath);
                    Directory.CreateDirectory(Path.GetDirectoryName(destPath)!);
                    SafeExtractToFile(entry, destPath);
                }

                // Ensure 64-bit sqlite DLL and Windows ServiceController DLL are available in root
                var x64Sqlite = Path.Combine(targetDir, "runtimes", "win-x64", "native", "e_sqlite3.dll");
                if (File.Exists(x64Sqlite))
                {
                    SafeCopyFile(x64Sqlite, Path.Combine(targetDir, "e_sqlite3.dll"));
                }

                var winSvc = Path.Combine(targetDir, "runtimes", "win", "lib", "net10.0", "System.ServiceProcess.ServiceController.dll");
                if (File.Exists(winSvc))
                {
                    SafeCopyFile(winSvc, Path.Combine(targetDir, "System.ServiceProcess.ServiceController.dll"));
                }
                return;
            }
        }

        // 2. Fallback: Copy from local publish directories if present
        string basePublish = @"c:\AradhanaSystems\projects\print-router\publish";
        string[] sourceDirs = [
            Path.Combine(basePublish, "console"),
            Path.Combine(basePublish, "node")
        ];

        foreach (var src in sourceDirs)
        {
            if (Directory.Exists(src))
            {
                foreach (var dir in Directory.GetDirectories(src, "*", SearchOption.AllDirectories))
                {
                    string rel = Path.GetRelativePath(src, dir);
                    Directory.CreateDirectory(Path.Combine(targetDir, rel));
                }
                foreach (var file in Directory.GetFiles(src, "*.*", SearchOption.AllDirectories))
                {
                    string rel = Path.GetRelativePath(src, file);
                    var dest = Path.Combine(targetDir, rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
                    SafeCopyFile(file, dest);
                }
            }
        }

        var x64SqliteFallback = Path.Combine(targetDir, "runtimes", "win-x64", "native", "e_sqlite3.dll");
        if (File.Exists(x64SqliteFallback))
        {
            SafeCopyFile(x64SqliteFallback, Path.Combine(targetDir, "e_sqlite3.dll"));
        }

        var winSvcFallback = Path.Combine(targetDir, "runtimes", "win", "lib", "net10.0", "System.ServiceProcess.ServiceController.dll");
        if (File.Exists(winSvcFallback))
        {
            SafeCopyFile(winSvcFallback, Path.Combine(targetDir, "System.ServiceProcess.ServiceController.dll"));
        }
    }

    private static void SafeExtractToFile(System.IO.Compression.ZipArchiveEntry entry, string destPath)
    {
        for (int attempt = 1; attempt <= 5; attempt++)
        {
            try
            {
                entry.ExtractToFile(destPath, overwrite: true);
                return;
            }
            catch (IOException)
            {
                if (attempt == 1)
                {
                    Program.StopRunningServicesAndProcesses();
                }
                else if (attempt >= 3 && File.Exists(destPath))
                {
                    try
                    {
                        var oldPath = $"{destPath}.old.{Guid.NewGuid():N}";
                        File.Move(destPath, oldPath, overwrite: true);
                        entry.ExtractToFile(destPath, overwrite: true);
                        return;
                    }
                    catch { }
                }
                Thread.Sleep(500);
            }
        }
        entry.ExtractToFile(destPath, overwrite: true);
    }

    private static void SafeCopyFile(string src, string dest)
    {
        for (int attempt = 1; attempt <= 5; attempt++)
        {
            try
            {
                File.Copy(src, dest, overwrite: true);
                return;
            }
            catch (IOException)
            {
                if (attempt == 1)
                {
                    Program.StopRunningServicesAndProcesses();
                }
                else if (attempt >= 3 && File.Exists(dest))
                {
                    try
                    {
                        var oldPath = $"{dest}.old.{Guid.NewGuid():N}";
                        File.Move(dest, oldPath, overwrite: true);
                        File.Copy(src, dest, overwrite: true);
                        return;
                    }
                    catch { }
                }
                Thread.Sleep(500);
            }
        }
        File.Copy(src, dest, overwrite: true);
    }

    private void CreateShortcuts(string targetDir)
    {
        var consoleExe = Path.Combine(targetDir, "Ambic.PrintConsole.exe");
        if (!File.Exists(consoleExe))
        {
            consoleExe = Path.Combine(@"c:\AradhanaSystems\projects\print-router\publish\console", "Ambic.PrintConsole.exe");
        }

        try
        {
            Type? shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) return;
            dynamic shell = Activator.CreateInstance(shellType)!;

            if (_chkDesktopShortcut.Checked)
            {
                var desktopPath = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                var lnkPath = Path.Combine(desktopPath, "Print Server.lnk");
                var shortcut = shell.CreateShortcut(lnkPath);
                shortcut.TargetPath = consoleExe;
                shortcut.WorkingDirectory = Path.GetDirectoryName(consoleExe);
                shortcut.IconLocation = $"{consoleExe},0";
                shortcut.Description = "Print Server - Enterprise Print Spooler";
                shortcut.Save();
            }

            if (_chkStartMenuShortcut.Checked)
            {
                var programsPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms), "AMBIC DIGITAL");
                Directory.CreateDirectory(programsPath);
                var lnkPath = Path.Combine(programsPath, "Print Server.lnk");
                var shortcut = shell.CreateShortcut(lnkPath);
                shortcut.TargetPath = consoleExe;
                shortcut.WorkingDirectory = Path.GetDirectoryName(consoleExe);
                shortcut.IconLocation = $"{consoleExe},0";
                shortcut.Description = "Print Server - Enterprise Print Spooler";
                shortcut.Save();
            }
        }
        catch { }
    }

    private void OnNextClicked(object? sender, EventArgs e)
    {
        if (_currentStep == 0)
        {
            ShowStep(1);
        }
        else if (_currentStep == 1)
        {
            ShowStep(2);
        }
        else if (_currentStep == 3)
        {
            if (_chkLaunchConsole.Checked)
            {
                var targetDir = _txtInstallDir.Text.Trim();
                var consoleExe = Path.Combine(targetDir, "Ambic.PrintConsole.exe");
                if (!File.Exists(consoleExe))
                {
                    consoleExe = Path.Combine(@"c:\AradhanaSystems\projects\print-router\publish\console", "Ambic.PrintConsole.exe");
                }
                if (File.Exists(consoleExe))
                {
                    Process.Start(new ProcessStartInfo(consoleExe) { UseShellExecute = true });
                }
            }
            Close();
        }
    }
}

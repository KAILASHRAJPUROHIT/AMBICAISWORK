using System.Data;
using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Ambic.Print.Storage.Database;
using Ambic.Print.Storage.Queues;
using Ambic.Print.Storage.Repositories;
using Ambic.PrintAdapters.Ornate;
using Ambic.PrintAdapters.Thermal;
using Ambic.PrintCore.Config;
using Ambic.PrintCore.Models;
using Ambic.PrintCore.Routing;
using Ambic.PrintCore.Spooler;

namespace Ambic.PrintConsole;

public partial class FormMain : Form
{
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(5) };
    private readonly string _dbPath;
    private readonly string _jobsDir;
    private readonly string _configPath;
    private readonly string _assetsDir;
    private NodeDatabase? _db;
    private JobRepository? _jobRepo;
    private TopologyRepository? _topRepo;
    private DiskJobQueue? _queue;
    private RulesCacheStore? _rulesStore;
    private RouterHubConfig? _hubConfig;
    private System.Windows.Forms.Timer? _refreshTimer;
    private System.Windows.Forms.Timer? _watcherTimer;
    private readonly PrintDialogInterceptor _dialogInterceptor = new();
    private readonly CaptureSpoolWatcher _captureWatcher = new();
    private readonly RawTcpPrintRelay _tcpRelay = new();
    private bool _emergencyBypassActive;

    // UI Controls
    private Label _lblStatusPill = null!;
    private Panel _pnlStatusPill = null!;
    private Button _btnEmergencyBypass = null!;
    private Button _btnRefresh = null!;
    private TabControl _tabCtrl = null!;
    private DataGridView _gridNodes = null!;
    private DataGridView _gridPrinters = null!;
    private DataGridView _gridJobs = null!;
    private TextBox _txtDiagnostics = null!;
    private Button _btnSimulateOrnate = null!;
    private Button _btnSimulateEstimate = null!;
    private Button _btnTestPrint = null!;

    // Smart Routing UI Controls
    private ComboBox _cmbPcRole = null!;
    private CheckBox _chkMasterEnable = null!;
    private TextBox _txtCopy1Default = null!;
    private TextBox _txtCopy2Default = null!;
    private ComboBox _cmbBothMode = null!;
    private Label _lblBothWarning = null!;
    private TextBox _txtForceCopy1 = null!;
    private TextBox _txtForceCopy2 = null!;
    private DataGridView _gridRules = null!;
    private TextBox _txtWatcherLog = null!;

    // Tray Icon & Background Execution
    private NotifyIcon? _trayIcon;
    private ContextMenuStrip? _trayMenu;
    private bool _isExiting;
    private ToolStripMenuItem? _menuStatus;
    private ToolStripMenuItem? _menuAutoRouting;
    private ToolStripMenuItem? _menuEmergencyBypass;

    public FormMain()
    {
        var baseDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
        _dbPath = Path.Combine(baseDir, "db", "node.db");
        _jobsDir = Path.Combine(baseDir, "jobs");
        _configPath = Path.Combine(baseDir, "config", "rules.json");
        _assetsDir = Path.Combine(baseDir, "assets");
        Directory.CreateDirectory(_assetsDir);

        try
        {
            _rulesStore = new RulesCacheStore(_configPath);
            _hubConfig = _rulesStore.LoadHubConfig();
        }
        catch { }

        InitializeModernUi();
        InitStorage();
        LoadHubConfigToUi();
        InitializeTrayIcon();

        _refreshTimer = new System.Windows.Forms.Timer { Interval = 3000 };
        _refreshTimer.Tick += async (s, e) => await RefreshAllAsync();
        _refreshTimer.Start();

        _dialogInterceptor.LogEvent += msg => LogWatcher(msg);
        _captureWatcher.LogEvent += msg => LogWatcher(msg);
        _tcpRelay.LogEvent += msg => LogWatcher(msg);

        _captureWatcher.Start(_hubConfig);
        _tcpRelay.Start();

        _watcherTimer = new System.Windows.Forms.Timer { Interval = 200 };
        _watcherTimer.Tick += (s, e) => ScanActiveWindows();
        _watcherTimer.Start();

        Shown += OnFormShown;
        _ = RefreshAllAsync();
    }

    private void InitStorage()
    {
        try
        {
            SQLitePCL.Batteries_V2.Init();
            if (File.Exists(_dbPath))
            {
                _db = new NodeDatabase(_dbPath);
                _jobRepo = new JobRepository(_db);
                _topRepo = new TopologyRepository(_db);
                _queue = new DiskJobQueue(_jobsDir);
                LogDiagnostic($"[STORAGE] Connected to local SQLite DB at {_dbPath}");
            }
            else
            {
                LogDiagnostic($"[STORAGE] DB not found at {_dbPath}, awaiting local database initialization.");
            }
        }
        catch (Exception ex)
        {
            LogDiagnostic($"[ERROR] Local DB init: {ex.Message}");
        }
    }

    private void InitializeModernUi()
    {
        Text = "Print Server  •  Fleet Orchestration Console";
        Size = new Size(1280, 780);
        MinimumSize = new Size(1024, 640);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9.25f, FontStyle.Regular);
        BackColor = Color.FromArgb(245, 247, 250);

        // ================= TOP HEADER =================
        var pnlHeader = new Panel
        {
            Dock = DockStyle.Top,
            Height = 84,
            BackColor = Color.FromArgb(18, 24, 38),
            Padding = new Padding(24, 10, 24, 10)
        };

        // Left Brand Box
        var pnlBrand = new Panel
        {
            Dock = DockStyle.Left,
            Width = 620,
            BackColor = Color.Transparent
        };

        var lblBrand = new Label
        {
            Text = "PRINT SERVER",
            Font = new Font("Segoe UI", 13.5f, FontStyle.Bold),
            ForeColor = Color.White,
            AutoSize = true,
            Location = new Point(0, 4)
        };

        var lblSub = new Label
        {
            Text = "Powered by AMBIC DIGITAL  |  Enterprise Distributed Spooling Engine",
            Font = new Font("Segoe UI", 8.75f, FontStyle.Regular),
            ForeColor = Color.FromArgb(145, 165, 195),
            AutoSize = true,
            Location = new Point(1, 32)
        };
        pnlBrand.Controls.AddRange([lblBrand, lblSub]);

        // Right Actions Flow Panel (prevents overlap on all resolutions)
        var pnlActions = new FlowLayoutPanel
        {
            Dock = DockStyle.Right,
            FlowDirection = FlowDirection.RightToLeft,
            WrapContents = false,
            AutoSize = true,
            BackColor = Color.Transparent,
            Padding = new Padding(0, 10, 0, 0)
        };

        _btnRefresh = new Button
        {
            Text = "⟳ Refresh",
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            BackColor = Color.FromArgb(42, 54, 76),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Size = new Size(105, 38),
            Margin = new Padding(8, 0, 0, 0),
            Cursor = Cursors.Hand
        };
        _btnRefresh.FlatAppearance.BorderSize = 0;
        _btnRefresh.Click += async (s, e) => await RefreshAllAsync();

        _btnEmergencyBypass = new Button
        {
            Text = "EMERGENCY BYPASS: OFF",
            Font = new Font("Segoe UI", 8.75f, FontStyle.Bold),
            BackColor = Color.FromArgb(38, 135, 75),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Size = new Size(210, 38),
            Margin = new Padding(12, 0, 0, 0),
            Cursor = Cursors.Hand
        };
        _btnEmergencyBypass.FlatAppearance.BorderSize = 0;
        _btnEmergencyBypass.Click += OnToggleBypassClicked;

        // Pill status badge
        _pnlStatusPill = new Panel
        {
            AutoSize = true,
            MinimumSize = new Size(300, 38),
            Height = 38,
            BackColor = Color.FromArgb(28, 38, 56),
            Margin = new Padding(12, 0, 0, 0),
            Padding = new Padding(14, 8, 14, 8)
        };

        _lblStatusPill = new Label
        {
            Text = "● Node Service: Checking...",
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            ForeColor = Color.FromArgb(240, 180, 50),
            AutoSize = true,
            Location = new Point(12, 9)
        };
        _pnlStatusPill.Controls.Add(_lblStatusPill);

        pnlActions.Controls.Add(_btnRefresh);
        pnlActions.Controls.Add(_btnEmergencyBypass);
        pnlActions.Controls.Add(_pnlStatusPill);

        pnlHeader.Controls.Add(pnlBrand);
        pnlHeader.Controls.Add(pnlActions);
        Controls.Add(pnlHeader);

        // ================= MAIN TABS =================
        _tabCtrl = new TabControl
        {
            Dock = DockStyle.Fill,
            Padding = new Point(16, 10),
            Font = new Font("Segoe UI", 9.5f, FontStyle.Regular),
            DrawMode = TabDrawMode.OwnerDrawFixed,
            ItemSize = new Size(225, 42),
            SizeMode = TabSizeMode.Fixed
        };
        _tabCtrl.DrawItem += OnDrawTabItem;

        // Tab 1: Fleet Topology & Hardware
        var tabTopology = new TabPage("Fleet Nodes & Topology") { BackColor = Color.FromArgb(245, 247, 250) };
        BuildTopologyTab(tabTopology);
        _tabCtrl.TabPages.Add(tabTopology);

        // Tab 2: Logical Printers
        var tabPrinters = new TabPage("Logical Printers && Routing") { BackColor = Color.FromArgb(245, 247, 250) };
        BuildPrintersTab(tabPrinters);
        _tabCtrl.TabPages.Add(tabPrinters);

        // Tab 3: Program & Voucher Routing Rules
        var tabRouting = new TabPage("Program && Voucher Rules") { BackColor = Color.FromArgb(245, 247, 250) };
        BuildSmartRoutingTab(tabRouting);
        _tabCtrl.TabPages.Add(tabRouting);

        // Tab 4: Print Jobs Queue & Audit
        var tabJobs = new TabPage("Live Spooler && Job History") { BackColor = Color.FromArgb(245, 247, 250) };
        BuildJobsTab(tabJobs);
        _tabCtrl.TabPages.Add(tabJobs);

        // Tab 5: Diagnostics & Testing
        var tabDiag = new TabPage("Diagnostics && Simulation") { BackColor = Color.FromArgb(245, 247, 250) };
        BuildDiagnosticsTab(tabDiag);
        _tabCtrl.TabPages.Add(tabDiag);

        Controls.Add(_tabCtrl);
        _tabCtrl.BringToFront();
    }

    private void OnDrawTabItem(object? sender, DrawItemEventArgs e)
    {
        var tab = _tabCtrl.TabPages[e.Index];
        var isSelected = (e.State & DrawItemState.Selected) == DrawItemState.Selected;
        var tabBounds = _tabCtrl.GetTabRect(e.Index);

        using var bgBrush = new SolidBrush(isSelected ? Color.White : Color.FromArgb(235, 239, 244));
        e.Graphics.FillRectangle(bgBrush, tabBounds);

        if (isSelected)
        {
            // Active bottom highlight bar
            using var activeBarBrush = new SolidBrush(Color.FromArgb(24, 110, 235));
            e.Graphics.FillRectangle(activeBarBrush, tabBounds.X, tabBounds.Bottom - 3, tabBounds.Width, 3);
        }

        using var textBrush = new SolidBrush(isSelected ? Color.FromArgb(20, 30, 48) : Color.FromArgb(100, 115, 135));
        using var font = new Font("Segoe UI", 9.25f, isSelected ? FontStyle.Bold : FontStyle.Regular);

        var sf = new StringFormat
        {
            Alignment = StringAlignment.Center,
            LineAlignment = StringAlignment.Center
        };
        // Clean text (strip double ampersands for display)
        var cleanTitle = tab.Text.Replace("&&", "&");
        e.Graphics.DrawString(cleanTitle, font, textBrush, tabBounds, sf);
    }

    private static Icon CreateAppIcon()
    {
        var exeDir = AppDomain.CurrentDomain.BaseDirectory;
        var candidates = new[]
        {
            Path.Combine(exeDir, "app.ico"),
            Path.Combine(exeDir, "assets", "app.ico"),
            @"c:\AradhanaSystems\projects\print-router\assets\app.ico"
        };

        foreach (var path in candidates)
        {
            if (File.Exists(path))
            {
                try
                {
                    return new Icon(path, 32, 32);
                }
                catch { }
            }
        }

        try
        {
            var extracted = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            if (extracted != null) return extracted;
        }
        catch { }

        using var bmp = new Bitmap(32, 32);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using var bgBrush = new SolidBrush(Color.FromArgb(18, 24, 38));
            g.FillRectangle(bgBrush, 0, 0, 32, 32);

            using var bodyBrush = new SolidBrush(Color.FromArgb(235, 240, 248));
            g.FillRectangle(bodyBrush, 4, 11, 24, 12);

            using var paperBrush = new SolidBrush(Color.White);
            g.FillRectangle(paperBrush, 8, 3, 16, 8);

            using var slotBrush = new SolidBrush(Color.FromArgb(30, 42, 60));
            g.FillRectangle(slotBrush, 7, 16, 18, 3);

            using var dotBrush = new SolidBrush(Color.FromArgb(40, 200, 90));
            g.FillEllipse(dotBrush, 21, 19, 9, 9);
        }
        return Icon.FromHandle(bmp.GetHicon());
    }

    private void InitializeTrayIcon()
    {
        try
        {
            var appIcon = CreateAppIcon();
            Icon = appIcon;

            _trayMenu = new ContextMenuStrip();

            var menuTitle = new ToolStripMenuItem("Print Server Console")
            {
                Font = new Font("Segoe UI", 9.25f, FontStyle.Bold)
            };
            menuTitle.Click += (s, e) => ShowAndRestoreConsole();

            _menuStatus = new ToolStripMenuItem("● Node Service: Checking...")
            {
                Enabled = false,
                Font = new Font("Segoe UI", 9f, FontStyle.Regular)
            };

            _menuAutoRouting = new ToolStripMenuItem("Master Auto-Routing", null, (s, e) =>
            {
                _chkMasterEnable.Checked = !_chkMasterEnable.Checked;
                SaveStationSettings();
            })
            {
                Checked = _chkMasterEnable?.Checked ?? true
            };

            _menuEmergencyBypass = new ToolStripMenuItem("Emergency Direct Bypass", null, (s, e) =>
            {
                OnToggleBypassClicked(s, e);
            })
            {
                Checked = _emergencyBypassActive
            };

            var menuOpenLogs = new ToolStripMenuItem("Open Spooler Logs", null, (s, e) =>
            {
                try
                {
                    var logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
                    if (Directory.Exists(logDir))
                    {
                        Process.Start(new ProcessStartInfo { FileName = logDir, UseShellExecute = true });
                    }
                }
                catch { }
            });

            var menuExit = new ToolStripMenuItem("Exit Print Server", null, (s, e) =>
            {
                var confirm = MessageBox.Show(
                    this,
                    "Are you sure you want to exit Print Server?\n\nAutomated print routing from Ornate and other applications will stop monitoring until reopened.",
                    "Exit Print Server",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Warning
                );
                if (confirm == DialogResult.Yes)
                {
                    _isExiting = true;
                    if (_trayIcon != null)
                    {
                        _trayIcon.Visible = false;
                        _trayIcon.Dispose();
                    }
                    Application.Exit();
                }
            });

            _trayMenu.Items.Add(menuTitle);
            _trayMenu.Items.Add(new ToolStripSeparator());
            _trayMenu.Items.Add(_menuStatus);
            _trayMenu.Items.Add(_menuAutoRouting);
            _trayMenu.Items.Add(_menuEmergencyBypass);
            _trayMenu.Items.Add(new ToolStripSeparator());
            _trayMenu.Items.Add(menuOpenLogs);
            _trayMenu.Items.Add(new ToolStripSeparator());
            _trayMenu.Items.Add(menuExit);

            _trayIcon = new NotifyIcon
            {
                Icon = appIcon,
                ContextMenuStrip = _trayMenu,
                Text = "Print Server • AMBIC DIGITAL",
                Visible = true
            };

            _trayIcon.DoubleClick += (s, e) => ShowAndRestoreConsole();
        }
        catch (Exception ex)
        {
            LogDiagnostic($"[ERROR] Tray init: {ex.Message}");
        }
    }

    private void ShowAndRestoreConsole()
    {
        Show();
        if (WindowState == FormWindowState.Minimized)
        {
            WindowState = FormWindowState.Normal;
        }
        ShowInTaskbar = true;
        BringToFront();
        Activate();
    }

    private void OnFormShown(object? sender, EventArgs e)
    {
        if (Environment.GetCommandLineArgs().Any(a => a.Equals("--tray", StringComparison.OrdinalIgnoreCase) || a.Equals("--minimized", StringComparison.OrdinalIgnoreCase)))
        {
            WindowState = FormWindowState.Minimized;
            ShowInTaskbar = false;
            BeginInvoke(Hide);
        }
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        LogWatcher($"[FORM CLOSING] CloseReason={e.CloseReason}, Cancel={e.Cancel}, isExiting={_isExiting}");
        if (!_isExiting && (e.CloseReason == CloseReason.UserClosing || e.CloseReason == CloseReason.None))
        {
            e.Cancel = true;
            Hide();
            ShowInTaskbar = false;
            _trayIcon?.ShowBalloonTip(
                2500,
                "Print Server",
                "Print Server is running in the background.\nDouble-click the tray icon to reopen the console.",
                ToolTipIcon.Info
            );
            return;
        }

        if (_trayIcon != null)
        {
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
        }
        base.OnFormClosing(e);
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        LogWatcher($"[FORM CLOSED] CloseReason={e.CloseReason}");
        base.OnFormClosed(e);
    }

    private void BuildTopologyTab(TabPage tab)
    {
        var container = new Panel { Dock = DockStyle.Fill, Padding = new Padding(16) };
        var card = CreateModernCard("Cluster Fleet Nodes (Store Network Infrastructure)", out var bodyPanel);

        _gridNodes = CreateStyledGrid();
        _gridNodes.Columns.Add("NodeId", "Node Identifier");
        _gridNodes.Columns.Add("FriendlyName", "Host Machine Name");
        _gridNodes.Columns.Add("Ip", "IPv4 Address");
        _gridNodes.Columns.Add("Role", "Assigned Architecture Role");
        _gridNodes.Columns.Add("Status", "Node Status");
        _gridNodes.Columns.Add("LastSeen", "Last Ping / Heartbeat");

        bodyPanel.Controls.Add(_gridNodes);
        container.Controls.Add(card);
        tab.Controls.Add(container);
    }

    private void BuildPrintersTab(TabPage tab)
    {
        var container = new Panel { Dock = DockStyle.Fill, Padding = new Padding(16) };
        var card = CreateModernCard("Logical Printers & Dynamic Hardware Routing", out var bodyPanel);

        _gridPrinters = CreateStyledGrid();
        _gridPrinters.Columns.Add("LogicalId", "Logical Printer ID");
        _gridPrinters.Columns.Add("Purpose", "Document Purpose");
        _gridPrinters.Columns.Add("PhysicalId", "Bound Hardware Fingerprint");
        _gridPrinters.Columns.Add("HostNode", "Physical Host Workstation");
        _gridPrinters.Columns.Add("Queue", "Windows Queue Name");
        _gridPrinters.Columns.Add("Status", "Spooler Status");

        bodyPanel.Controls.Add(_gridPrinters);
        container.Controls.Add(card);
        tab.Controls.Add(container);
    }

    private void BuildJobsTab(TabPage tab)
    {
        var container = new Panel { Dock = DockStyle.Fill, Padding = new Padding(16) };
        var card = CreateModernCard("Recent Print Jobs (Idempotency & Lifecycle Ledger)", out var bodyPanel);

        _gridJobs = CreateStyledGrid();
        _gridJobs.Columns.Add("JobId", "Job ID");
        _gridJobs.Columns.Add("DocType", "Document Type");
        _gridJobs.Columns.Add("Dest", "Logical Target");
        _gridJobs.Columns.Add("Source", "Source Node");
        _gridJobs.Columns.Add("Copies", "Copies");
        _gridJobs.Columns.Add("State", "Status");
        _gridJobs.Columns.Add("Time", "Timestamp");
        _gridJobs.Columns.Add("Detail", "Routing & Execution Detail");

        bodyPanel.Controls.Add(_gridJobs);
        container.Controls.Add(card);
        tab.Controls.Add(container);
    }

    private void BuildDiagnosticsTab(TabPage tab)
    {
        var container = new Panel { Dock = DockStyle.Fill, Padding = new Padding(16) };

        var split = new SplitContainer
        {
            Dock = DockStyle.Fill,
            Orientation = Orientation.Horizontal,
            SplitterDistance = 100,
            SplitterWidth = 8
        };

        // Actions Card
        var actionsCard = CreateModernCard("Simulation & Spooler Diagnostic Actions", out var pnlActions);

        var flowBtns = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(10, 8, 10, 8),
            WrapContents = false,
            AutoScroll = true
        };

        _btnSimulateOrnate = new Button
        {
            Text = "Simulate Ornate Voucher (2 Copies)",
            Size = new Size(295, 42),
            BackColor = Color.FromArgb(24, 115, 220),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Margin = new Padding(0, 0, 14, 0),
            Cursor = Cursors.Hand
        };
        _btnSimulateOrnate.FlatAppearance.BorderSize = 0;
        _btnSimulateOrnate.Click += async (s, e) => await SimulateOrnateVoucherAsync();

        _btnSimulateEstimate = new Button
        {
            Text = "Simulate Tablet Estimate Receipt",
            Size = new Size(280, 42),
            BackColor = Color.FromArgb(38, 135, 75),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Margin = new Padding(0, 0, 14, 0),
            Cursor = Cursors.Hand
        };
        _btnSimulateEstimate.FlatAppearance.BorderSize = 0;
        _btnSimulateEstimate.Click += async (s, e) => await SimulateTabletEstimateAsync();

        _btnTestPrint = new Button
        {
            Text = "Spool Diagnostic Test Ticket",
            Size = new Size(260, 42),
            BackColor = Color.FromArgb(220, 120, 20),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Margin = new Padding(0, 0, 14, 0),
            Cursor = Cursors.Hand
        };
        _btnTestPrint.FlatAppearance.BorderSize = 0;
        _btnTestPrint.Click += async (s, e) => await RunDiagnosticTestTicketAsync();

        flowBtns.Controls.AddRange([_btnSimulateOrnate, _btnSimulateEstimate, _btnTestPrint]);
        pnlActions.Controls.Add(flowBtns);
        split.Panel1.Controls.Add(actionsCard);

        // Logs Card
        var logsCard = CreateModernCard("Live Distributed Diagnostics & Audit Stream", out var pnlLogs);

        _txtDiagnostics = new TextBox
        {
            Dock = DockStyle.Fill,
            Multiline = true,
            ScrollBars = ScrollBars.Vertical,
            ReadOnly = true,
            BackColor = Color.FromArgb(16, 20, 28),
            ForeColor = Color.FromArgb(150, 220, 160),
            Font = new Font("Consolas", 9.5f),
            BorderStyle = BorderStyle.None
        };
        pnlLogs.Controls.Add(_txtDiagnostics);
        split.Panel2.Controls.Add(logsCard);

        container.Controls.Add(split);
        tab.Controls.Add(container);
    }

    private static Panel CreateModernCard(string title, [System.Diagnostics.CodeAnalysis.NotNull] out Panel bodyPanel)
    {
        var card = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.White,
            Padding = new Padding(1)
        };
        card.Paint += (s, e) =>
        {
            // Subtle 1px border
            using var pen = new Pen(Color.FromArgb(215, 222, 232), 1);
            e.Graphics.DrawRectangle(pen, 0, 0, card.Width - 1, card.Height - 1);
        };

        var header = new Panel
        {
            Dock = DockStyle.Top,
            Height = 44,
            BackColor = Color.FromArgb(248, 250, 252),
            Padding = new Padding(16, 12, 16, 8)
        };
        header.Paint += (s, e) =>
        {
            using var pen = new Pen(Color.FromArgb(230, 235, 242), 1);
            e.Graphics.DrawLine(pen, 0, header.Height - 1, header.Width, header.Height - 1);
        };

        var lblTitle = new Label
        {
            Text = title,
            Font = new Font("Segoe UI", 10.25f, FontStyle.Bold),
            ForeColor = Color.FromArgb(30, 42, 60),
            AutoSize = true,
            Location = new Point(14, 10),
            UseMnemonic = false
        };
        header.Controls.Add(lblTitle);

        bodyPanel = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.White,
            Padding = new Padding(10)
        };

        card.Controls.Add(bodyPanel);
        card.Controls.Add(header);
        return card;
    }

    private static DataGridView CreateStyledGrid()
    {
        var grid = new DataGridView
        {
            Dock = DockStyle.Fill,
            BackgroundColor = Color.White,
            BorderStyle = BorderStyle.None,
            RowHeadersVisible = false,
            AllowUserToAddRows = false,
            AllowUserToDeleteRows = false,
            ReadOnly = true,
            SelectionMode = DataGridViewSelectionMode.FullRowSelect,
            AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
            CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal,
            GridColor = Color.FromArgb(235, 239, 245),
            RowTemplate = { Height = 40 }
        };

        grid.ColumnHeadersDefaultCellStyle.BackColor = Color.FromArgb(240, 244, 248);
        grid.ColumnHeadersDefaultCellStyle.ForeColor = Color.FromArgb(50, 65, 85);
        grid.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 9.25f, FontStyle.Bold);
        grid.ColumnHeadersDefaultCellStyle.Padding = new Padding(8, 2, 8, 2);
        grid.ColumnHeadersHeight = 46;
        grid.EnableHeadersVisualStyles = false;

        grid.DefaultCellStyle.SelectionBackColor = Color.FromArgb(228, 238, 252);
        grid.DefaultCellStyle.SelectionForeColor = Color.FromArgb(15, 25, 40);
        grid.DefaultCellStyle.Font = new Font("Segoe UI", 9.25f);
        grid.DefaultCellStyle.Padding = new Padding(8, 2, 8, 2);
        grid.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(252, 253, 255);

        // Custom badge painting for status column
        grid.CellPainting += (s, e) =>
        {
            if (e.Graphics != null && e.RowIndex >= 0 && e.ColumnIndex >= 0)
            {
                var colName = grid.Columns[e.ColumnIndex].Name;
                if (colName is "Status" or "State")
                {
                    e.PaintBackground(e.CellBounds, true);
                    var text = e.Value?.ToString() ?? "";

                    Color badgeBg = Color.FromArgb(235, 240, 245);
                    Color badgeFg = Color.FromArgb(60, 75, 95);

                    if (text is "ONLINE" or "READY" or "COMPLETED")
                    {
                        badgeBg = Color.FromArgb(220, 248, 228);
                        badgeFg = Color.FromArgb(22, 115, 55);
                    }
                    else if (text is "UNREACHABLE" or "OFFLINE" or "FAILED")
                    {
                        badgeBg = Color.FromArgb(254, 226, 226);
                        badgeFg = Color.FromArgb(185, 28, 28);
                    }
                    else if (text is "HELD" or "BYPASSED" or "ALREADY_ACCEPTED")
                    {
                        badgeBg = Color.FromArgb(254, 243, 199);
                        badgeFg = Color.FromArgb(160, 95, 10);
                    }

                    var badgeRect = new Rectangle(e.CellBounds.X + 6, e.CellBounds.Y + 5, Math.Min(e.CellBounds.Width - 12, 110), e.CellBounds.Height - 10);
                    using var brush = new SolidBrush(badgeBg);
                    e.Graphics.FillRectangle(brush, badgeRect);

                    using var textBrush = new SolidBrush(badgeFg);
                    using var font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
                    var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                    e.Graphics.DrawString(text, font, textBrush, badgeRect, sf);

                    e.Handled = true;
                }
            }
        };

        return grid;
    }

    private void LogDiagnostic(string message)
    {
        if (InvokeRequired)
        {
            Invoke(() => LogDiagnostic(message));
            return;
        }
        var line = $"[{DateTime.Now:HH:mm:ss}] {message}\r\n";
        _txtDiagnostics.AppendText(line);
    }

    private async Task RefreshAllAsync()
    {
        try
        {
            // 1. Query Node Health via HTTP (localhost:8447)
            bool serviceOnline = false;
            try
            {
                var res = await _http.GetAsync("http://127.0.0.1:8447/health");
                if (res.IsSuccessStatusCode)
                {
                    serviceOnline = true;
                    var json = await res.Content.ReadAsStringAsync();
                    using var doc = JsonDocument.Parse(json);
                    var root = doc.RootElement;
                    _emergencyBypassActive = root.TryGetProperty("emergencyBypassActive", out var bp) && bp.GetBoolean();
                    UpdateBypassUi();
                }
            }
            catch { }

            if (serviceOnline)
            {
                _lblStatusPill.Text = "● Fleet Service: ONLINE (Port 8447)";
                _lblStatusPill.ForeColor = Color.FromArgb(80, 215, 120);
                _pnlStatusPill.BackColor = Color.FromArgb(20, 48, 32);
            }
            else
            {
                _lblStatusPill.Text = "● Service: OFFLINE (Operating Local Cache)";
                _lblStatusPill.ForeColor = Color.FromArgb(245, 185, 65);
                _pnlStatusPill.BackColor = Color.FromArgb(48, 38, 22);
            }

            if (_menuStatus != null)
            {
                _menuStatus.Text = serviceOnline ? "● Fleet Service: ONLINE" : "● Fleet Service: OFFLINE";
            }
            if (_trayIcon != null)
            {
                var st = serviceOnline ? "ONLINE" : "OFFLINE";
                var bp = _emergencyBypassActive ? " [BYPASS]" : "";
                _trayIcon.Text = $"Print Server: {st}{bp}";
            }

            // 2. Ensure storage initialized
            if (_topRepo == null)
            {
                InitStorage();
            }

            // 3. Refresh Nodes Table
            List<NodeInfo>? nodes = null;
            if (_topRepo != null)
            {
                nodes = _topRepo.GetAllNodes();
            }
            else if (serviceOnline)
            {
                try
                {
                    nodes = await _http.GetFromJsonAsync<List<NodeInfo>>("http://127.0.0.1:8447/api/v1/nodes");
                }
                catch { }
            }

            if (nodes != null)
            {
                _gridNodes.Rows.Clear();
                foreach (var n in nodes)
                {
                    _gridNodes.Rows.Add(
                        n.NodeId,
                        n.FriendlyName,
                        n.HostIp,
                        n.Role + (n.IsDellAuthority ? " [Central Authority]" : ""),
                        n.IsOnline ? "ONLINE" : "UNREACHABLE",
                        n.LastHeartbeatUtc.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss")
                    );
                }
            }

            // 4. Refresh Printers Table
            List<PhysicalPrinter>? printers = null;
            if (_topRepo != null)
            {
                printers = _topRepo.GetAllPhysicalPrinters();
            }
            else if (serviceOnline)
            {
                try
                {
                    printers = await _http.GetFromJsonAsync<List<PhysicalPrinter>>("http://127.0.0.1:8447/api/v1/printers");
                }
                catch { }
            }

            if (printers != null)
            {
                _gridPrinters.Rows.Clear();
                foreach (var p in printers)
                {
                    _gridPrinters.Rows.Add(
                        p.FriendlyName,
                        p.Type.ToString(),
                        p.PrinterId,
                        p.HostNodeId + (string.IsNullOrEmpty(p.HostIp) ? "" : $" ({p.HostIp})"),
                        p.WindowsQueueName,
                        p.IsOnline ? "READY" : "OFFLINE"
                    );
                }
            }

            // 5. Refresh Jobs Table
            List<PrintJob>? jobs = null;
            if (_jobRepo != null)
            {
                jobs = _jobRepo.GetRecentJobs(50);
            }
            else if (serviceOnline)
            {
                try
                {
                    jobs = await _http.GetFromJsonAsync<List<PrintJob>>("http://127.0.0.1:8447/api/v1/jobs");
                }
                catch { }
            }

            if (jobs != null)
            {
                _gridJobs.Rows.Clear();
                foreach (var j in jobs)
                {
                    _gridJobs.Rows.Add(
                        j.JobId,
                        j.DocumentType,
                        j.LogicalDestination,
                        j.SourceNodeId,
                        j.Copies,
                        j.State.ToString().ToUpperInvariant(),
                        j.CreatedAtUtc.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss"),
                        j.StateDetail ?? ""
                    );
                }
            }
        }
        catch (Exception ex)
        {
            LogDiagnostic($"[REFRESH ERROR] {ex.Message}");
        }
    }

    private void UpdateBypassUi()
    {
        if (_emergencyBypassActive)
        {
            _btnEmergencyBypass.Text = "EMERGENCY BYPASS: ACTIVE";
            _btnEmergencyBypass.BackColor = Color.FromArgb(215, 45, 45);
        }
        else
        {
            _btnEmergencyBypass.Text = "EMERGENCY BYPASS: OFF";
            _btnEmergencyBypass.BackColor = Color.FromArgb(38, 135, 75);
        }

        if (_menuEmergencyBypass != null)
        {
            _menuEmergencyBypass.Checked = _emergencyBypassActive;
        }
    }

    private async void OnToggleBypassClicked(object? sender, EventArgs e)
    {
        var newState = !_emergencyBypassActive;
        var confirmMsg = newState
            ? "ACTIVATE EMERGENCY DIRECT PRINTING?\n\nThis bypasses all managed routing rules and sends unintercepted prints straight to hardware. Use during system maintenance or network failures only."
            : "DEACTIVATE EMERGENCY BYPASS?\n\nManaged routing rules and duplicate prevention will resume.";

        var dr = MessageBox.Show(confirmMsg, "Emergency Print Routing Bypass", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
        if (dr != DialogResult.Yes) return;

        try
        {
            var res = await _http.PostAsync($"http://127.0.0.1:8447/api/v1/admin/bypass?active={newState}", null);
            if (res.IsSuccessStatusCode)
            {
                _emergencyBypassActive = newState;
                UpdateBypassUi();
                LogDiagnostic($"[BYPASS] Toggled to {newState}");
            }
            else
            {
                MessageBox.Show("Failed to update bypass mode on PrintNode service.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Could not contact PrintNode service: {ex.Message}", "Connection Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private async Task SimulateOrnateVoucherAsync()
    {
        LogDiagnostic("[SIMULATION] Generating simulated Ornate GST Sales Voucher (2 copies)...");
        var jobId = $"SIM-ORN-{Guid.NewGuid():N}";
        var sampleVoucherText = $"--- SIMULATED ORNATE GST SALES VOUCHER ---\nInvoice: INV-2026-0988\nCustomer: Kailas Jewellery\nAmount: Rs. 145,200.00\nCopy: 1 (Office) / 2 (Customer)\n";
        var bytes = Encoding.UTF8.GetBytes(sampleVoucherText);
        var base64 = Convert.ToBase64String(bytes);

        var payload = new
        {
            jobId = jobId,
            idempotencyKey = $"idem-ornate-{jobId}",
            documentType = "GST_SALES_VOUCHER",
            destination = "OFFICE_A4",
            copies = 2,
            payloadType = "Raw",
            payloadBase64 = base64,
            sourceNodeId = "BILL02",
            sourceProcess = "ONX.exe",
            sourceUser = "billing_user"
        };

        try
        {
            var json = JsonSerializer.Serialize(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            var res = await _http.PostAsync("http://127.0.0.1:8447/api/v1/jobs", content);
            var respBody = await res.Content.ReadAsStringAsync();
            LogDiagnostic($"[SIMULATION RESULT] Ornate Voucher: {res.StatusCode} -> {respBody}");
            await RefreshAllAsync();
            MessageBox.Show(this, "Simulated Ornate GST Sales Voucher (2 copies) successfully dispatched!\n\nTarget Routing:\n• Copy 1 (Office) -> Laser Printer P1007\n• Copy 2 (Customer) -> 355 Letterhead Capture", "Simulation Dispatched", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            LogDiagnostic($"[SIMULATION] Operating in local node mode. Ledger logged: {payload.jobId} ({ex.Message})");
            _gridJobs.Rows.Insert(0, payload.jobId, payload.documentType, payload.destination, payload.sourceNodeId, payload.copies, "COMPLETED", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"), "Simulated local ledger dispatch");
            MessageBox.Show(this, "Simulated Ornate GST Sales Voucher (2 copies) registered in local print ledger!\n\nTarget Routing:\n• Copy 1 (Office) -> Laser Printer P1007\n• Copy 2 (Customer) -> 355 Letterhead Capture", "Simulation Dispatched", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
    }

    private async Task SimulateTabletEstimateAsync()
    {
        LogDiagnostic("[SIMULATION] Generating simulated Tablet Estimate Receipt...");
        var est = new EstimateReceipt
        {
            EstimateNumber = $"EST-{new Random().Next(1000, 9999)}",
            CustomerName = "Priya Sharma",
            CustomerPhone = "9845012345",
            SalesPerson = "Sales Staff 1",
            Items =
            [
                new EstimateItem { Description = "Gold Bangles (22K)", Purity = "22K", GrossWeightGrams = 24.500m, NetWeightGrams = 24.200m, RatePerGram = 6850m, MakingCharges = 8500m, TotalAmount = 174270m },
                new EstimateItem { Description = "Gold Ring", Purity = "22K", GrossWeightGrams = 4.200m, NetWeightGrams = 4.100m, RatePerGram = 6850m, MakingCharges = 1500m, TotalAmount = 29585m }
            ],
            Subtotal = 203855m,
            GstAmount = 6115.65m,
            GrandTotal = 209970.65m
        };

        var payload = new
        {
            jobId = $"SIM-EST-{Guid.NewGuid():N}",
            idempotencyKey = $"idem-est-{est.EstimateNumber}",
            sourceNodeId = "TAB-03",
            receipt = est
        };

        try
        {
            var json = JsonSerializer.Serialize(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            var res = await _http.PostAsync("http://127.0.0.1:8447/api/v1/jobs/estimate", content);
            var respBody = await res.Content.ReadAsStringAsync();
            LogDiagnostic($"[SIMULATION RESULT] Tablet Estimate: {res.StatusCode} -> {respBody}");
            await RefreshAllAsync();
            MessageBox.Show(this, $"Simulated Tablet Estimate Receipt ({est.EstimateNumber}) dispatched!\n\nTarget: Thermal Estimate Printer (58mm/80mm)\nCustomer: {est.CustomerName} - Total: Rs. {est.GrandTotal:N2}", "Simulation Dispatched", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            LogDiagnostic($"[SIMULATION] Operating in local node mode. Ledger logged: {payload.jobId} ({ex.Message})");
            _gridJobs.Rows.Insert(0, payload.jobId, "ESTIMATE_RECEIPT", "ESTIMATE_THERMAL", payload.sourceNodeId, 1, "COMPLETED", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"), $"Simulated local ledger receipt {est.EstimateNumber}");
            MessageBox.Show(this, $"Simulated Tablet Estimate Receipt ({est.EstimateNumber}) registered in local ledger!\n\nTarget: Thermal Estimate Printer (58mm/80mm)\nCustomer: {est.CustomerName} - Total: Rs. {est.GrandTotal:N2}", "Simulation Dispatched", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
    }

    private async Task RunDiagnosticTestTicketAsync()
    {
        var localPrinters = PrinterDiscovery.DiscoverLocalPrinters();
        if (localPrinters.Count == 0)
        {
            LogDiagnostic("[DIAGNOSTIC] No local physical printers discovered on this node.");
            MessageBox.Show(this, "No local printers discovered on this system to send test ticket to.", "Test Print", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var p = localPrinters.FirstOrDefault(x => x.IsDefault) ?? localPrinters[0];
        LogDiagnostic($"[DIAGNOSTIC] Spooling test print ticket to {p.Name}...");

        bool printed = false;
        try
        {
            var res = await _http.PostAsync($"http://127.0.0.1:8447/api/v1/admin/test-print?printerName={Uri.EscapeDataString(p.Name)}", null);
            if (res.IsSuccessStatusCode)
            {
                var respBody = await res.Content.ReadAsStringAsync();
                LogDiagnostic($"[DIAGNOSTIC RESULT] Spooler via Node Service: {res.StatusCode} -> {respBody}");
                printed = true;
            }
        }
        catch { }

        if (!printed)
        {
            var testText = $"--- AMBIC PRINT SERVER TEST PRINT ---\r\nNode: {Environment.MachineName}\r\nPrinter: {p.Name}\r\nTimestamp: {DateTime.Now:yyyy-MM-dd HH:mm:ss}\r\nStatus: SUCCESS (Direct Spool)\r\n\r\n\r\n";
            var testData = Encoding.UTF8.GetBytes(testText);
            var (success, error) = Win32Spooler.SendRawBytes(p.Name, testData, "Print Server Diagnostic Test");
            if (success)
            {
                LogDiagnostic($"[DIAGNOSTIC RESULT] Spooled directly to '{p.Name}' via Win32.");
                printed = true;
            }
            else
            {
                LogDiagnostic($"[DIAGNOSTIC ERROR] Win32 direct spool failed: {error}");
                MessageBox.Show(this, $"Failed to print test ticket to '{p.Name}': {error}", "Test Print Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
        }

        MessageBox.Show(this, $"Diagnostic test print ticket successfully spooled to printer '{p.Name}'!", "Test Print Spooled", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    private void BuildSmartRoutingTab(TabPage tab)
    {
        var container = new Panel { Dock = DockStyle.Fill, Padding = new Padding(14) };

        // Bottom: Log Card
        var pnlBottom = new Panel { Dock = DockStyle.Bottom, Height = 165, Padding = new Padding(0, 8, 0, 0) };
        var cardLogs = CreateModernCard("Live Window Automation & Spool Stream", out var bodyLogs);
        _txtWatcherLog = new TextBox
        {
            Dock = DockStyle.Fill,
            Multiline = true,
            ScrollBars = ScrollBars.Vertical,
            ReadOnly = true,
            BackColor = Color.FromArgb(16, 20, 28),
            ForeColor = Color.FromArgb(145, 215, 175),
            Font = new Font("Consolas", 9f),
            BorderStyle = BorderStyle.None
        };
        bodyLogs.Controls.Add(_txtWatcherLog);
        pnlBottom.Controls.Add(cardLogs);

        // Top: Station Card (Height 220 to give full breathing room for 3 rows)
        var pnlTop = new Panel { Dock = DockStyle.Top, Height = 220, Padding = new Padding(0, 0, 0, 8) };
        var cardStation = CreateModernCard("Station Split & Manual Overrides (Workstation Topology Settings)", out var bodyStation);

        var tblStation = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 5,
            RowCount = 3,
            Padding = new Padding(12, 6, 12, 6)
        };
        tblStation.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 16f));
        tblStation.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 24f));
        tblStation.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 16f));
        tblStation.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 26f));
        tblStation.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 18f));

        tblStation.RowStyles.Add(new RowStyle(SizeType.Absolute, 38f));
        tblStation.RowStyles.Add(new RowStyle(SizeType.Absolute, 38f));
        tblStation.RowStyles.Add(new RowStyle(SizeType.Absolute, 42f));

        // Row 0
        var lblRole = new Label { Text = "Workstation Role:", AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, Font = new Font("Segoe UI", 9f, FontStyle.Bold), ForeColor = Color.FromArgb(40, 50, 70) };
        _cmbPcRole = new ComboBox { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
        _cmbPcRole.Items.AddRange(["Master Spooler Hub", "Billing Station (PC-01)", "Billing Station (PC-02)", "Satellite Terminal", "Standalone Node"]);
        _cmbPcRole.SelectedIndex = 0;

        var lblBoth = new Label { Text = "Both Copies Mode:", AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, Font = new Font("Segoe UI", 9f, FontStyle.Bold), ForeColor = Color.FromArgb(40, 50, 70) };
        _cmbBothMode = new ComboBox { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
        _cmbBothMode.Items.AddRange([
            "Automatic Split (Copy 1 -> P1007, Copy 2+ -> HP 355)",
            "Both copies -> Laser Printer P1007 (Office/Accounts)",
            "Both copies -> Customer HP 355 (Customer Front)",
            "Rule Target Only"
        ]);
        _cmbBothMode.SelectedIndex = 0;

        _chkMasterEnable = new CheckBox
        {
            Text = "Master Auto-Routing",
            AutoSize = true,
            Checked = true,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            ForeColor = Color.FromArgb(20, 110, 40),
            Anchor = AnchorStyles.Left
        };

        tblStation.Controls.Add(lblRole, 0, 0);
        tblStation.Controls.Add(_cmbPcRole, 1, 0);
        tblStation.Controls.Add(lblBoth, 2, 0);
        tblStation.Controls.Add(_cmbBothMode, 3, 0);
        tblStation.Controls.Add(_chkMasterEnable, 4, 0);

        // Row 1
        var lblC1Def = new Label { Text = "Default Copy 1 Printer:", AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, ForeColor = Color.FromArgb(60, 70, 90) };
        _txtCopy1Default = new TextBox { Dock = DockStyle.Fill, Text = "Laser Printer P1007" };

        var lblC2Def = new Label { Text = "Default Copy 2+ Printer:", AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, ForeColor = Color.FromArgb(60, 70, 90) };
        _txtCopy2Default = new TextBox { Dock = DockStyle.Fill, Text = "Customer HP 355 Duplex Letterhead" };

        _lblBothWarning = new Label
        {
            Text = "⚠️ Override active: All copies routed to single printer",
            ForeColor = Color.FromArgb(210, 50, 20),
            Font = new Font("Segoe UI", 8.25f, FontStyle.Bold),
            AutoSize = true,
            Anchor = AnchorStyles.Left,
            Visible = false
        };

        _cmbBothMode.SelectedIndexChanged += (s, e) =>
        {
            _lblBothWarning.Visible = _cmbBothMode.SelectedIndex == 1 || _cmbBothMode.SelectedIndex == 2;
        };

        tblStation.Controls.Add(lblC1Def, 0, 1);
        tblStation.Controls.Add(_txtCopy1Default, 1, 1);
        tblStation.Controls.Add(lblC2Def, 2, 1);
        tblStation.Controls.Add(_txtCopy2Default, 3, 1);
        tblStation.Controls.Add(_lblBothWarning, 4, 1);

        // Row 2
        var lblF1 = new Label { Text = "Force Copy 1 Manual:", AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, ForeColor = Color.FromArgb(60, 70, 90) };
        _txtForceCopy1 = new TextBox { Dock = DockStyle.Fill, PlaceholderText = "(none - follow rules)" };

        var lblF2 = new Label { Text = "Force Copy 2 Manual:", AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, ForeColor = Color.FromArgb(60, 70, 90) };
        _txtForceCopy2 = new TextBox { Dock = DockStyle.Fill, PlaceholderText = "(none - follow rules)" };

        var btnSaveStation = new Button
        {
            Text = "💾 Save Station Settings",
            Dock = DockStyle.Fill,
            Height = 34,
            BackColor = Color.FromArgb(24, 115, 220),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Margin = new Padding(4, 2, 4, 2),
            Cursor = Cursors.Hand
        };
        btnSaveStation.FlatAppearance.BorderSize = 0;
        btnSaveStation.Click += (s, e) => SaveStationSettings();

        tblStation.Controls.Add(lblF1, 0, 2);
        tblStation.Controls.Add(_txtForceCopy1, 1, 2);
        tblStation.Controls.Add(lblF2, 2, 2);
        tblStation.Controls.Add(_txtForceCopy2, 3, 2);
        tblStation.Controls.Add(btnSaveStation, 4, 2);

        bodyStation.Controls.Add(tblStation);
        pnlTop.Controls.Add(cardStation);

        // Middle Card: Rules
        var cardRules = CreateModernCard("Program & Voucher Routing Rules (Automated Print Invariants)", out var bodyRules);

        // Toolbar
        var pnlToolbar = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 44,
            Padding = new Padding(8, 6, 8, 4),
            BackColor = Color.FromArgb(245, 247, 251),
            WrapContents = false
        };

        var btnAddOrnate = new Button
        {
            Text = "+ Add Ornate Voucher Rule",
            Height = 32,
            Width = 205,
            BackColor = Color.FromArgb(38, 135, 75),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Cursor = Cursors.Hand,
            Margin = new Padding(0, 0, 10, 0)
        };
        btnAddOrnate.FlatAppearance.BorderSize = 0;
        btnAddOrnate.Click += (s, e) => AddOrnateRule();

        var btnAddCustom = new Button
        {
            Text = "+ Add Custom Program Rule...",
            Height = 32,
            Width = 215,
            BackColor = Color.FromArgb(24, 115, 220),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Cursor = Cursors.Hand,
            Margin = new Padding(0, 0, 10, 0)
        };
        btnAddCustom.FlatAppearance.BorderSize = 0;
        btnAddCustom.Click += (s, e) => AddCustomProgramRule();

        var btnRemove = new Button
        {
            Text = "- Remove Selected",
            Height = 32,
            Width = 145,
            BackColor = Color.FromArgb(210, 60, 60),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Cursor = Cursors.Hand,
            Margin = new Padding(0, 0, 10, 0)
        };
        btnRemove.FlatAppearance.BorderSize = 0;
        btnRemove.Click += (s, e) => RemoveSelectedRule();

        var btnCapture = new Button
        {
            Text = "📷 Capture Window Template...",
            Height = 32,
            Width = 230,
            BackColor = Color.FromArgb(110, 60, 180),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Cursor = Cursors.Hand,
            Margin = new Padding(0, 0, 10, 0)
        };
        btnCapture.FlatAppearance.BorderSize = 0;
        btnCapture.Click += (s, e) => CaptureCurrentTemplate();

        var btnSaveRules = new Button
        {
            Text = "💾 Save All Rules",
            Height = 32,
            Width = 140,
            BackColor = Color.FromArgb(18, 140, 100),
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9f, FontStyle.Bold),
            FlatStyle = FlatStyle.Flat,
            Cursor = Cursors.Hand
        };
        btnSaveRules.FlatAppearance.BorderSize = 0;
        btnSaveRules.Click += (s, e) => SaveAllRules();

        pnlToolbar.Controls.AddRange([btnAddOrnate, btnAddCustom, btnRemove, btnCapture, btnSaveRules]);

        // Grid
        _gridRules = CreateStyledGrid();
        _gridRules.ReadOnly = false;
        _gridRules.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
        _gridRules.AllowUserToAddRows = false;
        _gridRules.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
        _gridRules.MultiSelect = false;
        _gridRules.ScrollBars = ScrollBars.Both;
        _gridRules.RowTemplate.Height = 42;
        _gridRules.ColumnHeadersHeight = 48;
        _gridRules.DefaultCellStyle.Font = new Font("Segoe UI", 9.25f);
        _gridRules.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleLeft;
        _gridRules.DefaultCellStyle.Padding = new Padding(8, 2, 8, 2);
        _gridRules.ColumnHeadersDefaultCellStyle.Padding = new Padding(8, 2, 8, 2);
        _gridRules.DefaultCellStyle.SelectionBackColor = Color.FromArgb(220, 235, 252);
        _gridRules.DefaultCellStyle.SelectionForeColor = Color.FromArgb(20, 35, 55);

        _gridRules.Columns.Add("RuleName", "Rule Name");
        _gridRules.Columns.Add("TargetProgram", "Target Program");
        _gridRules.Columns.Add("WindowTitle", "Window Title");
        _gridRules.Columns.Add("Copies", "Copies");
        _gridRules.Columns.Add("ReferenceTemplate", "Visual Template");
        _gridRules.Columns.Add("Copy1Printer", "Copy 1 Printer");
        _gridRules.Columns.Add("LaterPrinter", "Copies 2+ Printer");
        _gridRules.Columns.Add("Overlay", "Letterhead / Overlay");

        foreach (DataGridViewColumn col in _gridRules.Columns)
        {
            col.ReadOnly = true;
        }

        var chkCol = new DataGridViewCheckBoxColumn
        {
            Name = "Enabled",
            HeaderText = "Enabled",
            Width = 70,
            AutoSizeMode = DataGridViewAutoSizeColumnMode.None,
            ReadOnly = false
        };
        _gridRules.Columns.Add(chkCol);

        _gridRules.CurrentCellDirtyStateChanged += (s, e) =>
        {
            if (_gridRules.IsCurrentCellDirty)
            {
                _gridRules.CommitEdit(DataGridViewDataErrorContexts.Commit);
            }
        };

        _gridRules.CellValueChanged += (s, e) =>
        {
            if (e.RowIndex >= 0 && e.ColumnIndex >= 0 && _gridRules.Columns[e.ColumnIndex].Name == "Enabled")
            {
                var row = _gridRules.Rows[e.RowIndex];
                if (row.Tag is RoutingRule rule && row.Cells["Enabled"].Value is bool b)
                {
                    rule.Enabled = b;
                }
            }
        };

        _gridRules.Columns["RuleName"].AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill;
        _gridRules.Columns["RuleName"].FillWeight = 26;
        _gridRules.Columns["RuleName"].MinimumWidth = 220;

        _gridRules.Columns["TargetProgram"].AutoSizeMode = DataGridViewAutoSizeColumnMode.AllCells;
        _gridRules.Columns["TargetProgram"].MinimumWidth = 110;

        _gridRules.Columns["WindowTitle"].AutoSizeMode = DataGridViewAutoSizeColumnMode.AllCells;
        _gridRules.Columns["WindowTitle"].MinimumWidth = 120;

        _gridRules.Columns["Copies"].AutoSizeMode = DataGridViewAutoSizeColumnMode.AllCells;
        _gridRules.Columns["Copies"].MinimumWidth = 65;

        _gridRules.Columns["ReferenceTemplate"].AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill;
        _gridRules.Columns["ReferenceTemplate"].FillWeight = 24;
        _gridRules.Columns["ReferenceTemplate"].MinimumWidth = 200;

        _gridRules.Columns["Copy1Printer"].AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill;
        _gridRules.Columns["Copy1Printer"].FillWeight = 25;
        _gridRules.Columns["Copy1Printer"].MinimumWidth = 180;

        _gridRules.Columns["LaterPrinter"].AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill;
        _gridRules.Columns["LaterPrinter"].FillWeight = 25;
        _gridRules.Columns["LaterPrinter"].MinimumWidth = 180;

        _gridRules.Columns["Overlay"].AutoSizeMode = DataGridViewAutoSizeColumnMode.AllCells;
        _gridRules.Columns["Overlay"].MinimumWidth = 140;

        bodyRules.Controls.Add(_gridRules);
        bodyRules.Controls.Add(pnlToolbar);
        pnlToolbar.SendToBack();
        _gridRules.BringToFront();

        // Assemble into container in strict docking order
        container.Controls.Add(cardRules);
        container.Controls.Add(pnlTop);
        container.Controls.Add(pnlBottom);
        pnlTop.SendToBack();
        pnlBottom.SendToBack();
        cardRules.BringToFront();

        tab.Controls.Add(container);
    }

    private void LoadHubConfigToUi()
    {
        try
        {
            _hubConfig ??= _rulesStore?.LoadHubConfig() ?? DefaultTopology.CreateDefaultHubConfig();

            _cmbPcRole.Text = _hubConfig.WorkstationRole;
            _chkMasterEnable.Checked = _hubConfig.MasterRoutingEnabled;
            _txtCopy1Default.Text = _hubConfig.DefaultCopy1Printer;
            _txtCopy2Default.Text = _hubConfig.DefaultCopy2Printer;

            _cmbBothMode.SelectedIndex = _hubConfig.BothCopiesMode switch
            {
                "BOTH_P1007" => 1,
                "BOTH_P355" => 2,
                "RULE_ONLY" => 3,
                _ => 0
            };
            _lblBothWarning.Visible = _cmbBothMode.SelectedIndex == 1 || _cmbBothMode.SelectedIndex == 2;

            _txtForceCopy1.Text = _hubConfig.ForceCopy1Printer ?? "";
            _txtForceCopy2.Text = _hubConfig.ForceCopy2Printer ?? "";

            PopulateRulesGrid();
        }
        catch (Exception ex)
        {
            LogWatcher($"[ERROR] Loading Hub config: {ex.Message}");
        }
    }

    private void PopulateRulesGrid()
    {
        if (_gridRules == null || _hubConfig == null) return;
        _gridRules.Rows.Clear();

        foreach (var rule in _hubConfig.Rules)
        {
            var rowIndex = _gridRules.Rows.Add(
                rule.Name,
                rule.TargetProgram ?? rule.Source.Process,
                rule.WindowTitleMatch ?? rule.Source.Screen ?? "*",
                rule.RequiredCopies > 0 ? rule.RequiredCopies.ToString() : (rule.Source.Copies.HasValue ? rule.Source.Copies.ToString() : "Any"),
                rule.ReferenceTemplate ?? "",
                rule.Copy1Printer ?? "(default)",
                rule.LaterPrinter ?? "(default)",
                rule.LetterheadOverlay ?? "NONE",
                rule.Enabled
            );
            _gridRules.Rows[rowIndex].Tag = rule;
        }
    }

    private void SaveStationSettings()
    {
        try
        {
            _hubConfig ??= new RouterHubConfig();
            _hubConfig.WorkstationRole = _cmbPcRole.Text;
            _hubConfig.MasterRoutingEnabled = _chkMasterEnable.Checked;
            _hubConfig.DefaultCopy1Printer = _txtCopy1Default.Text.Trim();
            _hubConfig.DefaultCopy2Printer = _txtCopy2Default.Text.Trim();

            _hubConfig.BothCopiesMode = _cmbBothMode.SelectedIndex switch
            {
                1 => "BOTH_P1007",
                2 => "BOTH_P355",
                3 => "RULE_ONLY",
                _ => "SPLIT"
            };

            _hubConfig.ForceCopy1Printer = string.IsNullOrWhiteSpace(_txtForceCopy1.Text) ? null : _txtForceCopy1.Text.Trim();
            _hubConfig.ForceCopy2Printer = string.IsNullOrWhiteSpace(_txtForceCopy2.Text) ? null : _txtForceCopy2.Text.Trim();

            _rulesStore?.SaveHubConfig(_hubConfig);
            _captureWatcher.Start(_hubConfig);

            try
            {
                _ = _http.PostAsync("http://127.0.0.1:8447/api/v1/admin/reload-rules", null);
            }
            catch { }

            if (_menuAutoRouting != null) _menuAutoRouting.Checked = _chkMasterEnable.Checked;
            LogWatcher($"[CONFIG] Station settings saved successfully. Role={_hubConfig.WorkstationRole}, Mode={_hubConfig.BothCopiesMode}");
            MessageBox.Show(this, "Station topology and split settings saved successfully!", "Print Server", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            LogWatcher($"[ERROR] Save station settings: {ex.Message}");
            MessageBox.Show(this, $"Failed to save station settings: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void SaveAllRules()
    {
        try
        {
            if (_hubConfig == null) return;
            var updatedList = new List<RoutingRule>();

            foreach (DataGridViewRow row in _gridRules.Rows)
            {
                if (row.IsNewRow) continue;
                var rule = row.Tag as RoutingRule ?? new RoutingRule
                {
                    Id = $"RULE-{Guid.NewGuid():N}".Substring(0, 16).ToUpperInvariant()
                };

                rule.Name = row.Cells["RuleName"].Value?.ToString() ?? "Custom Rule";
                rule.TargetProgram = row.Cells["TargetProgram"].Value?.ToString() ?? "*";
                rule.WindowTitleMatch = row.Cells["WindowTitle"].Value?.ToString() ?? "*";

                var copiesStr = row.Cells["Copies"].Value?.ToString() ?? "";
                if (int.TryParse(copiesStr, out var cVal) && cVal > 0)
                {
                    rule.RequiredCopies = cVal;
                    rule.Source.Copies = cVal;
                }
                else
                {
                    rule.RequiredCopies = 0;
                    rule.Source.Copies = null;
                }

                rule.ReferenceTemplate = row.Cells["ReferenceTemplate"].Value?.ToString();
                rule.Copy1Printer = row.Cells["Copy1Printer"].Value?.ToString();
                rule.LaterPrinter = row.Cells["LaterPrinter"].Value?.ToString();
                rule.LetterheadOverlay = row.Cells["Overlay"].Value?.ToString();
                rule.Enabled = row.Cells["Enabled"].Value is bool b ? b : true;

                rule.Source.Process = rule.TargetProgram;
                rule.Source.Screen = rule.WindowTitleMatch;

                updatedList.Add(rule);
            }

            _hubConfig.Rules = updatedList;
            _rulesStore?.SaveHubConfig(_hubConfig);

            try
            {
                _ = _http.PostAsync("http://127.0.0.1:8447/api/v1/admin/reload-rules", null);
            }
            catch { }

            LogWatcher($"[CONFIG] Successfully saved {updatedList.Count} program & voucher routing rules.");
            MessageBox.Show(this, $"Successfully saved {updatedList.Count} routing rules!", "Print Server", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            LogWatcher($"[ERROR] Save rules failed: {ex.Message}");
            MessageBox.Show(this, $"Failed to save rules: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void AddOrnateRule()
    {
        var newRule = new RoutingRule
        {
            Id = $"RULE-{Guid.NewGuid():N}".Substring(0, 16).ToUpperInvariant(),
            Name = "Ornate GST Sales Voucher (2 Copies)",
            TargetProgram = "ONX.exe",
            WindowTitleMatch = "Voucher",
            RequiredCopies = 2,
            ReferenceTemplate = "office-sales-voucher-format-reference.png",
            Copy1Printer = "Laser Printer P1007",
            LaterPrinter = "Customer HP 355 Duplex Letterhead",
            LetterheadOverlay = "DUPLEX_FRONT_BACK",
            Duplex = true,
            Enabled = true,
            OnMismatch = "P355_ONLY",
            Source = new RuleSourceCriteria { Process = "ONX.exe", Screen = "Voucher", Copies = 2 },
            Actions =
            [
                new RuleAction { CopyNumber = 1, Destination = "Laser Printer P1007" },
                new RuleAction { CopyNumber = 2, Destination = "Customer HP 355 Duplex Letterhead", Duplex = true, Transform = "CUSTOMER_LETTERHEAD_DUPLEX" }
            ]
        };

        _hubConfig?.Rules.Add(newRule);
        var rowIndex = _gridRules.Rows.Add(
            newRule.Name,
            newRule.TargetProgram,
            newRule.WindowTitleMatch,
            "2",
            newRule.ReferenceTemplate,
            newRule.Copy1Printer,
            newRule.LaterPrinter,
            newRule.LetterheadOverlay,
            newRule.Enabled
        );
        _gridRules.Rows[rowIndex].Tag = newRule;
        _gridRules.ClearSelection();
        _gridRules.Rows[rowIndex].Selected = true;
        LogWatcher($"[RULE ADDED] Added standard Ornate rule: '{newRule.Name}'");
    }

    private void AddCustomProgramRule()
    {
        var printerList = new List<string>
        {
            "Laser Printer P1007",
            "Customer HP 355 Duplex Letterhead",
            "Thermal Estimate Printer",
            "TSC Barcode TE244",
            "Zebra Tag Printer"
        };

        try
        {
            var discovered = PrinterDiscovery.DiscoverLocalPrinters();
            foreach (var p in discovered)
            {
                if (!printerList.Contains(p.Name)) printerList.Add(p.Name);
            }
        }
        catch { }

        using var dlg = new FormAddProgramRule(printerList);
        if (dlg.ShowDialog(this) == DialogResult.OK && dlg.ResultRule != null)
        {
            var rule = dlg.ResultRule;
            _hubConfig?.Rules.Add(rule);
            var rowIndex = _gridRules.Rows.Add(
                rule.Name,
                rule.TargetProgram,
                rule.WindowTitleMatch,
                rule.RequiredCopies > 0 ? rule.RequiredCopies.ToString() : "Any",
                rule.ReferenceTemplate ?? "",
                rule.Copy1Printer ?? "(default)",
                rule.LaterPrinter ?? "(default)",
                rule.LetterheadOverlay ?? "NONE",
                rule.Enabled
            );
            _gridRules.Rows[rowIndex].Tag = rule;
            _gridRules.ClearSelection();
            _gridRules.Rows[rowIndex].Selected = true;
            LogWatcher($"[RULE ADDED] Added custom program rule: '{rule.Name}' for {rule.TargetProgram}");
        }
    }

    private void RemoveSelectedRule()
    {
        if (_gridRules.SelectedRows.Count == 0)
        {
            MessageBox.Show(this, "Please select a rule to remove.", "Print Server", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var row = _gridRules.SelectedRows[0];
        var name = row.Cells["RuleName"].Value?.ToString() ?? "selected rule";
        if (MessageBox.Show(this, $"Are you sure you want to remove rule '{name}'?", "Confirm Delete", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) == DialogResult.Yes)
        {
            if (row.Tag is RoutingRule rule && _hubConfig != null)
            {
                _hubConfig.Rules.Remove(rule);
            }
            _gridRules.Rows.Remove(row);
            LogWatcher($"[RULE REMOVED] Removed rule: '{name}'");
        }
    }

    private async void CaptureCurrentTemplate()
    {
        if (_gridRules.SelectedRows.Count == 0)
        {
            MessageBox.Show(this, "Please select a rule in the table to associate with the captured template.", "Print Server", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var selectedRow = _gridRules.SelectedRows[0];
        var ruleName = selectedRow.Cells["RuleName"].Value?.ToString() ?? "rule";
        var cleanPrefix = string.Join("_", ruleName.Split(Path.GetInvalidFileNameChars())).Replace(" ", "_").ToLowerInvariant();

        MessageBox.Show(this,
            "When you click OK, you have 3 seconds to switch to and activate the target application or voucher window.\n\nPrint Server will capture that window and save it as reference template.",
            "Capture Window Template",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information);

        LogWatcher("[CAPTURE] 3 second timer started... bring target application to the front now!");
        await Task.Delay(3000);

        var foregroundHwnd = GetForegroundWindow();
        if (foregroundHwnd == IntPtr.Zero || foregroundHwnd == Handle)
        {
            var ornateWindows = OrnateWindowWatcher.FindOrnateVoucherWindows();
            if (ornateWindows.Count > 0)
            {
                foregroundHwnd = ornateWindows[0].WindowHandle;
            }
        }

        if (foregroundHwnd == IntPtr.Zero || foregroundHwnd == Handle)
        {
            LogWatcher("[CAPTURE ERROR] Could not locate an external foreground application window.");
            MessageBox.Show(this, "Could not capture window: Foreground window was the Print Server itself. Please ensure target window is open and active.", "Capture Failed", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var savedFile = OrnateWindowWatcher.CaptureWindowToFile(foregroundHwnd, _assetsDir, cleanPrefix);
        if (!string.IsNullOrEmpty(savedFile))
        {
            selectedRow.Cells["ReferenceTemplate"].Value = savedFile;
            if (selectedRow.Tag is RoutingRule rule)
            {
                rule.ReferenceTemplate = savedFile;
            }
            LogWatcher($"[CAPTURE SUCCESS] Captured template window to '{savedFile}'. Linked to rule '{ruleName}'.");
            MessageBox.Show(this, $"Successfully captured window template:\n\n{savedFile}\n\nAssigned to rule '{ruleName}'. Don't forget to click 'Save All Rules'.", "Template Captured", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        else
        {
            LogWatcher("[CAPTURE ERROR] Window capture API returned empty. Check window permissions.");
        }
    }

    private string _lastLoggedWindowKey = "";

    private void ScanActiveWindows()
    {
        try
        {
            _dialogInterceptor.ScanAndIntercept(_hubConfig);
        }
        catch { }
    }

    private void LogWatcher(string message)
    {
        var entry = $"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}";

        try
        {
            var logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
            Directory.CreateDirectory(logDir);
            File.AppendAllText(Path.Combine(logDir, "watcher.log"), entry);
        }
        catch { }

        if (_txtWatcherLog == null) return;
        if (_txtWatcherLog.IsDisposed) return;

        try
        {
            if (_txtWatcherLog.InvokeRequired)
            {
                _txtWatcherLog.BeginInvoke(() =>
                {
                    _txtWatcherLog.AppendText(entry);
                    if (_txtWatcherLog.TextLength > 30000)
                        _txtWatcherLog.Text = _txtWatcherLog.Text.Substring(_txtWatcherLog.TextLength - 15000);
                });
            }
            else
            {
                _txtWatcherLog.AppendText(entry);
                if (_txtWatcherLog.TextLength > 30000)
                    _txtWatcherLog.Text = _txtWatcherLog.Text.Substring(_txtWatcherLog.TextLength - 15000);
            }
        }
        catch { }
    }
}

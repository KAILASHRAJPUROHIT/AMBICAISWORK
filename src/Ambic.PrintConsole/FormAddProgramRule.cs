using System.Diagnostics;
using Ambic.PrintCore.Models;

namespace Ambic.PrintConsole;

public class FormAddProgramRule : Form
{
    private readonly TextBox _txtLabel;
    private readonly ComboBox _cmbProcess;
    private readonly TextBox _txtWindowTitle;
    private readonly NumericUpDown _numCopies;
    private readonly CheckBox _chkAnyCopies;
    private readonly TextBox _txtTemplate;
    private readonly ComboBox _cmbCopy1;
    private readonly ComboBox _cmbLater;
    private readonly ComboBox _cmbOverlay;
    private readonly CheckBox _chkDuplex;
    private readonly CheckBox _chkEnabled;
    private readonly Button _btnSave;
    private readonly Button _btnCancel;

    public RoutingRule ResultRule { get; private set; } = null!;

    public FormAddProgramRule(List<string> availablePrinters, RoutingRule? existingRule = null)
    {
        Text = existingRule == null ? "Add Program Routing Rule" : "Edit Program Routing Rule";
        Width = 580;
        Height = 520;
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        Font = new Font("Segoe UI", 9.25f, FontStyle.Regular);
        BackColor = Color.FromArgb(248, 250, 252);

        int lblWidth = 160;
        int inputLeft = 180;
        int inputWidth = 350;
        int y = 20;
        int spacing = 38;

        // Rule Label
        var lbl1 = new Label { Text = "Rule Label / Name:", Left = 20, Top = y + 3, Width = lblWidth };
        _txtLabel = new TextBox { Left = inputLeft, Top = y, Width = inputWidth, Text = existingRule?.Name ?? "Custom Program Rule" };
        Controls.AddRange([lbl1, _txtLabel]);
        y += spacing;

        // Target Program
        var lbl2 = new Label { Text = "Target Program / Process:", Left = 20, Top = y + 3, Width = lblWidth };
        _cmbProcess = new ComboBox { Left = inputLeft, Top = y, Width = inputWidth, DropDownStyle = ComboBoxStyle.DropDown };
        _cmbProcess.Items.Add("* (Any Application)");
        _cmbProcess.Items.Add("ONX.exe (Ornate ERP)");
        _cmbProcess.Items.Add("AcroRd32.exe (Adobe Acrobat Reader)");
        _cmbProcess.Items.Add("chrome.exe (Google Chrome)");
        _cmbProcess.Items.Add("msedge.exe (Microsoft Edge)");
        _cmbProcess.Items.Add("EXCEL.EXE (Microsoft Excel)");
        
        // Populate running processes
        try
        {
            var running = Process.GetProcesses()
                .Select(p => p.ProcessName + ".exe")
                .Distinct()
                .OrderBy(p => p);
            foreach (var p in running)
            {
                if (!_cmbProcess.Items.Contains(p)) _cmbProcess.Items.Add(p);
            }
        }
        catch { }

        _cmbProcess.Text = existingRule?.TargetProgram ?? "ONX.exe";
        Controls.AddRange([lbl2, _cmbProcess]);
        y += spacing;

        // Window Title Match
        var lbl3 = new Label { Text = "Window Title Match:", Left = 20, Top = y + 3, Width = lblWidth };
        _txtWindowTitle = new TextBox { Left = inputLeft, Top = y, Width = inputWidth, Text = existingRule?.WindowTitleMatch ?? "*" };
        Controls.AddRange([lbl3, _txtWindowTitle]);
        y += spacing;

        // Required Copies
        var lbl4 = new Label { Text = "Required Copy Count:", Left = 20, Top = y + 3, Width = lblWidth };
        _numCopies = new NumericUpDown { Left = inputLeft, Top = y, Width = 100, Minimum = 1, Maximum = 99, Value = Math.Max(1, existingRule?.RequiredCopies ?? 2) };
        _chkAnyCopies = new CheckBox { Text = "Any copy count (match all)", Left = inputLeft + 120, Top = y + 2, AutoSize = true, Checked = (existingRule?.RequiredCopies ?? 2) == 0 };
        _chkAnyCopies.CheckedChanged += (s, e) => _numCopies.Enabled = !_chkAnyCopies.Checked;
        if (_chkAnyCopies.Checked) _numCopies.Enabled = false;
        Controls.AddRange([lbl4, _numCopies, _chkAnyCopies]);
        y += spacing;

        // Reference Template
        var lbl5 = new Label { Text = "Visual Reference Template:", Left = 20, Top = y + 3, Width = lblWidth };
        _txtTemplate = new TextBox { Left = inputLeft, Top = y, Width = inputWidth, Text = existingRule?.ReferenceTemplate ?? "" };
        Controls.AddRange([lbl5, _txtTemplate]);
        y += spacing;

        // Copy 1 Printer
        var lbl6 = new Label { Text = "Copy 1 Printer (Office):", Left = 20, Top = y + 3, Width = lblWidth };
        _cmbCopy1 = new ComboBox { Left = inputLeft, Top = y, Width = inputWidth, DropDownStyle = ComboBoxStyle.DropDownList };
        _cmbCopy1.Items.Add("(use configured default)");
        foreach (var p in availablePrinters) if (!_cmbCopy1.Items.Contains(p)) _cmbCopy1.Items.Add(p);
        _cmbCopy1.Text = existingRule?.Copy1Printer ?? "(use configured default)";
        Controls.AddRange([lbl6, _cmbCopy1]);
        y += spacing;

        // Later Copies Printer
        var lbl7 = new Label { Text = "Copies 2+ Printer (Customer):", Left = 20, Top = y + 3, Width = lblWidth };
        _cmbLater = new ComboBox { Left = inputLeft, Top = y, Width = inputWidth, DropDownStyle = ComboBoxStyle.DropDownList };
        _cmbLater.Items.Add("(use configured default)");
        foreach (var p in availablePrinters) if (!_cmbLater.Items.Contains(p)) _cmbLater.Items.Add(p);
        _cmbLater.Text = existingRule?.LaterPrinter ?? "(use configured default)";
        Controls.AddRange([lbl7, _cmbLater]);
        y += spacing;

        // Letterhead Overlay & Duplex
        var lbl8 = new Label { Text = "Digital Letterhead Overlay:", Left = 20, Top = y + 3, Width = lblWidth };
        _cmbOverlay = new ComboBox { Left = inputLeft, Top = y, Width = 200, DropDownStyle = ComboBoxStyle.DropDownList };
        _cmbOverlay.Items.AddRange(["DUPLEX_FRONT_BACK", "FRONT_ONLY", "NONE"]);
        _cmbOverlay.Text = existingRule?.LetterheadOverlay ?? "DUPLEX_FRONT_BACK";

        _chkDuplex = new CheckBox { Text = "Hardware Duplex", Left = inputLeft + 220, Top = y + 2, AutoSize = true, Checked = existingRule?.Duplex ?? true };
        Controls.AddRange([lbl8, _cmbOverlay, _chkDuplex]);
        y += spacing;

        // Enabled
        _chkEnabled = new CheckBox { Text = "Enable this routing rule immediately", Left = inputLeft, Top = y, AutoSize = true, Checked = existingRule?.Enabled ?? true };
        Controls.Add(_chkEnabled);
        y += spacing + 10;

        // Buttons
        _btnSave = new Button
        {
            Text = "Save Rule",
            Left = inputLeft + 120,
            Top = y,
            Width = 110,
            Height = 36,
            BackColor = Color.FromArgb(24, 115, 220),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            DialogResult = DialogResult.OK,
            Cursor = Cursors.Hand
        };
        _btnSave.FlatAppearance.BorderSize = 0;
        _btnSave.Click += OnSaveClicked;

        _btnCancel = new Button
        {
            Text = "Cancel",
            Left = inputLeft + 240,
            Top = y,
            Width = 110,
            Height = 36,
            BackColor = Color.FromArgb(225, 230, 238),
            ForeColor = Color.FromArgb(40, 50, 70),
            FlatStyle = FlatStyle.Flat,
            DialogResult = DialogResult.Cancel,
            Cursor = Cursors.Hand
        };
        _btnCancel.FlatAppearance.BorderSize = 0;

        Controls.AddRange([_btnSave, _btnCancel]);
        AcceptButton = _btnSave;
        CancelButton = _btnCancel;
    }

    private void OnSaveClicked(object? sender, EventArgs e)
    {
        var proc = _cmbProcess.Text.Trim();
        if (proc.Contains(" (")) proc = proc.Substring(0, proc.IndexOf(" (")).Trim();

        ResultRule = new RoutingRule
        {
            Id = $"RULE-{Guid.NewGuid():N}".Substring(0, 16).ToUpperInvariant(),
            Name = _txtLabel.Text.Trim(),
            TargetProgram = proc,
            WindowTitleMatch = _txtWindowTitle.Text.Trim(),
            RequiredCopies = _chkAnyCopies.Checked ? 0 : (int)_numCopies.Value,
            ReferenceTemplate = _txtTemplate.Text.Trim(),
            Copy1Printer = _cmbCopy1.Text,
            LaterPrinter = _cmbLater.Text,
            LetterheadOverlay = _cmbOverlay.Text,
            Duplex = _chkDuplex.Checked,
            Enabled = _chkEnabled.Checked,
            OnMismatch = "P355_ONLY",
            Source = new RuleSourceCriteria
            {
                Process = proc,
                Screen = _txtWindowTitle.Text.Trim(),
                Copies = _chkAnyCopies.Checked ? null : (int)_numCopies.Value
            },
            Actions = new List<RuleAction>
            {
                new RuleAction { CopyNumber = 1, Destination = _cmbCopy1.Text },
                new RuleAction { CopyNumber = 2, Destination = _cmbLater.Text, Duplex = _chkDuplex.Checked, Transform = _cmbOverlay.Text == "DUPLEX_FRONT_BACK" ? "CUSTOMER_LETTERHEAD_DUPLEX" : null }
            }
        };

        Close();
    }
}

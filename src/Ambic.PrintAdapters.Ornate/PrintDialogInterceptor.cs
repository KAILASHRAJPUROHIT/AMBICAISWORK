using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Ambic.PrintCore.Models;
using Ambic.PrintCore.Routing;

namespace Ambic.PrintAdapters.Ornate;

public class PrintDialogInterceptor
{
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll", ExactSpelling = true)]
    private static extern IntPtr GetDlgItem(IntPtr hDlg, int nIDDlgItem);

    [DllImport("user32.dll")]
    private static extern int GetDlgCtrlID(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, StringBuilder lParam);

    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr hWnd);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern IntPtr VirtualAllocEx(IntPtr hProcess, IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);

    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern bool VirtualFreeEx(IntPtr hProcess, IntPtr lpAddress, uint dwSize, uint dwFreeType);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool ReadProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, [Out] byte[] lpBuffer, uint dwSize, out IntPtr lpNumberOfBytesRead);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool WriteProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, IntPtr lpBuffer, uint nSize, out IntPtr lpNumberOfBytesWritten);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);

    [DllImport("kernel32.dll", SetLastError = true, CallingConvention = CallingConvention.Winapi)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWow64Process([In] IntPtr processHandle, [Out, MarshalAs(UnmanagedType.Bool)] out bool wow64Process);

    private const uint BM_CLICK = 0x00F5;
    private const int IDC_PRINTER_COMBO = 0x0140;
    private const uint WM_COMMAND = 0x0111;
    private const int CBN_SELCHANGE = 1;
    private const uint CB_GETCOUNT = 0x0146;
    private const uint CB_GETLBTEXT = 0x0148;
    private const uint CB_GETLBTEXTLEN = 0x0149;
    private const uint CB_SETCURSEL = 0x014E;

    private const uint LVM_GETITEMCOUNT = 0x1004;
    private const uint LVM_GETITEMTEXTW = 0x1073;
    private const uint LVM_SETITEMSTATE = 0x102B;
    private const uint LVIF_TEXT = 0x0001;
    private const uint LVIF_STATE = 0x0008;
    private const uint LVIS_SELECTED = 0x0002;
    private const uint LVIS_FOCUSED = 0x0001;

    private const uint PROCESS_VM_OPERATION = 0x0008;
    private const uint PROCESS_VM_READ = 0x0010;
    private const uint PROCESS_VM_WRITE = 0x0020;
    private const uint PROCESS_QUERY_INFORMATION = 0x0400;
    private const uint MEM_COMMIT = 0x1000;
    private const uint MEM_RELEASE = 0x8000;
    private const uint PAGE_READWRITE = 0x04;

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct LVITEM32
    {
        public uint mask;
        public int iItem;
        public int iSubItem;
        public uint state;
        public uint stateMask;
        public uint pszText;
        public int cchTextMax;
        public int iImage;
        public int lParam;
        public int iIndent;
        public int iGroupId;
        public uint cColumns;
        public uint puColumns;
        public uint piColFmt;
        public int iGroup;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LVITEM64
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

    private static int MakeLong(int low, int high) => (low & 0xFFFF) | ((high & 0xFFFF) << 16);

    // State tracking
    private readonly HashSet<IntPtr> _handledDialogs = [];
    private readonly HashSet<IntPtr> _knownVoucherWindows = [];
    private bool _voucherSessionActive;
    private bool _officeCopyHandled;
    private bool _sessionExplicitSingleCopy;
    private string _sessionCopy1Printer = "";
    private string _sessionLaterPrinter = "";
    private DateTime _sessionStartTime = DateTime.MinValue;
    private int _onxDialogIndex = 0;
    private DateTime _lastOnxDialogTime = DateTime.MinValue;
    private static readonly TimeSpan SessionTimeout = TimeSpan.FromSeconds(35);
    private static readonly TimeSpan DialogGapThreshold = TimeSpan.FromSeconds(12);

    public event Action<string>? LogEvent;

    private void Log(string message) => LogEvent?.Invoke(message);

    public void ArmVoucherSession(string copy1Printer, string copy2Printer, string voucherTitle)
    {
        _voucherSessionActive = true;
        _officeCopyHandled = false;
        _sessionCopy1Printer = copy1Printer;
        _sessionLaterPrinter = copy2Printer;
        _sessionStartTime = DateTime.UtcNow;
        Log($"[SESSION ARMED] Ornate Voucher: '{voucherTitle}' -> Copy 1: [{copy1Printer}], Copy 2+: [{copy2Printer}]");
    }

    public void ScanAndIntercept(RouterHubConfig? config)
    {
        if (config != null && !config.MasterRoutingEnabled)
            return;

        // Cleanup stale handles
        _handledDialogs.RemoveWhere(h => !IsWindow(h));
        _knownVoucherWindows.RemoveWhere(h => !IsWindow(h));

        // Check session expiration
        if (_voucherSessionActive && (DateTime.UtcNow - _sessionStartTime) > SessionTimeout)
        {
            _voucherSessionActive = false;
            _officeCopyHandled = false;
            Log("[SESSION EXPIRED] Ornate Voucher print session timed out after 35 seconds without print.");
        }

        // 1. Scan for Ornate Voucher Print windows to automatically arm session
        var voucherWindows = OrnateWindowWatcher.FindOrnateVoucherWindows();
        foreach (var vw in voucherWindows)
        {
            if (_knownVoucherWindows.Contains(vw.WindowHandle))
                continue;

            // Resolve target printers from HubSettings / Rules
            string c1 = "";
            string c2 = "";

            if (config != null)
            {
                var match = RoutingEngine.FindMatchingRule(config.Rules, vw.ProcessName, vw.WindowTitle, vw.DetectedCopyCount);
                if (match != null)
                {
                    c1 = !string.IsNullOrWhiteSpace(match.Copy1Printer) && match.Copy1Printer != "(use configured default)"
                        ? match.Copy1Printer
                        : config.DefaultCopy1Printer;

                    c2 = !string.IsNullOrWhiteSpace(match.LaterPrinter) && match.LaterPrinter != "(use configured default)"
                        ? match.LaterPrinter
                        : config.DefaultCopy2Printer;
                }
                else
                {
                    c1 = config.DefaultCopy1Printer;
                    c2 = config.DefaultCopy2Printer;
                }

                // Apply force overrides if configured
                if (!string.IsNullOrWhiteSpace(config.ForceCopy1Printer)) c1 = config.ForceCopy1Printer;
                if (!string.IsNullOrWhiteSpace(config.ForceCopy2Printer)) c2 = config.ForceCopy2Printer;

                // Apply BothMode override if set
                if (config.BothMode.StartsWith("BOTH_P1007", StringComparison.OrdinalIgnoreCase) ||
                    config.BothMode.Contains("P1007", StringComparison.OrdinalIgnoreCase) && !config.BothMode.Contains("split", StringComparison.OrdinalIgnoreCase))
                {
                    c1 = config.DefaultCopy1Printer;
                    c2 = config.DefaultCopy1Printer;
                }
                else if (config.BothMode.StartsWith("BOTH_P355", StringComparison.OrdinalIgnoreCase) ||
                         config.BothMode.Contains("355", StringComparison.OrdinalIgnoreCase) && !config.BothMode.Contains("split", StringComparison.OrdinalIgnoreCase))
                {
                    c1 = config.DefaultCopy2Printer;
                    c2 = config.DefaultCopy2Printer;
                }
            }

            if (string.IsNullOrWhiteSpace(c1)) c1 = "P1007 (via PC2)";
            if (string.IsNullOrWhiteSpace(c2)) c2 = "355 Letterhead Capture";

            // UNIVERSAL INVARIANT: P1007 is STRICTLY and EXCLUSIVELY for Copy 1 of a verified 2-copy voucher.
            if (vw.DetectedCopyCount == 2)
            {
                _knownVoucherWindows.Add(vw.WindowHandle);
                _sessionExplicitSingleCopy = false;
                ArmVoucherSession(c1, c2, vw.WindowTitle);
            }
            else if (vw.DetectedCopyCount == 1)
            {
                _knownVoucherWindows.Add(vw.WindowHandle);
                _sessionExplicitSingleCopy = true;
                Log($"[ROUTE SAFETY] Voucher '{vw.WindowTitle}' copy count is explicitly 1 (single-copy voucher). P1007 blocked, routed to [{c2}].");
                ArmVoucherSession(c2, c2, vw.WindowTitle);
            }
            else if (vw.DetectedCopyCount > 2)
            {
                _knownVoucherWindows.Add(vw.WindowHandle);
                _sessionExplicitSingleCopy = false;
                ArmVoucherSession(c1, c2, vw.WindowTitle);
            }
            // If DetectedCopyCount == 0 (still opening / unreadable), do not lock into _knownVoucherWindows yet.
        }

        // 2. Scan for Win32 #32770 Print dialogs
        EnumWindows((hWnd, lParam) =>
        {
            try
            {
                var className = new StringBuilder(256);
                GetClassName(hWnd, className, className.Capacity);
                if (className.ToString() != "#32770") return true;

                var title = new StringBuilder(256);
                GetWindowText(hWnd, title, title.Capacity);
                var titleStr = title.ToString();
                if (!string.Equals(titleStr, "Print", StringComparison.OrdinalIgnoreCase)) return true;

                if (_handledDialogs.Contains(hWnd)) return true;

                GetWindowThreadProcessId(hWnd, out var pid);
                string procName = "";
                try
                {
                    var proc = Process.GetProcessById((int)pid);
                    procName = proc.ProcessName;
                }
                catch { }

                // Check affirmative Print button (ID 1)
                IntPtr printButton = GetDlgItem(hWnd, 1);
                if (printButton == IntPtr.Zero) return true;

                var btnText = new StringBuilder(64);
                GetWindowText(printButton, btnText, btnText.Capacity);
                var cleanBtn = btnText.ToString().Replace("&", "").Trim();
                if (!string.Equals(cleanBtn, "Print", StringComparison.OrdinalIgnoreCase)) return true;

                // Determine target printer
                string targetPrinter = "";
                int copyNumber = 1;

                if (string.Equals(procName, "ONX", StringComparison.OrdinalIgnoreCase))
                {
                    bool forceAll1007 = config != null && (config.BothMode.StartsWith("BOTH_P1007", StringComparison.OrdinalIgnoreCase) ||
                                                           (config.BothMode.Contains("P1007", StringComparison.OrdinalIgnoreCase) && !config.BothMode.Contains("split", StringComparison.OrdinalIgnoreCase)));
                    bool forceAll355 = config != null && (config.BothMode.StartsWith("BOTH_P355", StringComparison.OrdinalIgnoreCase) ||
                                                          (config.BothMode.Contains("355", StringComparison.OrdinalIgnoreCase) && !config.BothMode.Contains("split", StringComparison.OrdinalIgnoreCase)));

                    string c1Printer = config != null && !string.IsNullOrWhiteSpace(config.DefaultCopy1Printer)
                        ? config.DefaultCopy1Printer : "P1007 (via PC2)";
                    string c2Printer = config != null && !string.IsNullOrWhiteSpace(config.DefaultCopy2Printer)
                        ? config.DefaultCopy2Printer : "355 Letterhead Capture";

                    if (!string.IsNullOrWhiteSpace(config?.ForceCopy1Printer)) c1Printer = config.ForceCopy1Printer;
                    if (!string.IsNullOrWhiteSpace(config?.ForceCopy2Printer)) c2Printer = config.ForceCopy2Printer;

                    if (forceAll1007)
                    {
                        copyNumber = 1;
                        targetPrinter = c1Printer;
                    }
                    else if (forceAll355)
                    {
                        copyNumber = 2;
                        targetPrinter = c2Printer;
                    }
                    else
                    {
                        // Check if this dialog belongs to a new sequence or is part of a rapid burst
                        var gap = DateTime.UtcNow - _lastOnxDialogTime;
                        if (gap > DialogGapThreshold)
                        {
                            _onxDialogIndex = 1;
                            if (!_voucherSessionActive)
                            {
                                _sessionExplicitSingleCopy = false;
                            }
                        }
                        else
                        {
                            _onxDialogIndex++;
                        }
                        _lastOnxDialogTime = DateTime.UtcNow;

                        // Check if an armed 2-copy session exists
                        if (_voucherSessionActive)
                        {
                            if (_onxDialogIndex == 1)
                            {
                                copyNumber = 1;
                                targetPrinter = !string.IsNullOrWhiteSpace(_sessionCopy1Printer) ? _sessionCopy1Printer : c1Printer;
                                _officeCopyHandled = true;
                                Log($"[ROUTE] Ornate 2-copy voucher (armed session): Dialog 1 -> Copy 1 routed to [{targetPrinter}].");
                            }
                            else if (_onxDialogIndex == 2)
                            {
                                copyNumber = 2;
                                targetPrinter = !string.IsNullOrWhiteSpace(_sessionLaterPrinter) ? _sessionLaterPrinter : c2Printer;
                                _voucherSessionActive = false; // completed 2-copy voucher
                                Log($"[ROUTE] Ornate 2-copy voucher (armed session): Dialog 2 -> Copy 2 routed to [{targetPrinter}].");
                            }
                            else
                            {
                                // Dialog 3 or higher: URD purchase voucher or extra copies in this sequence
                                copyNumber = _onxDialogIndex;
                                targetPrinter = c2Printer;
                                _voucherSessionActive = false;
                                Log($"[ROUTE SAFETY] Ornate Dialog {_onxDialogIndex} in sequence (URD purchase voucher / extra copy). P1007 STRICTLY BLOCKED. Routed to [{c2Printer}].");
                            }
                        }
                        else
                        {
                            // Unarmed session (preview window closed quickly or was skipped)
                            if (_onxDialogIndex == 1)
                            {
                                if (_sessionExplicitSingleCopy)
                                {
                                    copyNumber = 1;
                                    targetPrinter = c2Printer;
                                    Log($"[ROUTE SAFETY] Ornate single-copy voucher. P1007 strictly blocked. Routed to [{c2Printer}].");
                                }
                                else
                                {
                                    copyNumber = 1;
                                    targetPrinter = c1Printer;
                                    Log($"[ROUTE] Ornate Dialog 1 of sequence -> Copy 1 (Office Copy) routed to [{c1Printer}].");
                                }
                            }
                            else if (_onxDialogIndex == 2)
                            {
                                copyNumber = 2;
                                targetPrinter = c2Printer;
                                Log($"[ROUTE] Ornate Dialog 2 of sequence -> Copy 2 (Customer Copy) routed to [{c2Printer}].");
                            }
                            else
                            {
                                // Dialog 3 or higher: URD purchase voucher or extra copies!
                                copyNumber = _onxDialogIndex;
                                targetPrinter = c2Printer;
                                Log($"[ROUTE SAFETY] Ornate Dialog {_onxDialogIndex} of sequence (URD purchase voucher / extra copy). P1007 STRICTLY BLOCKED. Routed to [{c2Printer}].");
                            }
                        }
                    }
                }
                else
                {
                    // Check other programs configured in rules
                    if (config != null)
                    {
                        var match = RoutingEngine.FindMatchingRule(config.Rules, procName, titleStr, 1);
                        if (match != null)
                        {
                            targetPrinter = !string.IsNullOrWhiteSpace(match.Copy1Printer) && match.Copy1Printer != "(use configured default)"
                                ? match.Copy1Printer
                                : config.DefaultCopy1Printer;
                        }
                    }

                    if (string.IsNullOrWhiteSpace(targetPrinter)) return true; // not managed
                }

                if (string.IsNullOrWhiteSpace(targetPrinter)) return true;

                // Intercept and select the target printer
                _handledDialogs.Add(hWnd);
                var diags = new List<string>();
                Log($"[INTERCEPT] Print dialog detected (HWND: 0x{hWnd:X8}, Program: {procName}, Copy: {copyNumber}). Target printer: [{targetPrinter}]");

                bool selected = TrySelectPrinter(hWnd, (int)pid, targetPrinter, diags);
                if (selected)
                {
                    Log($"[AUTO-SELECT SUCCESS] Selected printer '{targetPrinter}' for Copy {copyNumber}. Clicking Print.");
                    Thread.Sleep(60); // Allow dialog to update DC/driver settings
                    SendMessage(printButton, BM_CLICK, IntPtr.Zero, IntPtr.Zero);
                }
                else
                {
                    Log($"[AUTO-SELECT BLOCKED] Could not auto-select printer '{targetPrinter}'. Leaving dialog open for manual user confirmation.");
                    foreach (var d in diags) Log($"  -> DIAG: {d}");
                }
            }
            catch (Exception ex)
            {
                Log($"[INTERCEPT ERROR] {ex.Message}");
            }

            return true;
        }, IntPtr.Zero);
    }

    private bool TrySelectPrinter(IntPtr dialog, int ownerPid, string printerName, List<string> diagnostics)
    {
        if (string.IsNullOrEmpty(printerName)) return false;

        // Method 1: UI Automation (robust across 32/64 bitness)
        try
        {
            var root = System.Windows.Automation.AutomationElement.FromHandle(dialog);
            if (root != null)
            {
                var itemCond = new System.Windows.Automation.PropertyCondition(
                    System.Windows.Automation.AutomationElement.ControlTypeProperty,
                    System.Windows.Automation.ControlType.ListItem);
                var items = root.FindAll(System.Windows.Automation.TreeScope.Descendants, itemCond);

                foreach (System.Windows.Automation.AutomationElement item in items)
                {
                    string name = item.Current.Name;
                    if (!string.IsNullOrEmpty(name) && name.IndexOf(printerName, StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        if (item.TryGetCurrentPattern(System.Windows.Automation.SelectionItemPattern.Pattern, out var pat) &&
                            pat is System.Windows.Automation.SelectionItemPattern selPat)
                        {
                            selPat.Select();
                            diagnostics.Add($"Selected via UI Automation ListItem: '{name}'");
                            return true;
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            diagnostics.Add($"UI Automation attempt: {ex.Message}");
        }

        // Method 2: Win32 SysListView32 (native ListView control)
        IntPtr listView = IntPtr.Zero;
        var combos = new List<IntPtr>();

        EnumChildWindows(dialog, (hWndChild, lParam) =>
        {
            var cls = new StringBuilder(256);
            GetClassName(hWndChild, cls, cls.Capacity);
            var clsName = cls.ToString();
            if (clsName == "SysListView32" && listView == IntPtr.Zero) listView = hWndChild;
            else if (clsName == "ComboBox") combos.Add(hWndChild);
            return true;
        }, IntPtr.Zero);

        if (listView != IntPtr.Zero && TrySelectPrinterInListView(listView, ownerPid, printerName, diagnostics))
        {
            return true;
        }

        // Method 3: Win32 ComboBox
        IntPtr guess = GetDlgItem(dialog, IDC_PRINTER_COMBO);
        if (guess != IntPtr.Zero && !combos.Contains(guess)) combos.Insert(0, guess);

        foreach (var combo in combos)
        {
            int count = SendMessage(combo, CB_GETCOUNT, IntPtr.Zero, IntPtr.Zero).ToInt32();
            if (count <= 0 || count > 200) continue;

            var items = new List<string>(count);
            int matchIndex = -1;

            for (int i = 0; i < count; i++)
            {
                int len = SendMessage(combo, CB_GETLBTEXTLEN, new IntPtr(i), IntPtr.Zero).ToInt32();
                if (len <= 0) continue;
                var sb = new StringBuilder(len + 1);
                SendMessage(combo, CB_GETLBTEXT, new IntPtr(i), sb);
                var text = sb.ToString();
                items.Add(text);

                if (matchIndex == -1 && text.IndexOf(printerName, StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    matchIndex = i;
                }
            }

            diagnostics.Add($"ComboBox 0x{combo:X} [{count} items]: {string.Join(" | ", items)}");

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

    private bool TrySelectPrinterInListView(IntPtr listView, int ownerPid, string printerName, List<string> diagnostics)
    {
        int count = SendMessage(listView, LVM_GETITEMCOUNT, IntPtr.Zero, IntPtr.Zero).ToInt32();
        if (count <= 0 || count > 500)
        {
            diagnostics.Add($"ListView item count was {count}");
            return false;
        }

        IntPtr hProcess = OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION, false, ownerPid);
        if (hProcess == IntPtr.Zero)
        {
            diagnostics.Add($"Could not open process PID {ownerPid} for cross-process memory read");
            return false;
        }

        try
        {
            bool isTargetWow64 = false;
            try { IsWow64Process(hProcess, out isTargetWow64); } catch { }

            const int textBufChars = 256;
            int textBufBytes = textBufChars * 2; // Unicode

            IntPtr remoteText = VirtualAllocEx(hProcess, IntPtr.Zero, (uint)textBufBytes, MEM_COMMIT, PAGE_READWRITE);
            if (remoteText == IntPtr.Zero)
            {
                diagnostics.Add("VirtualAllocEx remoteText failed");
                return false;
            }

            try
            {
                var items = new List<string>(count);
                int matchIndex = -1;

                if (isTargetWow64)
                {
                    int lvItemSize = Marshal.SizeOf(typeof(LVITEM32));
                    IntPtr remoteLvItem = VirtualAllocEx(hProcess, IntPtr.Zero, (uint)lvItemSize, MEM_COMMIT, PAGE_READWRITE);
                    if (remoteLvItem == IntPtr.Zero) return false;

                    try
                    {
                        for (int i = 0; i < count; i++)
                        {
                            var lv = new LVITEM32
                            {
                                mask = LVIF_TEXT,
                                iItem = i,
                                iSubItem = 0,
                                pszText = (uint)remoteText.ToInt64(),
                                cchTextMax = textBufChars
                            };

                            if (!WriteRemoteStruct(hProcess, remoteLvItem, lv)) continue;
                            SendMessage(listView, LVM_GETITEMTEXTW, new IntPtr(i), remoteLvItem);

                            byte[] buf = new byte[textBufBytes];
                            ReadProcessMemory(hProcess, remoteText, buf, (uint)textBufBytes, out _);
                            string text = Encoding.Unicode.GetString(buf);
                            int nullIdx = text.IndexOf('\0');
                            if (nullIdx >= 0) text = text.Substring(0, nullIdx);
                            items.Add(text);

                            if (matchIndex == -1 && text.IndexOf(printerName, StringComparison.OrdinalIgnoreCase) >= 0)
                                matchIndex = i;
                        }

                        diagnostics.Add($"ListView (WOW64) [{count} items]: {string.Join(" | ", items)}");
                        if (matchIndex < 0) return false;

                        // Deselect and select match
                        for (int i = 0; i < count; i++)
                        {
                            var lv = new LVITEM32 { mask = LVIF_STATE, state = 0, stateMask = LVIS_SELECTED | LVIS_FOCUSED };
                            WriteRemoteStruct(hProcess, remoteLvItem, lv);
                            SendMessage(listView, LVM_SETITEMSTATE, new IntPtr(i), remoteLvItem);
                        }

                        var selLv = new LVITEM32 { mask = LVIF_STATE, state = LVIS_SELECTED | LVIS_FOCUSED, stateMask = LVIS_SELECTED | LVIS_FOCUSED };
                        WriteRemoteStruct(hProcess, remoteLvItem, selLv);
                        SendMessage(listView, LVM_SETITEMSTATE, new IntPtr(matchIndex), remoteLvItem);
                        return true;
                    }
                    finally
                    {
                        VirtualFreeEx(hProcess, remoteLvItem, 0, MEM_RELEASE);
                    }
                }
                else
                {
                    int lvItemSize = Marshal.SizeOf(typeof(LVITEM64));
                    IntPtr remoteLvItem = VirtualAllocEx(hProcess, IntPtr.Zero, (uint)lvItemSize, MEM_COMMIT, PAGE_READWRITE);
                    if (remoteLvItem == IntPtr.Zero) return false;

                    try
                    {
                        for (int i = 0; i < count; i++)
                        {
                            var lv = new LVITEM64
                            {
                                mask = LVIF_TEXT,
                                iItem = i,
                                iSubItem = 0,
                                pszText = remoteText,
                                cchTextMax = textBufChars
                            };

                            if (!WriteRemoteStruct(hProcess, remoteLvItem, lv)) continue;
                            SendMessage(listView, LVM_GETITEMTEXTW, new IntPtr(i), remoteLvItem);

                            byte[] buf = new byte[textBufBytes];
                            ReadProcessMemory(hProcess, remoteText, buf, (uint)textBufBytes, out _);
                            string text = Encoding.Unicode.GetString(buf);
                            int nullIdx = text.IndexOf('\0');
                            if (nullIdx >= 0) text = text.Substring(0, nullIdx);
                            items.Add(text);

                            if (matchIndex == -1 && text.IndexOf(printerName, StringComparison.OrdinalIgnoreCase) >= 0)
                                matchIndex = i;
                        }

                        diagnostics.Add($"ListView (x64) [{count} items]: {string.Join(" | ", items)}");
                        if (matchIndex < 0) return false;

                        for (int i = 0; i < count; i++)
                        {
                            var lv = new LVITEM64 { mask = LVIF_STATE, state = 0, stateMask = LVIS_SELECTED | LVIS_FOCUSED };
                            WriteRemoteStruct(hProcess, remoteLvItem, lv);
                            SendMessage(listView, LVM_SETITEMSTATE, new IntPtr(i), remoteLvItem);
                        }

                        var selLv = new LVITEM64 { mask = LVIF_STATE, state = LVIS_SELECTED | LVIS_FOCUSED, stateMask = LVIS_SELECTED | LVIS_FOCUSED };
                        WriteRemoteStruct(hProcess, remoteLvItem, selLv);
                        SendMessage(listView, LVM_SETITEMSTATE, new IntPtr(matchIndex), remoteLvItem);
                        return true;
                    }
                    finally
                    {
                        VirtualFreeEx(hProcess, remoteLvItem, 0, MEM_RELEASE);
                    }
                }
            }
            finally
            {
                VirtualFreeEx(hProcess, remoteText, 0, MEM_RELEASE);
            }
        }
        finally
        {
            CloseHandle(hProcess);
        }
    }

    private static bool WriteRemoteStruct<T>(IntPtr hProcess, IntPtr remoteAddr, T structure) where T : struct
    {
        int size = Marshal.SizeOf(typeof(T));
        IntPtr local = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(structure, local, false);
            return WriteProcessMemory(hProcess, remoteAddr, local, (uint)size, out _);
        }
        finally
        {
            Marshal.FreeHGlobal(local);
        }
    }
}

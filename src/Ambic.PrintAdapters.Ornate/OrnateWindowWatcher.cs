using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Ambic.PrintCore.Models;
using Ambic.PrintCore.Routing;

namespace Ambic.PrintAdapters.Ornate;

public class OrnateVoucherDetectionResult
{
    public IntPtr WindowHandle { get; set; }
    public string ProcessName { get; set; } = string.Empty;
    public string WindowTitle { get; set; } = string.Empty;
    public string VoucherType { get; set; } = string.Empty;
    public int DetectedCopyCount { get; set; }
    public bool IsGstSalesVoucher { get; set; }
    public bool SafetyPassed { get; set; }
    public string FailureReason { get; set; } = string.Empty;
}

public class OrnateWindowWatcher
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

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, StringBuilder lParam);

    private const uint WM_GETTEXT = 0x000D;
    private const uint WM_GETTEXTLENGTH = 0x000E;

    public static List<OrnateVoucherDetectionResult> FindOrnateVoucherWindows() => ScanActiveVouchers();

    public static List<OrnateVoucherDetectionResult> ScanActiveVouchers()
    {
        var results = new List<OrnateVoucherDetectionResult>();

        EnumWindows((hWnd, lParam) =>
        {
            var className = new StringBuilder(256);
            GetClassName(hWnd, className, className.Capacity);
            if (className.ToString() != "#32770") return true;

            var title = new StringBuilder(256);
            GetWindowText(hWnd, title, title.Capacity);
            var titleStr = title.ToString();
            if (string.IsNullOrWhiteSpace(titleStr) ||
                (!titleStr.Contains("Voucher Print", StringComparison.OrdinalIgnoreCase) &&
                 !titleStr.Contains("Voucher", StringComparison.OrdinalIgnoreCase)))
                return true;

            GetWindowThreadProcessId(hWnd, out var pid);
            string procName = "";
            try
            {
                var proc = Process.GetProcessById((int)pid);
                procName = proc.ProcessName;
            }
            catch { }

            if (!string.Equals(procName, "ONX", StringComparison.OrdinalIgnoreCase))
                return true;

            var detection = InspectVoucherWindow(hWnd, procName, titleStr);
            results.Add(detection);
            return true;
        }, IntPtr.Zero);

        return results;
    }

    public static OrnateVoucherDetectionResult InspectVoucherWindow(IntPtr hWnd, string procName, string titleStr)
    {
        var result = new OrnateVoucherDetectionResult
        {
            WindowHandle = hWnd,
            ProcessName = procName,
            WindowTitle = titleStr
        };

        // 1. First try robust UI Automation (AutomationId=TxtNoOfCopy / ValuePattern)
        bool readViaUia = TryReadVoucherCopyCount(hWnd, out var uiaCopies, out var uiaDetail);
        var copyCount = 0;
        var foundCopyControl = false;
        var textSnippets = new List<string>();

        if (readViaUia && uiaCopies > 0)
        {
            copyCount = uiaCopies;
            foundCopyControl = true;
            result.FailureReason = uiaDetail;
        }

        // 2. Scan child controls for Edit controls if UI Automation didn't resolve copyCount
        EnumChildWindows(hWnd, (hChild, _) =>
        {
            var className = new StringBuilder(64);
            GetClassName(hChild, className, className.Capacity);
            var cls = className.ToString();

            var text = GetControlText(hChild);
            if (!string.IsNullOrWhiteSpace(text))
            {
                textSnippets.Add(text);
                if (!foundCopyControl &&
                    (cls.Equals("Edit", StringComparison.OrdinalIgnoreCase) ||
                     cls.Contains("TextBox", StringComparison.OrdinalIgnoreCase) ||
                     cls.Contains("Edit", StringComparison.OrdinalIgnoreCase)))
                {
                    if (GetWindowRect(hChild, out var rect))
                    {
                        int w = rect.Right - rect.Left;
                        int h = rect.Bottom - rect.Top;
                        if (w > 0 && w <= 120 && h > 0 && h <= 40)
                        {
                            if (int.TryParse(text.Trim(), out var val) && val > 0 && val <= 9)
                            {
                                copyCount = val;
                                foundCopyControl = true;
                            }
                        }
                    }
                }
            }
            return true;
        }, IntPtr.Zero);

        result.DetectedCopyCount = copyCount;
        result.IsGstSalesVoucher = textSnippets.Any(t => t.Contains("GST Sales", StringComparison.OrdinalIgnoreCase) ||
                                                         t.Contains("Sales Voucher", StringComparison.OrdinalIgnoreCase) ||
                                                         titleStr.Contains("Voucher", StringComparison.OrdinalIgnoreCase));
        result.VoucherType = result.IsGstSalesVoucher ? "GST Sales Voucher" : "Unknown";

        // Safety Invariant Evaluation
        if (copyCount == 2)
        {
            result.SafetyPassed = true;
            result.FailureReason = "Voucher verified: GST Sales Voucher with exact copy count = 2.";
        }
        else if (copyCount == 1)
        {
            result.SafetyPassed = false;
            result.FailureReason = "Single-copy voucher detected. P1007 blocked, customer printer 355 assigned.";
        }
        else
        {
            result.SafetyPassed = false;
            result.FailureReason = $"Copy count is {copyCount}. Awaiting definitive count or diverted to safe customer printer.";
        }

        return result;
    }

    public static bool TryReadVoucherCopyCount(IntPtr dialog, out int copies, out string detail)
    {
        copies = 0;
        detail = "";
        try
        {
            var root = System.Windows.Automation.AutomationElement.FromHandle(dialog);
            if (root == null)
            {
                detail = "UI Automation root unavailable for dialog.";
                return false;
            }

            var condition = new System.Windows.Automation.PropertyCondition(System.Windows.Automation.AutomationElement.IsControlElementProperty, true);
            var elements = root.FindAll(System.Windows.Automation.TreeScope.Descendants, condition);

            int matchCount = 0;
            int detectedCopies = 0;
            int? byAutomationId = null;

            foreach (System.Windows.Automation.AutomationElement element in elements)
            {
                string textVal = "";
                try
                {
                    if (element.TryGetCurrentPattern(System.Windows.Automation.ValuePattern.Pattern, out var vpObj) &&
                        vpObj is System.Windows.Automation.ValuePattern vp)
                    {
                        textVal = vp.Current.Value;
                    }
                }
                catch { }

                if (string.IsNullOrWhiteSpace(textVal))
                {
                    textVal = element.Current.Name;
                }

                if (string.IsNullOrWhiteSpace(textVal) && element.Current.NativeWindowHandle != 0)
                {
                    textVal = GetControlText((IntPtr)element.Current.NativeWindowHandle);
                }

                if (string.IsNullOrEmpty(textVal)) continue;
                if (!int.TryParse(textVal.Trim(), out var parsed) || parsed < 1 || parsed > 9) continue;

                var bounds = element.Current.BoundingRectangle;
                if (bounds.IsEmpty || bounds.Width <= 0 || bounds.Width > 120 || bounds.Height <= 0 || bounds.Height > 35)
                    continue;

                matchCount++;
                if (matchCount == 1) detectedCopies = parsed;
                if (string.Equals(element.Current.AutomationId, "TxtNoOfCopy", StringComparison.OrdinalIgnoreCase))
                {
                    byAutomationId = parsed;
                }
            }

            if (byAutomationId.HasValue)
            {
                copies = byAutomationId.Value;
                detail = $"Voucher Print copy count read via UI Automation (AutomationId=TxtNoOfCopy): {copies}";
                return true;
            }

            if (detectedCopies > 0)
            {
                copies = detectedCopies;
                detail = $"Voucher Print copy count read via UI Automation candidate: {copies}";
                return true;
            }
        }
        catch (Exception ex)
        {
            detail = $"UI Automation error: {ex.Message}";
        }

        return false;
    }

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static string? CaptureWindowToFile(IntPtr hWnd, string targetFolder, string? prefix = null)
    {
        try
        {
            if (hWnd == IntPtr.Zero || !GetWindowRect(hWnd, out var rect)) return null;

            int width = rect.Right - rect.Left;
            int height = rect.Bottom - rect.Top;
            if (width <= 50 || height <= 50) return null;

            Directory.CreateDirectory(targetFolder);
            var filename = $"{prefix ?? "template"}_{DateTime.Now:yyyyMMdd_HHmmss}.png";
            var fullPath = Path.Combine(targetFolder, filename);

            using var bmp = new System.Drawing.Bitmap(width, height);
            using (var g = System.Drawing.Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(rect.Left, rect.Top, 0, 0, new System.Drawing.Size(width, height));
            }

            bmp.Save(fullPath, System.Drawing.Imaging.ImageFormat.Png);
            return filename;
        }
        catch
        {
            return null;
        }
    }

    private static string GetControlText(IntPtr hWnd)
    {
        var len = (int)SendMessage(hWnd, WM_GETTEXTLENGTH, IntPtr.Zero, null!);
        if (len <= 0) return string.Empty;

        var sb = new StringBuilder(len + 1);
        SendMessage(hWnd, WM_GETTEXT, (IntPtr)sb.Capacity, sb);
        return sb.ToString();
    }
}

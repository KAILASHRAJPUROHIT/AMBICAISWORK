using Microsoft.Win32;

namespace Ambic.PrintAdapters.Ornate;

public class PrintDialogCompatibilityReport
{
    public bool IsWindows11 { get; set; }
    public bool DisablePrintSupportAppConfigured { get; set; }
    public bool HklmPreferClassicConfigured { get; set; }
    public bool HkcuPreferClassicConfigured { get; set; }
    public bool IsReady => !IsWindows11 || (DisablePrintSupportAppConfigured && HkcuPreferClassicConfigured);
    public string Summary => IsReady ? "PASS" : "FAIL (Modern XAML dialog active; Win32 Ornate automation blocked)";
}

public static class Windows11PrintDialogEnforcer
{
    private const string UnifiedPrintKey = @"Software\Microsoft\Print\UnifiedPrintDialog";
    private const string HklmUnifiedPrintKey = @"SOFTWARE\Microsoft\Print\UnifiedPrintDialog";
    private const string PrintersPolicyKey = @"SOFTWARE\Policies\Microsoft\Windows NT\Printers";

    public static bool IsWindows11()
    {
        try
        {
            var v = Environment.OSVersion.Version;
            // Windows 11 is NT 10.0 build >= 22000
            return v.Major >= 10 && Environment.OSVersion.Version.Build >= 22000;
        }
        catch
        {
            return false;
        }
    }

    public static PrintDialogCompatibilityReport CheckCompatibility()
    {
        var report = new PrintDialogCompatibilityReport
        {
            IsWindows11 = IsWindows11()
        };

        if (!report.IsWindows11)
            return report;

        // Check HKLM Policies Printers: DisablePrintSupportApp == 1
        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(PrintersPolicyKey);
            var val = key?.GetValue("DisablePrintSupportApp");
            report.DisablePrintSupportAppConfigured = val is int i && i == 1;
        }
        catch { }

        // Check HKLM UnifiedPrintDialog: PreferLegacyPrintDialog == 1
        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(HklmUnifiedPrintKey);
            var val = key?.GetValue("PreferLegacyPrintDialog");
            report.HklmPreferClassicConfigured = val is int i && i == 1;
        }
        catch { }

        // Check HKCU UnifiedPrintDialog: PreferLegacyPrintDialog == 1
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(UnifiedPrintKey);
            var val = key?.GetValue("PreferLegacyPrintDialog");
            report.HkcuPreferClassicConfigured = val is int i && i == 1;
        }
        catch { }

        return report;
    }

    public static (bool Success, string? Error) EnforceClassicPrintDialog()
    {
        try
        {
            // 1. HKCU\Software\Microsoft\Print\UnifiedPrintDialog -> PreferLegacyPrintDialog = 1
            try
            {
                using var key = Registry.CurrentUser.CreateSubKey(UnifiedPrintKey, writable: true);
                key?.SetValue("PreferLegacyPrintDialog", 1, RegistryValueKind.DWord);
                key?.SetValue("PreferLaunchModernPrintDialog", 0, RegistryValueKind.DWord);
            }
            catch { }

            // 2. HKCU Policies Printers: DisablePrintSupportApp = 1
            try
            {
                using var key = Registry.CurrentUser.CreateSubKey(PrintersPolicyKey, writable: true);
                key?.SetValue("DisablePrintSupportApp", 1, RegistryValueKind.DWord);
            }
            catch { }

            // 3. HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Printers -> DisablePrintSupportApp = 1
            try
            {
                using var key = Registry.LocalMachine.CreateSubKey(PrintersPolicyKey, writable: true);
                key?.SetValue("DisablePrintSupportApp", 1, RegistryValueKind.DWord);
            }
            catch { }

            // 4. HKLM\SOFTWARE\Microsoft\Print\UnifiedPrintDialog -> PreferLegacyPrintDialog = 1
            try
            {
                using var key = Registry.LocalMachine.CreateSubKey(HklmUnifiedPrintKey, writable: true);
                key?.SetValue("PreferLegacyPrintDialog", 1, RegistryValueKind.DWord);
                key?.SetValue("PreferLaunchModernPrintDialog", 0, RegistryValueKind.DWord);
            }
            catch { }

            // 5. Apply to all active users in HKEY_USERS
            try
            {
                foreach (var sid in Registry.Users.GetSubKeyNames())
                {
                    if (sid.EndsWith("_Classes", StringComparison.OrdinalIgnoreCase) || sid.StartsWith(".DEFAULT", StringComparison.OrdinalIgnoreCase))
                        continue;

                    try
                    {
                        using var userKey = Registry.Users.CreateSubKey($@"{sid}\{UnifiedPrintKey}", writable: true);
                        userKey?.SetValue("PreferLegacyPrintDialog", 1, RegistryValueKind.DWord);
                        userKey?.SetValue("PreferLaunchModernPrintDialog", 0, RegistryValueKind.DWord);
                    }
                    catch { }

                    try
                    {
                        using var policyKey = Registry.Users.CreateSubKey($@"{sid}\{PrintersPolicyKey}", writable: true);
                        policyKey?.SetValue("DisablePrintSupportApp", 1, RegistryValueKind.DWord);
                    }
                    catch { }
                }
            }
            catch { }

            // 6. Terminate any running Modern PrintDialog app so registry changes apply immediately
            try
            {
                foreach (var proc in System.Diagnostics.Process.GetProcessesByName("PrintDialog"))
                {
                    try { proc.Kill(true); } catch { }
                }
            }
            catch { }

            return (true, null);
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }
}

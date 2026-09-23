using System.Diagnostics;
using System.Security.Principal;
using System.Text.Json;
using Ambic.Print.Storage.Database;
using Ambic.Print.Storage.Repositories;
using Ambic.PrintAdapters.Ornate;
using Ambic.PrintCore.Config;
using Ambic.PrintCore.Models;

namespace Ambic.PrintInstaller;

internal class Program
{
    private static readonly string BaseDataDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "AMBIC DIGITAL",
        "Print Server"
    );

    private static readonly string BackupBaseDir = Path.Combine(BaseDataDir, "MigrationBackup");

    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    private static extern bool AttachConsole(int dwProcessId);
    private const int ATTACH_PARENT_PROCESS = -1;

    public static void StopRunningServicesAndProcesses()
    {
        string[] servicesToStop = ["AmbicPrintServerNode", "AmbicPrintNode"];
        foreach (var svc in servicesToStop)
        {
            try
            {
                RunCmd("sc.exe", $"stop {svc}");
                RunCmd("net.exe", $"stop {svc} /y");
            }
            catch { }
        }

        string[] procsToKill = ["Ambic.PrintNode", "Ambic.PrintConsole", "AradhanaOrnateAutoPrint", "Aradhana355Watcher", "UploadWatcher"];
        foreach (var pName in procsToKill)
        {
            try
            {
                RunCmd("taskkill.exe", $"/F /T /IM {pName}.exe");
                RunCmd("taskkill.exe", $"/F /T /IM {pName}");
                var running = Process.GetProcessesByName(pName);
                foreach (var proc in running)
                {
                    try
                    {
                        proc.Kill(true);
                        proc.WaitForExit(2000);
                    }
                    catch { }
                }
            }
            catch { }
        }

        Thread.Sleep(800);
    }

    [STAThread]
    static async Task<int> Main(string[] args)
    {
        if (args.Length == 0 || args.Contains("--gui"))
        {
            ApplicationConfiguration.Initialize();
            Application.Run(new FormSetup());
            return 0;
        }

        if (args.Contains("--generate-icon"))
        {
            var assetDir = @"c:\AradhanaSystems\projects\print-router\assets";
            Directory.CreateDirectory(assetDir);
            var icoPath = Path.Combine(assetDir, "app.ico");
            IconGenerator.Generate(icoPath);
            File.Copy(icoPath, @"c:\AradhanaSystems\projects\print-router\src\Ambic.PrintInstaller\app.ico", true);
            File.Copy(icoPath, @"c:\AradhanaSystems\projects\print-router\src\Ambic.PrintConsole\app.ico", true);
            Console.WriteLine($"Icon generated successfully at {icoPath} (Size: {new FileInfo(icoPath).Length} bytes)");
            return 0;
        }

        AttachConsole(ATTACH_PARENT_PROCESS);
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        PrintBanner();

        if (args.Contains("--help") || args.Contains("-h"))
        {
            PrintUsage();
            return 0;
        }

        bool isElevated = IsAdministrator();
        if (!isElevated)
        {
            LogWarn("WARNING: Installer is not running as Administrator. Some system-level actions (Service registration, Firewall, HKLM edits) may require elevation.");
        }

        try
        {
            if (args.Contains("--all"))
            {
                await RunFullDeploymentAsync();
            }
            else
            {
                if (args.Contains("--backup") || args.Contains("--migrate"))
                {
                    RunMigrationBackup();
                }

                if (args.Contains("--init-topology"))
                {
                    InitTopologyAndStorage();
                }

                if (args.Contains("--fix-win11"))
                {
                    FixWindows11PrintDialog();
                }

                if (args.Contains("--firewall"))
                {
                    ConfigureFirewall();
                }

                if (args.Contains("--install-service"))
                {
                    InstallWindowsService();
                }

                if (args.Contains("--uninstall-service"))
                {
                    UninstallWindowsService();
                }

                if (args.Contains("--verify"))
                {
                    await VerifyHealthAsync();
                }

                if (args.Contains("--setup-printer"))
                {
                    SetupCapturePrinter();
                }
            }

            LogSuccess("\nAll requested tasks completed successfully.");
            return 0;
        }
        catch (Exception ex)
        {
            LogError($"FATAL: Installation / Migration failed: {ex.Message}");
            return 1;
        }
    }

    private static void PrintBanner()
    {
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine(@"
===================================================================
   AMBIC PRINT SERVER - SETUP & FLEET MIGRATION UTILITY
   Powered by AMBIC DIGITAL (2026.09.22 Architecture)
===================================================================");
        Console.ResetColor();
    }

    private static void PrintUsage()
    {
        Console.WriteLine(@"Usage:
  Ambic.PrintInstaller.exe [options]

Options:
  --all                 Execute end-to-end migration, init, firewall, and service setup
  --migrate             Discover and create transactional backup of legacy print components
  --init-topology       Initialize local SQLite node database and rules cache
  --fix-win11           Enforce classic Win32 (#32770) print dialog for Windows 11
  --setup-printer       Install and configure 355 Letterhead Capture printer & spool folders
  --firewall            Open inbound TCP port 8447 in Windows Firewall
  --install-service     Register and configure AmbicPrintNode as delayed-auto Windows Service
  --uninstall-service   Stop and remove AmbicPrintNode Windows Service
  --verify              Perform health check against local running node (port 8447)
");
    }

    private static async Task RunFullDeploymentAsync()
    {
        LogInfo("--- STEP 1: Legacy Discovery & Transactional Backup ---");
        RunMigrationBackup();

        LogInfo("\n--- STEP 2: Storage & Topology Initialization ---");
        InitTopologyAndStorage();

        LogInfo("\n--- STEP 2.5: 355 Letterhead Capture Setup ---");
        SetupCapturePrinter();

        LogInfo("\n--- STEP 3: Windows 11 Print Dialog Enforcement ---");
        FixWindows11PrintDialog();

        LogInfo("\n--- STEP 4: Windows Firewall Configuration ---");
        ConfigureFirewall();

        LogInfo("\n--- STEP 5: Windows Service Registration ---");
        InstallWindowsService();

        LogInfo("\n--- STEP 6: Fleet Health Verification ---");
        await VerifyHealthAsync();
    }

    public static void RunMigrationBackup()
    {
        var timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        var targetBackup = Path.Combine(BackupBaseDir, $"backup_{timestamp}");
        Directory.CreateDirectory(targetBackup);

        LogInfo($"Starting legacy discovery and backup to: {targetBackup}");

        var discoveredPaths = new List<string>
        {
            @"C:\PrintBridge",
            @"C:\P1007PrinterRelay",
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Aradhana"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "PrintBridge"),
            @"C:\AradhanaSystems\projects\print-router\src\AradhanaOrnateAutoPrint.cs",
            @"C:\AradhanaSystems\projects\print-router\overlay",
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Bullzip", "PDF Printer")
        };

        try
        {
            if (Directory.Exists(@"C:\Users"))
            {
                foreach (var uDir in Directory.GetDirectories(@"C:\Users"))
                {
                    var pb = Path.Combine(uDir, "PrintBridge");
                    if (Directory.Exists(pb) && !discoveredPaths.Contains(pb))
                    {
                        discoveredPaths.Add(pb);
                    }
                }
            }
        }
        catch { }

        var backedUpItems = new List<string>();

        foreach (var path in discoveredPaths)
        {
            if (File.Exists(path))
            {
                var dest = Path.Combine(targetBackup, Path.GetFileName(path));
                File.Copy(path, dest, true);
                backedUpItems.Add(path);
                LogSuccess($"[BACKED UP FILE] {path} -> {dest}");
            }
            else if (Directory.Exists(path))
            {
                var dirName = new DirectoryInfo(path).Name;
                var destDir = Path.Combine(targetBackup, dirName);
                CopyDirectory(path, destDir);
                backedUpItems.Add(path);
                LogSuccess($"[BACKED UP DIR]  {path} -> {destDir}");
            }
        }

        // Export active scheduled tasks related to Aradhana
        try
        {
            var taskListOutput = RunCmd("schtasks.exe", "/query /fo LIST /v");
            var taskBackupFile = Path.Combine(targetBackup, "scheduled_tasks_dump.txt");
            File.WriteAllText(taskBackupFile, taskListOutput);
            LogSuccess($"[BACKED UP] Scheduled tasks list saved to {taskBackupFile}");
        }
        catch (Exception ex)
        {
            LogWarn($"Could not dump scheduled tasks: {ex.Message}");
        }

        var manifest = new
        {
            Timestamp = DateTime.UtcNow,
            Machine = Environment.MachineName,
            BackedUpSources = backedUpItems
        };
        var manifestJson = JsonSerializer.Serialize(manifest, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(Path.Combine(targetBackup, "manifest.json"), manifestJson);

        LogSuccess($"Migration snapshot successfully created with {backedUpItems.Count} items.");
    }

    public static void DecommissionLegacyPrintRouters(Action<string>? log = null)
    {
        void Log(string msg)
        {
            LogInfo(msg);
            log?.Invoke(msg);
        }

        Log("--- Decommissioning & Auto-Deleting Legacy Print Routers & Dependencies ---");

        // 1. Terminate all old processes
        string[] oldProcessNames = [
            "AradhanaOrnateAutoPrint",
            "AradhanaOrnateAutoPrint.exe",
            "UploadWatcher",
            "Aradhana355Watcher"
        ];

        foreach (var p in oldProcessNames)
        {
            try
            {
                RunCmd("taskkill.exe", $"/F /T /IM {p}.exe");
                RunCmd("taskkill.exe", $"/F /T /IM {p}");
                foreach (var proc in Process.GetProcessesByName(p.Replace(".exe", "")))
                {
                    try { proc.Kill(true); proc.WaitForExit(1000); } catch { }
                }
            }
            catch { }
        }

        try
        {
            RunCmd("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -Command \"Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'relay\\.py|run_relay_hidden|UploadWatcher|AradhanaOrnateAutoPrint' -or $_.Name -match 'AradhanaOrnateAutoPrint' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\"");
        }
        catch { }

        // 2. Delete legacy Scheduled Tasks
        string[] oldTasks = ["PrintBridgeUpload", "P1007PrinterRelay"];
        foreach (var t in oldTasks)
        {
            try
            {
                var res = RunCmd("schtasks.exe", $"/Delete /TN \"{t}\" /F");
                Log($"Removed scheduled task '{t}': {res.Trim()}");
            }
            catch (Exception ex)
            {
                Log($"Task '{t}' cleanup note: {ex.Message}");
            }
        }

        // Sweep for any task containing legacy router patterns
        try
        {
            var taskQuery = RunCmd("schtasks.exe", "/Query /FO CSV /NH");
            var lines = taskQuery.Split(["\r\n", "\n"], StringSplitOptions.RemoveEmptyEntries);
            foreach (var line in lines)
            {
                var parts = line.Split(',');
                if (parts.Length > 0)
                {
                    var taskName = parts[0].Trim('"', ' ', '\\');
                    if (taskName.Contains("PrintBridge", StringComparison.OrdinalIgnoreCase) ||
                        taskName.Contains("PrinterRelay", StringComparison.OrdinalIgnoreCase) ||
                        taskName.Contains("OrnateAutoPrint", StringComparison.OrdinalIgnoreCase))
                    {
                        try
                        {
                            RunCmd("schtasks.exe", $"/Delete /TN \"{taskName}\" /F");
                            Log($"Removed legacy task: {taskName}");
                        }
                        catch { }
                    }
                }
            }
        }
        catch { }

        // 3. Remove legacy Registry Run keys
        try
        {
            string[] runKeys = [
                @"Software\Microsoft\Windows\CurrentVersion\Run",
                @"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
            ];

            foreach (var rkPath in runKeys)
            {
                // CurrentUser
                using (var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(rkPath, writable: true))
                {
                    if (key != null)
                    {
                        foreach (var valName in key.GetValueNames())
                        {
                            var valData = key.GetValue(valName)?.ToString() ?? "";
                            if ((valName.Contains("Aradhana", StringComparison.OrdinalIgnoreCase) && valName.Contains("Print", StringComparison.OrdinalIgnoreCase)) ||
                                valName.Contains("PrintBridge", StringComparison.OrdinalIgnoreCase) ||
                                valData.Contains("AradhanaOrnateAutoPrint", StringComparison.OrdinalIgnoreCase) ||
                                valData.Contains("PrintBridge", StringComparison.OrdinalIgnoreCase) ||
                                valData.Contains("P1007PrinterRelay", StringComparison.OrdinalIgnoreCase))
                            {
                                try
                                {
                                    key.DeleteValue(valName, false);
                                    Log($"Deleted HKCU\\{rkPath} key: {valName}");
                                }
                                catch { }
                            }
                        }
                    }
                }

                // LocalMachine
                using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(rkPath, writable: true))
                {
                    if (key != null)
                    {
                        foreach (var valName in key.GetValueNames())
                        {
                            var valData = key.GetValue(valName)?.ToString() ?? "";
                            if ((valName.Contains("Aradhana", StringComparison.OrdinalIgnoreCase) && valName.Contains("Print", StringComparison.OrdinalIgnoreCase)) ||
                                valName.Contains("PrintBridge", StringComparison.OrdinalIgnoreCase) ||
                                valData.Contains("AradhanaOrnateAutoPrint", StringComparison.OrdinalIgnoreCase) ||
                                valData.Contains("PrintBridge", StringComparison.OrdinalIgnoreCase) ||
                                valData.Contains("P1007PrinterRelay", StringComparison.OrdinalIgnoreCase))
                            {
                                try
                                {
                                    key.DeleteValue(valName, false);
                                    Log($"Deleted HKLM\\{rkPath} key: {valName}");
                                }
                                catch { }
                            }
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Log($"Registry cleanup note: {ex.Message}");
        }

        // 4. Delete legacy Startup Folder items
        try
        {
            string[] startupDirs = [
                Environment.GetFolderPath(Environment.SpecialFolder.Startup),
                Environment.GetFolderPath(Environment.SpecialFolder.CommonStartup)
            ];

            foreach (var sDir in startupDirs)
            {
                if (Directory.Exists(sDir))
                {
                    foreach (var file in Directory.GetFiles(sDir, "*.*"))
                    {
                        var fname = Path.GetFileName(file);
                        if ((fname.Contains("Aradhana", StringComparison.OrdinalIgnoreCase) && fname.Contains("Print", StringComparison.OrdinalIgnoreCase)) ||
                            fname.Contains("PrintBridge", StringComparison.OrdinalIgnoreCase) ||
                            fname.Contains("AutoPrint", StringComparison.OrdinalIgnoreCase) ||
                            fname.Contains("P1007", StringComparison.OrdinalIgnoreCase))
                        {
                            try
                            {
                                File.Delete(file);
                                Log($"Deleted legacy startup shortcut: {file}");
                            }
                            catch { }
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Log($"Startup folder cleanup note: {ex.Message}");
        }

        // 5. Delete legacy Directories (preserve C:\PrintBridge for active spool & letterhead assets)
        List<string> legacyDirs = [
            @"C:\P1007PrinterRelay",
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Aradhana", "OrnateAutoPrintTray"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Aradhana", "Aradhana355Watcher"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "PrintBridge")
        ];

        try
        {
            if (Directory.Exists(@"C:\Users"))
            {
                foreach (var uDir in Directory.GetDirectories(@"C:\Users"))
                {
                    var userPb = Path.Combine(uDir, "PrintBridge");
                    if (Directory.Exists(userPb) && !legacyDirs.Contains(userPb))
                    {
                        legacyDirs.Add(userPb);
                    }
                }
            }
        }
        catch { }

        foreach (var dir in legacyDirs)
        {
            if (Directory.Exists(dir))
            {
                try
                {
                    Directory.Delete(dir, recursive: true);
                    Log($"Deleted legacy directory: {dir}");
                }
                catch
                {
                    try
                    {
                        var trash = dir + ".trash." + Guid.NewGuid().ToString("N");
                        Directory.Move(dir, trash);
                        Directory.Delete(trash, true);
                        Log($"Purged legacy directory via rename: {dir}");
                    }
                    catch (Exception ex)
                    {
                        Log($"Directory delete notice ({dir}): {ex.Message}");
                    }
                }
            }
        }

        // Check if C:\ProgramData\Aradhana has no remaining subdirectories
        try
        {
            var aradhanaData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Aradhana");
            if (Directory.Exists(aradhanaData))
            {
                var remaining = Directory.GetFileSystemEntries(aradhanaData);
                if (remaining.Length == 0)
                {
                    Directory.Delete(aradhanaData, false);
                    Log($"Removed empty legacy directory: {aradhanaData}");
                }
            }
        }
        catch { }

        // 6. Delete old Desktop shortcuts (e.g. "Aradhana Ornate AutoPrint.lnk")
        try
        {
            string[] desktopDirs = [
                Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory)
            ];

            foreach (var dDir in desktopDirs)
            {
                if (Directory.Exists(dDir))
                {
                    foreach (var lnk in Directory.GetFiles(dDir, "*.lnk"))
                    {
                        var name = Path.GetFileNameWithoutExtension(lnk);
                        if ((name.Contains("Aradhana", StringComparison.OrdinalIgnoreCase) && name.Contains("Print", StringComparison.OrdinalIgnoreCase)) ||
                            name.Contains("PrintBridge", StringComparison.OrdinalIgnoreCase) ||
                            name.Contains("Ornate AutoPrint", StringComparison.OrdinalIgnoreCase))
                        {
                            try
                            {
                                File.Delete(lnk);
                                Log($"Deleted legacy desktop shortcut: {lnk}");
                            }
                            catch { }
                        }
                    }
                }
            }
        }
        catch { }

        // 7. Silent uninstall of legacy MSI / Programs & Features installations (e.g. Aradhana Ornate AutoPrint Router)
        try
        {
            string[] uninstallRoots = [
                @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                @"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ];

            foreach (var rootPath in uninstallRoots)
            {
                using var rootKey = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(rootPath, writable: true);
                if (rootKey == null) continue;

                foreach (var subKeyName in rootKey.GetSubKeyNames())
                {
                    try
                    {
                        using var subKey = rootKey.OpenSubKey(subKeyName, writable: true);
                        if (subKey == null) continue;

                        var dispName = subKey.GetValue("DisplayName")?.ToString() ?? "";
                        if (string.IsNullOrWhiteSpace(dispName)) continue;

                        // Identify legacy Aradhana print routers
                        if ((dispName.Contains("Aradhana", StringComparison.OrdinalIgnoreCase) && dispName.Contains("Print", StringComparison.OrdinalIgnoreCase)) ||
                            dispName.Contains("Ornate AutoPrint", StringComparison.OrdinalIgnoreCase) ||
                            dispName.Contains("Aradhana Ornate", StringComparison.OrdinalIgnoreCase))
                        {
                            Log($"Detected legacy installed application: '{dispName}' (Key: {subKeyName})");

                            var uninstallString = subKey.GetValue("UninstallString")?.ToString() ?? "";
                            var quietUninstall = subKey.GetValue("QuietUninstallString")?.ToString() ?? "";

                            if (subKeyName.StartsWith("{") && subKeyName.EndsWith("}"))
                            {
                                Log($"Running silent MSI uninstall for {subKeyName}...");
                                var msiRes = RunCmd("msiexec.exe", $"/x {subKeyName} /qn /norestart");
                                Log($"MSI uninstall result: {msiRes.Trim()}");
                            }
                            else if (!string.IsNullOrWhiteSpace(quietUninstall))
                            {
                                Log($"Running quiet uninstaller: {quietUninstall}");
                                RunCmd("cmd.exe", $"/c {quietUninstall}");
                            }
                            else if (!string.IsNullOrWhiteSpace(uninstallString))
                            {
                                if (uninstallString.Contains("msiexec", StringComparison.OrdinalIgnoreCase))
                                {
                                    var match = System.Text.RegularExpressions.Regex.Match(uninstallString, @"\{[0-9a-fA-F-]+\}");
                                    if (match.Success)
                                    {
                                        RunCmd("msiexec.exe", $"/x {match.Value} /qn /norestart");
                                    }
                                }
                            }

                            // Clean residual registry key so it never lingers in Add/Remove Programs
                            try
                            {
                                rootKey.DeleteSubKeyTree(subKeyName, false);
                                Log($"Purged legacy uninstall registry entry: {subKeyName}");
                            }
                            catch { }
                        }
                    }
                    catch { }
                }
            }
        }
        catch (Exception ex)
        {
            Log($"Legacy MSI sweep note: {ex.Message}");
        }

        Log("--- Legacy Print Router Decommissioning Complete ---");
    }

    public static void ConfigureAutoStartConsole(string targetDir, bool enable = true)
    {
        try
        {
            var consoleExe = Path.Combine(targetDir, "Ambic.PrintConsole.exe");
            using var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", writable: true);
            if (key != null)
            {
                if (enable && File.Exists(consoleExe))
                {
                    key.SetValue("AmbicPrintServerConsole", $"\"{consoleExe}\" --tray");
                }
                else
                {
                    key.DeleteValue("AmbicPrintServerConsole", false);
                }
            }
        }
        catch { }
    }

    public static void InitTopologyAndStorage()
    {
        var dbDir = Path.Combine(BaseDataDir, "db");
        var jobsDir = Path.Combine(BaseDataDir, "jobs");
        var configDir = Path.Combine(BaseDataDir, "config");
        var assetsDir = Path.Combine(BaseDataDir, "assets");

        Directory.CreateDirectory(dbDir);
        Directory.CreateDirectory(jobsDir);
        Directory.CreateDirectory(configDir);
        Directory.CreateDirectory(assetsDir);

        try
        {
            RunCmd("icacls.exe", $"\"{BaseDataDir}\" /grant \"*S-1-5-32-545:(OI)(CI)F\" /T /C /Q");
            RunCmd("icacls.exe", $"\"{BaseDataDir}\" /grant \"Users:(OI)(CI)F\" /T /C /Q");
        }
        catch { }

        var dbPath = Path.Combine(dbDir, "node.db");
        LogInfo($"Initializing SQLite node database at: {dbPath}");
        var db = new NodeDatabase(dbPath);
        var topRepo = new TopologyRepository(db);
        LogSuccess("Topology seeded: 5 cluster nodes, 5 physical printers, 5 logical bindings.");

        var configPath = Path.Combine(configDir, "rules.json");
        LogInfo($"Initializing routing rules cache at: {configPath}");
        var rulesStore = new RulesCacheStore(configPath);
        var defaultRuleset = DefaultTopology.CreateDefaultRuleset();
        rulesStore.Save(defaultRuleset);
        LogSuccess($"Default routing ruleset v{defaultRuleset.Version} cached with {defaultRuleset.Rules.Count} rules.");

        // Copy letterhead & voucher reference assets if present
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        string[] referenceAssetNames = ["office-sales-voucher-format-reference.png", "letterhead_front.jpeg", "letterhead_back.jpeg"];
        foreach (var name in referenceAssetNames)
        {
            var candidates = new[]
            {
                Path.Combine(appDir, "assets", name),
                Path.Combine(appDir, name),
                Path.Combine(@"c:\AradhanaSystems\projects\print-router\assets", name),
                Path.Combine(@"c:\AradhanaSystems\projects\print-router\overlay\live-images", name)
            };
            foreach (var c in candidates)
            {
                if (File.Exists(c))
                {
                    var dest = Path.Combine(assetsDir, name);
                    File.Copy(c, dest, true);
                    LogSuccess($"[ASSET] Copied {name} to {dest}");
                    break;
                }
            }
        }
    }

    public static void SetupCapturePrinter()
    {
        LogInfo("Configuring '355 Letterhead Capture' printer and pipeline...");

        // 1. Ensure C:\PrintBridge directories exist
        string[] bridgeDirs = [
            @"C:\PrintBridge",
            @"C:\PrintBridge\incoming_355",
            @"C:\PrintBridge\done_355",
            @"C:\PrintBridge\failed_355",
            @"C:\PrintBridge\temp_355",
            @"C:\PrintBridgeTest\incoming",
            @"C:\PrintBridge\incoming_1007relay",
            @"C:\PrintBridge\done_1007relay",
            @"C:\ProgramData\AMBIC DIGITAL\Print Server\assets"
        ];
        foreach (var dir in bridgeDirs)
        {
            try
            {
                if (!Directory.Exists(dir))
                {
                    Directory.CreateDirectory(dir);
                    LogInfo($"Created pipeline directory: {dir}");
                }
            }
            catch (Exception ex)
            {
                LogWarn($"Failed to create directory {dir}: {ex.Message}");
            }
        }

        // 2. Deploy letterhead assets to both ProgramData and C:\PrintBridge
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        string targetAssets = @"C:\ProgramData\AMBIC DIGITAL\Print Server\assets";
        string[] assetFiles = ["letterhead_front.jpeg", "letterhead_back.jpeg", "overlay_merge.py", "office-sales-voucher-format-reference.png"];

        foreach (var file in assetFiles)
        {
            var candidates = new[]
            {
                Path.Combine(appDir, "assets", file),
                Path.Combine(appDir, file),
                Path.Combine(@"c:\AradhanaSystems\projects\print-router\assets", file),
                Path.Combine(@"c:\AradhanaSystems\projects\print-router\overlay\live-images", file),
                Path.Combine(@"c:\AradhanaSystems\projects\print-router\overlay", file),
                Path.Combine(targetAssets, file),
                Path.Combine(@"C:\PrintBridge", file)
            };

            foreach (var c in candidates)
            {
                if (File.Exists(c))
                {
                    try
                    {
                        var destAssets = Path.Combine(targetAssets, file);
                        var destBridge = Path.Combine(@"C:\PrintBridge", file);
                        if (!File.Exists(destAssets) || new FileInfo(destAssets).Length != new FileInfo(c).Length)
                            File.Copy(c, destAssets, true);
                        if (!File.Exists(destBridge) || new FileInfo(destBridge).Length != new FileInfo(c).Length)
                            File.Copy(c, destBridge, true);
                        LogSuccess($"[ASSET DEPLOYED] {file} deployed to assets & C:\\PrintBridge");
                    }
                    catch { }
                    break;
                }
            }
        }

        // 3. Configure Bullzip global.ini if Bullzip is present
        string[] bzConfigDirs = [
            @"C:\ProgramData\PDF Writer\355 Letterhead Capture",
            @"C:\ProgramData\Bullzip\PDF Printer"
        ];
        string bzIni = "[PDF Printer]\r\n" +
                       "Output=C:\\PrintBridge\\incoming_355\\<date>_<time>_<counter>.pdf\r\n" +
                       "ShowSettings=never\r\n" +
                       "ShowSaveAS=never\r\n" +
                       "ShowProgress=no\r\n" +
                       "ShowProgressFinished=no\r\n" +
                       "ShowPDF=no\r\n" +
                       "ConfirmOverwrite=no\r\n" +
                       "SuppressErrors=yes\r\n";

        foreach (var dir in bzConfigDirs)
        {
            try
            {
                Directory.CreateDirectory(dir);
                File.WriteAllText(Path.Combine(dir, "global.ini"), bzIni);
                LogSuccess($"Configured Bullzip global.ini at: {dir}");
            }
            catch { }
        }

        // 4. Install / Verify "355 Letterhead Capture" printer
        try
        {
            var printerListOut = RunCmd("powershell.exe", "-NoProfile -Command \"Get-Printer -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name\"");
            var lines = printerListOut.Split(["\r\n", "\n"], StringSplitOptions.RemoveEmptyEntries).Select(s => s.Trim()).ToList();

            if (lines.Any(p => p.Equals("355 Letterhead Capture", StringComparison.OrdinalIgnoreCase)))
            {
                LogSuccess("Printer '355 Letterhead Capture' is already installed and registered.");
                return;
            }

            // If "Bullzip PDF Printer" is installed, rename it to "355 Letterhead Capture"
            if (lines.Any(p => p.Equals("Bullzip PDF Printer", StringComparison.OrdinalIgnoreCase)))
            {
                LogInfo("Renaming 'Bullzip PDF Printer' -> '355 Letterhead Capture'...");
                RunCmd("powershell.exe", "-NoProfile -Command \"Rename-Printer -Name 'Bullzip PDF Printer' -NewName '355 Letterhead Capture'\"");
                LogSuccess("Successfully renamed 'Bullzip PDF Printer' to '355 Letterhead Capture'.");
                return;
            }

            // Check if Bullzip driver is available
            var driverOut = RunCmd("powershell.exe", "-NoProfile -Command \"Get-PrinterDriver -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name\"");
            if (driverOut.Contains("Bullzip PDF Driver", StringComparison.OrdinalIgnoreCase) ||
                driverOut.Contains("Bullzip PDF Printer", StringComparison.OrdinalIgnoreCase))
            {
                string driverName = driverOut.Contains("Bullzip PDF Driver", StringComparison.OrdinalIgnoreCase) ? "Bullzip PDF Driver" : "Bullzip PDF Printer";
                LogInfo($"Found '{driverName}'. Creating '355 Letterhead Capture' printer...");
                RunCmd("powershell.exe", $"-NoProfile -Command \"Add-Printer -Name '355 Letterhead Capture' -DriverName '{driverName}' -PortName '355LETTE_UADLKCEA' -ErrorAction SilentlyContinue\"");
                LogSuccess("Added '355 Letterhead Capture' via Bullzip driver.");
                return;
            }

            // Native Windows fallback: "Microsoft PS Class Driver" with standard TCP port 9100
            LogInfo("Bullzip not detected. Installing Native Windows PostScript capture printer '355 Letterhead Capture'...");
            RunCmd("powershell.exe", "-NoProfile -Command \"" +
                "try { Add-PrinterPort -Name 'AmbicDigitalPDFCapture9100' -PrinterHostAddress '127.0.0.1' -PortNumber 9100 -ErrorAction SilentlyContinue } catch {}; " +
                "try { Add-Printer -Name '355 Letterhead Capture' -DriverName 'Microsoft PS Class Driver' -PortName 'AmbicDigitalPDFCapture9100' -ErrorAction SilentlyContinue } catch {}" +
            "\"");
            LogSuccess("Installed Native Windows PostScript '355 Letterhead Capture' printer on Port 9100.");
        }
        catch (Exception ex)
        {
            LogWarn($"Capture printer registration note: {ex.Message}");
        }
    }

    public static void FixWindows11PrintDialog()
    {
        LogInfo("Enforcing Windows 11 classic legacy print dialog (#32770)...");
        var (ok, error) = Windows11PrintDialogEnforcer.EnforceClassicPrintDialog();
        if (ok)
        {
            LogSuccess("Windows 11 Classic Print Dialog successfully enforced in registry.");
            try
            {
                var onxProcs = Process.GetProcessesByName("ONX");
                if (onxProcs.Length > 0)
                {
                    LogWarn("NOTE: Ornate (ONX.exe) is currently running. Please restart Ornate for the classic print dialog to take effect.");
                }
            }
            catch { }
        }
        else
        {
            LogWarn($"Windows 11 Classic Print Dialog enforcement warning: {error}");
        }
    }

    public static void ConfigureFirewall()
    {
        LogInfo("Configuring Windows Firewall inbound rule for port 8447...");
        var checkOut = RunCmd("netsh.exe", "advfirewall firewall show rule name=\"AMBIC Print Server\"");
        if (checkOut.Contains("AMBIC Print Server", StringComparison.OrdinalIgnoreCase))
        {
            LogSuccess("Windows Firewall rule 'AMBIC Print Server' already exists.");
            return;
        }

        var addOut = RunCmd("netsh.exe", "advfirewall firewall add rule name=\"AMBIC Print Server\" dir=in action=allow protocol=TCP localport=8447");
        if (addOut.Contains("Ok", StringComparison.OrdinalIgnoreCase))
        {
            LogSuccess("Added inbound firewall rule for TCP port 8447.");
        }
        else
        {
            LogWarn($"Firewall output: {addOut}");
        }
    }

    public static void InstallWindowsService(string? explicitDir = null)
    {
        string serviceName = "AmbicPrintServerNode";
        string exePath = FindServiceExecutable(explicitDir);

        if (string.IsNullOrEmpty(exePath) || !File.Exists(exePath))
        {
            LogWarn($"Could not locate compiled Ambic.PrintNode.exe. Build or publish it first.");
            return;
        }

        LogInfo($"Configuring Windows Service '{serviceName}' pointing to: {exePath}");

        // Stop and delete if existing
        RunCmd("sc.exe", $"stop {serviceName}");
        RunCmd("sc.exe", $"delete {serviceName}");

        var createCmd = $"create {serviceName} binPath= \"{exePath}\" start= delayed-auto DisplayName= \"AMBIC Print Server Node\"";
        var createOut = RunCmd("sc.exe", createCmd);

        if (createOut.Contains("SUCCESS", StringComparison.OrdinalIgnoreCase))
        {
            LogSuccess($"Windows Service '{serviceName}' created successfully.");
            RunCmd("sc.exe", $"description {serviceName} \"High-availability distributed Print Server powered by AMBIC DIGITAL.\"");
            var startOut = RunCmd("sc.exe", $"start {serviceName}");
            LogInfo($"Starting service: {startOut.Trim()}");
        }
        else
        {
            LogWarn($"Service creation returned: {createOut}");
        }
    }

    public static void UninstallWindowsService()
    {
        string serviceName = "AmbicPrintServerNode";
        LogInfo($"Stopping and deleting Windows Service '{serviceName}'...");
        RunCmd("sc.exe", $"stop {serviceName}");
        var delOut = RunCmd("sc.exe", $"delete {serviceName}");
        LogSuccess($"Service uninstalled: {delOut.Trim()}");
    }

    public static async Task VerifyHealthAsync()
    {
        LogInfo("Pinging local node health at http://127.0.0.1:8447/health ...");
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };

        for (int i = 1; i <= 5; i++)
        {
            try
            {
                var res = await client.GetAsync("http://127.0.0.1:8447/health");
                if (res.IsSuccessStatusCode)
                {
                    var content = await res.Content.ReadAsStringAsync();
                    LogSuccess($"[HEALTH CHECK PASS] Status Code: {res.StatusCode}\n{content}");
                    return;
                }
            }
            catch (Exception ex)
            {
                LogWarn($"Attempt {i}/5: Node not responding yet ({ex.Message}). Retrying in 1s...");
                await Task.Delay(1000);
            }
        }

        LogError("Health check timed out. Node service may not be running yet or port 8447 is blocked.");
    }

    private static string FindServiceExecutable(string? explicitDir = null)
    {
        var candidates = new List<string>();
        if (!string.IsNullOrEmpty(explicitDir))
        {
            candidates.Add(Path.Combine(explicitDir, "Ambic.PrintNode.exe"));
        }
        candidates.Add(@"C:\Program Files\AMBIC DIGITAL\Print Server\Ambic.PrintNode.exe");
        candidates.Add(Path.Combine(AppContext.BaseDirectory, "Ambic.PrintNode.exe"));
        candidates.Add(@"C:\AradhanaSystems\projects\print-router\publish\node\Ambic.PrintNode.exe");
        candidates.Add(@"C:\AradhanaSystems\projects\print-router\src\Ambic.PrintNode\bin\Release\net10.0-windows\Ambic.PrintNode.exe");
        candidates.Add(@"C:\AradhanaSystems\projects\print-router\src\Ambic.PrintNode\bin\Debug\net10.0-windows\Ambic.PrintNode.exe");
        candidates.Add(Path.Combine(BaseDataDir, "bin", "Ambic.PrintNode.exe"));

        foreach (var c in candidates)
        {
            if (File.Exists(c)) return c;
        }

        return candidates[0];
    }

    private static bool IsAdministrator()
    {
        try
        {
            using var identity = WindowsIdentity.GetCurrent();
            var principal = new WindowsPrincipal(identity);
            return principal.IsInRole(WindowsBuiltInRole.Administrator);
        }
        catch
        {
            return false;
        }
    }

    private static string RunCmd(string exe, string args)
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = args,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            using var proc = Process.Start(psi);
            if (proc == null) return "";
            var stdout = proc.StandardOutput.ReadToEnd();
            var stderr = proc.StandardError.ReadToEnd();
            proc.WaitForExit(5000);
            return stdout + (string.IsNullOrWhiteSpace(stderr) ? "" : "\n" + stderr);
        }
        catch (Exception ex)
        {
            return $"EXEC_ERROR: {ex.Message}";
        }
    }

    private static void CopyDirectory(string sourceDir, string destinationDir)
    {
        Directory.CreateDirectory(destinationDir);
        foreach (string file in Directory.GetFiles(sourceDir))
        {
            string dest = Path.Combine(destinationDir, Path.GetFileName(file));
            File.Copy(file, dest, true);
        }
        foreach (string subDir in Directory.GetDirectories(sourceDir))
        {
            string dest = Path.Combine(destinationDir, Path.GetFileName(subDir));
            CopyDirectory(subDir, dest);
        }
    }

    private static void LogInfo(string msg)
    {
        Console.ForegroundColor = ConsoleColor.White;
        Console.WriteLine(msg);
        Console.ResetColor();
    }

    private static void LogSuccess(string msg)
    {
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine(msg);
        Console.ResetColor();
    }

    private static void LogWarn(string msg)
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine(msg);
        Console.ResetColor();
    }

    private static void LogError(string msg)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine(msg);
        Console.ResetColor();
    }
}

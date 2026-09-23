namespace Ambic.PrintConsole;

static class Program
{
    /// <summary>
    ///  The main entry point for the application.
    /// </summary>
    [STAThread]
    static void Main(string[] args)
    {
        if (args.Contains("--generate-icon"))
        {
            var assetDir = @"c:\AradhanaSystems\projects\print-router\assets";
            Directory.CreateDirectory(assetDir);
            var icoPath = Path.Combine(assetDir, "app.ico");
            IconGenerator.Generate(icoPath);
            File.Copy(icoPath, @"c:\AradhanaSystems\projects\print-router\src\Ambic.PrintInstaller\app.ico", true);
            File.Copy(icoPath, @"c:\AradhanaSystems\projects\print-router\src\Ambic.PrintConsole\app.ico", true);
            Console.WriteLine($"Icon generated successfully at {icoPath} (Size: {new FileInfo(icoPath).Length} bytes)");
            return;
        }

        AppDomain.CurrentDomain.UnhandledException += (s, e) =>
        {
            try
            {
                var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
                Directory.CreateDirectory(dir);
                File.AppendAllText(Path.Combine(dir, "crash.log"), $"[{DateTime.Now}] UNHANDLED DOMAIN EXCEPTION:\n{e.ExceptionObject}\n\n");
            }
            catch { }
        };

        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) =>
        {
            try
            {
                var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
                Directory.CreateDirectory(dir);
                File.AppendAllText(Path.Combine(dir, "crash.log"), $"[{DateTime.Now}] THREAD EXCEPTION:\n{e.Exception}\n\n");
            }
            catch { }
        };

        Application.ApplicationExit += (s, e) =>
        {
            try
            {
                var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
                File.AppendAllText(Path.Combine(dir, "watcher.log"), $"[{DateTime.Now:HH:mm:ss}] [APP EXIT] Application.ApplicationExit fired!\n");
            }
            catch { }
        };

        try
        {
            Ambic.PrintAdapters.Ornate.Windows11PrintDialogEnforcer.EnforceClassicPrintDialog();
            ApplicationConfiguration.Initialize();

            var isTray = args.Any(a => a.Equals("--tray", StringComparison.OrdinalIgnoreCase) || a.Equals("--minimized", StringComparison.OrdinalIgnoreCase));
            var form = new FormMain();

            Application.Run(new PrintServerAppContext(form, isTray));
        }
        catch (Exception ex)
        {
            var logPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server", "crash.log");
            File.WriteAllText(logPath, ex.ToString());
            MessageBox.Show($"Application failed to start:\n\n{ex.Message}\n\nDetails saved to: {logPath}", "Startup Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }    
}

internal class PrintServerAppContext : ApplicationContext
{
    private readonly FormMain _form;

    public PrintServerAppContext(FormMain form, bool startMinimized)
    {
        _form = form;
        _form.FormClosed += (s, e) => ExitThread();
        if (!startMinimized)
        {
            _form.Show();
        }
    }
}
using System.Diagnostics;
using Ambic.PrintCore.Models;

namespace Ambic.PrintAdapters.Pdf;

public class PdfOverlayOptions
{
    public string? PythonPath { get; set; }
    public string? ScriptPath { get; set; }
    public string? FrontImagePath { get; set; }
    public string? BackImagePath { get; set; }
    public int TimeoutSeconds { get; set; } = 30;
}

public class OverlayResult
{
    public bool Success { get; set; }
    public string? OutputPdfPath { get; set; }
    public string? ErrorMessage { get; set; }
    public TimeSpan Duration { get; set; }
}

public class PdfOverlayService
{
    private readonly PdfOverlayOptions _options;
    private const string EmbeddedScript = @"# AMBIC DIGITAL 355sdnw letterhead overlay
import re
import sys
import fitz

WHITE_BG_PATTERN = re.compile(rb""1 1 1 rg\s*\n[\d.]+ [\d.]+ [\d.]+ [\d.]+ re\s*\nf\*?\s*\n"")

def strip_full_page_white_fill(doc, page):
    xrefs = page.get_contents()
    if not xrefs:
        return
    xref = xrefs[0]
    raw = doc.xref_stream(xref)
    new_raw, count = WHITE_BG_PATTERN.subn(b"""", raw, count=1)
    if count > 0:
        doc.update_stream(xref, new_raw)

def main():
    if len(sys.argv) != 5:
        print(""Usage: overlay_merge.py <input_bill.pdf> <output_merged.pdf> <front_image> <back_image>"")
        sys.exit(1)
    input_pdf_path, output_pdf_path, front_image_path, back_image_path = sys.argv[1:5]
    doc = fitz.open(input_pdf_path)
    if doc.page_count == 0:
        print(""ERROR: input PDF has no pages"")
        sys.exit(1)
    front_page = doc[0]
    rect = front_page.rect
    strip_full_page_white_fill(doc, front_page)
    front_page.insert_image(rect, filename=front_image_path, overlay=False)
    back_page = doc.new_page(pno=1, width=rect.width, height=rect.height)
    back_page.insert_image(back_page.rect, filename=back_image_path)
    doc.save(output_pdf_path)
    doc.close()
    print(f""OK: wrote {output_pdf_path} ({rect.width}x{rect.height}pt, 2 pages)"")

if __name__ == ""__main__"":
    main()
";

    public PdfOverlayService(PdfOverlayOptions? options = null)
    {
        _options = options ?? new PdfOverlayOptions();
    }

    public async Task<OverlayResult> ProcessAsync(string inputPdfPath, string outputPdfPath, CancellationToken ct = default)
    {
        var sw = Stopwatch.StartNew();

        if (!File.Exists(inputPdfPath))
        {
            return new OverlayResult
            {
                Success = false,
                ErrorMessage = $"Input PDF does not exist: {inputPdfPath}",
                Duration = sw.Elapsed
            };
        }

        var inputInfo = new FileInfo(inputPdfPath);
        if (inputInfo.Length == 0)
        {
            return new OverlayResult
            {
                Success = false,
                ErrorMessage = $"Input PDF is 0 bytes: {inputPdfPath}",
                Duration = sw.Elapsed
            };
        }

        string frontImg = ResolveAssetPath(_options.FrontImagePath, "letterhead_front.jpeg");
        string backImg = ResolveAssetPath(_options.BackImagePath, "letterhead_back.jpeg");

        if (!File.Exists(frontImg))
        {
            return new OverlayResult
            {
                Success = false,
                ErrorMessage = $"Front letterhead image not found: {frontImg}",
                Duration = sw.Elapsed
            };
        }

        if (!File.Exists(backImg))
        {
            return new OverlayResult
            {
                Success = false,
                ErrorMessage = $"Back letterhead image not found: {backImg}",
                Duration = sw.Elapsed
            };
        }

        string scriptPath = ResolveScriptPath();
        var (pythonExe, pythonArgsPrefix) = ResolvePythonCommand();

        var outputDir = Path.GetDirectoryName(Path.GetFullPath(outputPdfPath));
        if (!string.IsNullOrEmpty(outputDir) && !Directory.Exists(outputDir))
        {
            Directory.CreateDirectory(outputDir);
        }

        var fullArgs = $"{pythonArgsPrefix}\"{scriptPath}\" \"{Path.GetFullPath(inputPdfPath)}\" \"{Path.GetFullPath(outputPdfPath)}\" \"{Path.GetFullPath(frontImg)}\" \"{Path.GetFullPath(backImg)}\"";

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = pythonExe,
                Arguments = fullArgs,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            using var proc = new Process { StartInfo = psi };
            proc.Start();

            var outTask = proc.StandardOutput.ReadToEndAsync(ct);
            var errTask = proc.StandardError.ReadToEndAsync(ct);

            var completed = await Task.Run(() => proc.WaitForExit((int)TimeSpan.FromSeconds(_options.TimeoutSeconds).TotalMilliseconds), ct);
            if (!completed)
            {
                try { proc.Kill(true); } catch { }
                return new OverlayResult
                {
                    Success = false,
                    ErrorMessage = $"Overlay script timed out after {_options.TimeoutSeconds}s",
                    Duration = sw.Elapsed
                };
            }

            string stdout = await outTask;
            string stderr = await errTask;

            if (proc.ExitCode != 0 || !File.Exists(outputPdfPath))
            {
                return new OverlayResult
                {
                    Success = false,
                    ErrorMessage = $"Overlay failed with exit code {proc.ExitCode}. Output: {stdout}. Error: {stderr}",
                    Duration = sw.Elapsed
                };
            }

            var outInfo = new FileInfo(outputPdfPath);
            if (outInfo.Length == 0)
            {
                return new OverlayResult
                {
                    Success = false,
                    ErrorMessage = "Generated output PDF is 0 bytes",
                    Duration = sw.Elapsed
                };
            }

            return new OverlayResult
            {
                Success = true,
                OutputPdfPath = outputPdfPath,
                Duration = sw.Elapsed
            };
        }
        catch (Exception ex)
        {
            return new OverlayResult
            {
                Success = false,
                ErrorMessage = $"Exception running overlay merge: {ex.Message}",
                Duration = sw.Elapsed
            };
        }
    }

    private string ResolveScriptPath()
    {
        if (!string.IsNullOrEmpty(_options.ScriptPath) && File.Exists(_options.ScriptPath))
        {
            return Path.GetFullPath(_options.ScriptPath);
        }

        // Check well-known locations
        string[] candidates = [
            Path.Combine(AppContext.BaseDirectory, "overlay_merge.py"),
            Path.Combine(AppContext.BaseDirectory, "overlay", "overlay_merge.py"),
            @"C:\ProgramData\AMBIC DIGITAL\Print Server\assets\overlay_merge.py",
            @"C:\AradhanaSystems\projects\print-router\overlay\overlay_merge.py"
        ];

        foreach (var c in candidates)
        {
            if (File.Exists(c)) return c;
        }

        // Write out embedded script to AppData
        string fallbackDir = @"C:\ProgramData\AMBIC DIGITAL\Print Server\assets";
        Directory.CreateDirectory(fallbackDir);
        string fallbackScript = Path.Combine(fallbackDir, "overlay_merge.py");
        File.WriteAllText(fallbackScript, EmbeddedScript);
        return fallbackScript;
    }

    private string ResolveAssetPath(string? customPath, string defaultFileName)
    {
        if (!string.IsNullOrEmpty(customPath) && File.Exists(customPath))
        {
            return Path.GetFullPath(customPath);
        }

        string[] candidates = [
            Path.Combine(AppContext.BaseDirectory, "assets", defaultFileName),
            Path.Combine(AppContext.BaseDirectory, defaultFileName),
            Path.Combine(@"C:\ProgramData\AMBIC DIGITAL\Print Server\assets", defaultFileName),
            Path.Combine(@"C:\AradhanaSystems\projects\print-router\overlay\live-images", defaultFileName)
        ];

        foreach (var c in candidates)
        {
            if (File.Exists(c)) return c;
        }

        return Path.Combine(@"C:\ProgramData\AMBIC DIGITAL\Print Server\assets", defaultFileName);
    }

    private (string Exe, string ArgsPrefix) ResolvePythonCommand()
    {
        if (!string.IsNullOrEmpty(_options.PythonPath))
        {
            return (_options.PythonPath, "");
        }

        // Try py launcher first
        try
        {
            var p = Process.Start(new ProcessStartInfo
            {
                FileName = "py",
                Arguments = "-3 -V",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            });
            if (p != null)
            {
                p.WaitForExit(1000);
                if (p.ExitCode == 0) return ("py", "-3 ");
            }
        }
        catch { }

        // Try standard python
        try
        {
            var p = Process.Start(new ProcessStartInfo
            {
                FileName = "python",
                Arguments = "-V",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            });
            if (p != null)
            {
                p.WaitForExit(1000);
                if (p.ExitCode == 0) return ("python", "");
            }
        }
        catch { }

        return ("python", "");
    }
}

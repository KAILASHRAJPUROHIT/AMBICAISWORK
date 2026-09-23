using Ambic.PrintCore.Models;
using System.Security.Cryptography;

namespace Ambic.Print.Storage.Queues;

public class DiskJobQueue
{
    private readonly string _baseDir;
    private readonly string _pendingDir;
    private readonly string _processingDir;
    private readonly string _completedDir;
    private readonly string _failedDir;
    private readonly string _heldDir;

    public DiskJobQueue(string baseDir)
    {
        _baseDir = baseDir;
        _pendingDir = Path.Combine(_baseDir, "pending");
        _processingDir = Path.Combine(_baseDir, "processing");
        _completedDir = Path.Combine(_baseDir, "completed");
        _failedDir = Path.Combine(_baseDir, "failed");
        _heldDir = Path.Combine(_baseDir, "held");

        Directory.CreateDirectory(_pendingDir);
        Directory.CreateDirectory(_processingDir);
        Directory.CreateDirectory(_completedDir);
        Directory.CreateDirectory(_failedDir);
        Directory.CreateDirectory(_heldDir);
    }

    public async Task<string> EnqueueAsync(string jobId, byte[] payload, PayloadType type)
    {
        var ext = type switch
        {
            PayloadType.Pdf => ".pdf",
            PayloadType.Raw => ".prn",
            PayloadType.EscPos => ".bin",
            PayloadType.Text => ".txt",
            PayloadType.Image => ".png",
            _ => ".dat"
        };
        var filename = $"{jobId}{ext}";
        var path = Path.Combine(_pendingDir, filename);
        var tempPath = Path.Combine(_pendingDir, $"{filename}.tmp");

        await File.WriteAllBytesAsync(tempPath, payload);
        File.Move(tempPath, path, overwrite: true);
        return path;
    }

    public string? MarkProcessing(string jobId, PayloadType type)
    {
        var ext = GetExt(type);
        var src = Path.Combine(_pendingDir, $"{jobId}{ext}");
        var dst = Path.Combine(_processingDir, $"{jobId}{ext}");
        if (!File.Exists(src)) return null;

        File.Move(src, dst, overwrite: true);
        return dst;
    }

    public void MarkCompleted(string jobId, PayloadType type)
    {
        MoveJobFile(jobId, type, _processingDir, _completedDir);
    }

    public void MarkFailed(string jobId, PayloadType type)
    {
        MoveJobFile(jobId, type, _processingDir, _failedDir);
    }

    public void MarkHeld(string jobId, PayloadType type)
    {
        MoveJobFile(jobId, type, _processingDir, _heldDir);
    }

    private void MoveJobFile(string jobId, PayloadType type, string fromDir, string toDir)
    {
        var ext = GetExt(type);
        var src = Path.Combine(fromDir, $"{jobId}{ext}");
        var dst = Path.Combine(toDir, $"{jobId}{ext}");
        if (File.Exists(src))
        {
            File.Move(src, dst, overwrite: true);
        }
    }

    private static string GetExt(PayloadType type) => type switch
    {
        PayloadType.Pdf => ".pdf",
        PayloadType.Raw => ".prn",
        PayloadType.EscPos => ".bin",
        PayloadType.Text => ".txt",
        PayloadType.Image => ".png",
        _ => ".dat"
    };

    public static string ComputeSha256(byte[] data)
    {
        using var sha = SHA256.Create();
        var hash = sha.ComputeHash(data);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }
}

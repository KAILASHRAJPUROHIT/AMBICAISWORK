using System.Net.Http.Json;
using System.Text.Json;
using Ambic.PrintCore.Models;

namespace Ambic.PrintCore.Network;

public class SubmitJobRequest
{
    public string JobId { get; set; } = string.Empty;
    public string IdempotencyKey { get; set; } = string.Empty;
    public string DocumentType { get; set; } = "DOCUMENT";
    public string Destination { get; set; } = string.Empty; // Logical printer ID
    public int Copies { get; set; } = 1;
    public PayloadType PayloadType { get; set; } = PayloadType.Raw;
    public string PayloadBase64 { get; set; } = string.Empty;
    public string? Sha256 { get; set; }
    public string SourceNodeId { get; set; } = string.Empty;
    public string SourceUser { get; set; } = string.Empty;
    public string SourceProcess { get; set; } = string.Empty;
}

public class SubmitJobResponse
{
    public string JobId { get; set; } = string.Empty;
    public string State { get; set; } = "ACCEPTED";
    public string Detail { get; set; } = string.Empty;
    public bool IsDuplicate { get; set; }
}

public class NodeHealthResponse
{
    public string NodeId { get; set; } = string.Empty;
    public string ServiceVersion { get; set; } = "1.0.0";
    public string Status { get; set; } = "HEALTHY";
    public long UptimeSeconds { get; set; }
    public string ConfigVersion { get; set; } = "2026.09.22.001";
    public bool EmergencyBypassActive { get; set; }
    public List<string> AvailablePrinters { get; set; } = new();
}

public class NodeClient
{
    private readonly HttpClient _httpClient;
    private static readonly JsonSerializerOptions JsonOpts = new() { PropertyNameCaseInsensitive = true };

    public NodeClient(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.Timeout = TimeSpan.FromSeconds(15);
    }

    public async Task<SubmitJobResponse?> SubmitJobAsync(string targetHostIp, int port, SubmitJobRequest request)
    {
        var url = $"http://{targetHostIp}:{port}/api/v1/jobs";
        var res = await _httpClient.PostAsJsonAsync(url, request, JsonOpts);
        res.EnsureSuccessStatusCode();
        return await res.Content.ReadFromJsonAsync<SubmitJobResponse>(JsonOpts);
    }

    public async Task<NodeHealthResponse?> GetHealthAsync(string targetHostIp, int port)
    {
        var url = $"http://{targetHostIp}:{port}/health";
        var res = await _httpClient.GetAsync(url);
        if (!res.IsSuccessStatusCode) return null;
        return await res.Content.ReadFromJsonAsync<NodeHealthResponse>(JsonOpts);
    }
}

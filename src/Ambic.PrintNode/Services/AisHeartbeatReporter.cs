using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ambic.PrintCore.Spooler;
using Ambic.Print.Storage.Repositories;

namespace Ambic.PrintNode.Services;

/// <summary>
/// Outbound-only telemetry. Nodes never need an open management port: they
/// report state through the AIS HTTPS gateway using a timestamped HMAC.
/// Commands will later be collected by the node from that same outbound path.
/// </summary>
public sealed class AisHeartbeatReporter : BackgroundService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;
    private readonly RulesCacheStore _rules;
    private readonly PrintEngineService _engine;
    private readonly ILogger<AisHeartbeatReporter> _logger;

    public AisHeartbeatReporter(IHttpClientFactory httpClientFactory, IConfiguration configuration, RulesCacheStore rules, PrintEngineService engine, ILogger<AisHeartbeatReporter> logger)
    {
        _httpClientFactory = httpClientFactory;
        _configuration = configuration;
        _rules = rules;
        _engine = engine;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var seconds = Math.Clamp(_configuration.GetValue("AisControl:HeartbeatSeconds", 30), 15, 300);
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(seconds));
        while (!stoppingToken.IsCancellationRequested)
        {
            await ReportOnceAsync(stoppingToken);
            await timer.WaitForNextTickAsync(stoppingToken);
        }
    }

    private async Task ReportOnceAsync(CancellationToken cancellationToken)
    {
        var centralUrl = _configuration["AisControl:CentralUrl"];
        var sharedToken = _configuration["AisControl:SharedToken"];
        if (string.IsNullOrWhiteSpace(centralUrl) || string.IsNullOrWhiteSpace(sharedToken)) return;
        if (!Uri.TryCreate(centralUrl, UriKind.Absolute, out var baseUri) || baseUri.Scheme != Uri.UriSchemeHttps)
        {
            _logger.LogWarning("AIS heartbeat CentralUrl must be HTTPS; report skipped.");
            return;
        }

        var printers = PrinterDiscovery.DiscoverLocalPrinters();
        var nodeId = _configuration["NodeId"] ?? Environment.MachineName;
        var payload = new
        {
            nodeId,
            stationName = _configuration["StationName"] ?? Environment.MachineName,
            observedAtUtc = DateTime.UtcNow,
            serviceVersion = typeof(AisHeartbeatReporter).Assembly.GetName().Version?.ToString() ?? "unknown",
            emergencyBypassActive = _engine.EmergencyBypassActive,
            printerSummary = new { total = printers.Count, online = printers.Count(p => p.IsOnline), offline = printers.Count(p => !p.IsOnline) },
            printers = printers.Select(p => new { p.Name, p.IsOnline, status = p.Status, p.DriverName, p.PortName }),
            routing = new { ruleCount = _rules.LoadHubConfig().Rules.Count }
        };
        var body = JsonSerializer.Serialize(payload);
        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString();
        var signature = Convert.ToHexString(HMACSHA256.HashData(Encoding.UTF8.GetBytes(sharedToken), Encoding.UTF8.GetBytes($"{timestamp}.{body}"))).ToLowerInvariant();

        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseUri, "/api/print-router/nodes/heartbeat"))
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json")
            };
            request.Headers.Add("x-ais-node-id", nodeId);
            request.Headers.Add("x-ais-timestamp", timestamp);
            request.Headers.Add("x-ais-signature", signature);
            using var response = await _httpClientFactory.CreateClient("ais-heartbeat").SendAsync(request, cancellationToken);
            if (!response.IsSuccessStatusCode) _logger.LogWarning("AIS heartbeat rejected with HTTP {StatusCode}", (int)response.StatusCode);
        }
        catch (Exception ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "AIS heartbeat failed");
        }
    }
}

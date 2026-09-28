using Ambic.Print.Storage.Database;
using Ambic.Print.Storage.Queues;
using Ambic.Print.Storage.Repositories;
using Ambic.PrintAdapters.Pdf;
using Ambic.PrintAdapters.Thermal;
using Ambic.PrintCore.Models;
using Ambic.PrintCore.Network;
using Ambic.PrintCore.Spooler;
using Ambic.PrintNode.Services;
using Microsoft.AspNetCore.Mvc;
using System.Security.Cryptography;

var builder = WebApplication.CreateBuilder(args);

// Enable Windows Service hosting
builder.Host.UseWindowsService();

builder.Services.ConfigureHttpJsonOptions(opts =>
{
    opts.SerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
});

// Determine Base Data Path
var baseDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AMBIC DIGITAL", "Print Server");
Directory.CreateDirectory(baseDir);

var dbPath = Path.Combine(baseDir, "db", "node.db");
var jobsDir = Path.Combine(baseDir, "jobs");
var configPath = Path.Combine(baseDir, "config", "rules.json");

// Register Services
builder.Services.AddSingleton(new NodeDatabase(dbPath));
builder.Services.AddSingleton<IdempotencyStore>();
builder.Services.AddSingleton<JobRepository>();
builder.Services.AddSingleton<TopologyRepository>();
builder.Services.AddSingleton(new DiskJobQueue(jobsDir));
builder.Services.AddSingleton(new RulesCacheStore(configPath));
builder.Services.AddHttpClient<NodeClient>();
builder.Services.AddSingleton<PrintEngineService>();
builder.Services.AddSingleton<AisControlAuthenticator>();

builder.Services.AddSingleton<PdfOverlayService>();
builder.Services.AddSingleton<ThermalReceiptFormatter>();

// Configure Kestrel to listen on 8447
var port = builder.Configuration.GetValue<int>("Port", 8447);
builder.WebHost.ConfigureKestrel(opts =>
{
    opts.ListenAnyIP(port);
});

var app = builder.Build();

static IResult AisUnauthorized() => Results.Json(
    new { error = "AIS node control is not configured or the bearer credential is invalid." },
    statusCode: StatusCodes.Status401Unauthorized);

static string HashFile(string path)
{
    if (!File.Exists(path)) return "missing";
    using var stream = File.OpenRead(path);
    return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
}

// Endpoints
app.MapGet("/health", ([FromServices] PrintEngineService engine, [FromServices] TopologyRepository topology, IConfiguration cfg) =>
{
    var localPrinters = PrinterDiscovery.DiscoverLocalPrinters();
    return Results.Ok(new NodeHealthResponse
    {
        NodeId = cfg["NodeId"] ?? Ambic.PrintCore.Config.DefaultTopology.DellServerNodeId,
        ServiceVersion = "1.0.0",
        Status = "HEALTHY",
        UptimeSeconds = (long)(DateTime.UtcNow - System.Diagnostics.Process.GetCurrentProcess().StartTime.ToUniversalTime()).TotalSeconds,
        ConfigVersion = "2026.09.22.001",
        EmergencyBypassActive = engine.EmergencyBypassActive,
        AvailablePrinters = localPrinters.Where(p => p.IsOnline).Select(p => p.Name).ToList()
    });
});

// AIS-only read model. This is the sole endpoint the dashboard may use for a
// PC selector and printer/rule state. It requires a per-node secret and does
// not expose any command or print operation.
app.MapGet("/api/v1/ais/node-state", (
    HttpRequest request,
    [FromServices] AisControlAuthenticator auth,
    [FromServices] PrintEngineService engine,
    [FromServices] TopologyRepository topology,
    [FromServices] RulesCacheStore rules,
    IConfiguration cfg) =>
{
    if (!auth.IsAuthorized(request)) return AisUnauthorized();

    var discovered = PrinterDiscovery.DiscoverLocalPrinters();
    var configured = rules.LoadHubConfig();
    var online = discovered.Count(p => p.IsOnline);
    var status = engine.EmergencyBypassActive ? "DEGRADED" : "HEALTHY";

    return Results.Ok(new
    {
        nodeId = cfg["NodeId"] ?? Environment.MachineName,
        stationName = cfg["StationName"] ?? Environment.MachineName,
        status,
        observedAtUtc = DateTime.UtcNow,
        serviceVersion = typeof(Program).Assembly.GetName().Version?.ToString() ?? "unknown",
        uptimeSeconds = (long)(DateTime.UtcNow - System.Diagnostics.Process.GetCurrentProcess().StartTime.ToUniversalTime()).TotalSeconds,
        emergencyBypassActive = engine.EmergencyBypassActive,
        printerSummary = new { total = discovered.Count, online, offline = discovered.Count - online },
        printers = discovered.Select(p => new { p.Name, p.IsOnline, status = p.Status, p.DriverName, p.PortName, observedAtUtc = DateTime.UtcNow }),
        routing = new
        {
            configHash = HashFile(configPath),
            ruleCount = configured.Rules.Count,
            writesEnabled = auth.WritesEnabled
        }
    });
});

// Deliberate safe stop. The UI can display the selected PC and its current
// rules, but cannot mutate a router until command signing, version checks and
// a rollback record are deployed together.
app.MapPost("/api/v1/ais/routing", (HttpRequest request, [FromServices] AisControlAuthenticator auth) =>
{
    if (!auth.IsAuthorized(request)) return AisUnauthorized();
    return auth.WritesEnabled
        ? Results.StatusCode(StatusCodes.Status501NotImplemented)
        : Results.Json(new { error = "Routing writes are disabled until signed commands and rollback are configured." }, statusCode: StatusCodes.Status423Locked);
});

app.MapGet("/api/v1/printers", ([FromServices] TopologyRepository topology) =>
{
    return Results.Ok(topology.GetAllPhysicalPrinters());
});

app.MapGet("/api/v1/printers/discovery", ([FromServices] TopologyRepository topology) =>
{
    var physical = topology.GetAllPhysicalPrinters();
    var discovered = PrinterDiscovery.DiscoverLocalPrinters();
    return Results.Ok(new
    {
        registeredPrinters = physical,
        localDiscoveredPrinters = discovered
    });
});

app.MapPost("/api/v1/jobs", async ([FromBody] SubmitJobRequest req, [FromServices] PrintEngineService engine) =>
{
    if (string.IsNullOrWhiteSpace(req.JobId) || string.IsNullOrWhiteSpace(req.IdempotencyKey) || string.IsNullOrWhiteSpace(req.Destination))
    {
        return Results.BadRequest(new SubmitJobResponse
        {
            JobId = req.JobId ?? "",
            State = "REJECTED",
            Detail = "Missing required fields: jobId, idempotencyKey, destination"
        });
    }

    var result = await engine.ProcessJobSubmissionAsync(req);
    return Results.Ok(result);
});

app.MapPost("/api/v1/jobs/estimate", async ([FromBody] SubmitEstimateRequest req, [FromServices] ThermalReceiptFormatter formatter, [FromServices] PrintEngineService engine) =>
{
    if (req.Receipt == null || string.IsNullOrWhiteSpace(req.Receipt.EstimateNumber))
    {
        return Results.BadRequest(new SubmitJobResponse
        {
            JobId = req.JobId ?? "",
            State = "REJECTED",
            Detail = "Invalid estimate receipt payload or missing estimate number"
        });
    }

    var jobId = string.IsNullOrWhiteSpace(req.JobId) ? $"EST-{Guid.NewGuid():N}" : req.JobId;
    var idempotencyKey = string.IsNullOrWhiteSpace(req.IdempotencyKey) ? $"idem-est-{req.Receipt.EstimateNumber}" : req.IdempotencyKey;

    var formattedEscPos = formatter.FormatEstimate(req.Receipt);
    var base64 = Convert.ToBase64String(formattedEscPos);
    var sha256 = DiskJobQueue.ComputeSha256(formattedEscPos);

    var jobReq = new SubmitJobRequest
    {
        JobId = jobId,
        IdempotencyKey = idempotencyKey,
        Destination = "ESTIMATE_THERMAL",
        DocumentType = "ESTIMATE_RECEIPT",
        SourceNodeId = req.SourceNodeId ?? "TABLET",
        SourceProcess = "AmbicTabletApp",
        Copies = 1,
        PayloadType = PayloadType.EscPos,
        PayloadBase64 = base64,
        Sha256 = sha256
    };

    var result = await engine.ProcessJobSubmissionAsync(jobReq);
    return Results.Ok(result);
});

app.MapGet("/api/v1/nodes", ([FromServices] TopologyRepository topology) =>
{
    return Results.Ok(topology.GetAllNodes());
});

app.MapGet("/api/v1/jobs", ([FromServices] JobRepository jobs) =>
{
    return Results.Ok(jobs.GetRecentJobs(50));
});

app.MapGet("/api/v1/jobs/{jobId}", (string jobId, [FromServices] JobRepository jobs) =>
{
    var job = jobs.GetJob(jobId);
    if (job == null) return Results.NotFound();
    return Results.Ok(job);
});

app.MapPost("/api/v1/admin/bypass", ([FromQuery] bool active, [FromServices] PrintEngineService engine) =>
{
    engine.SetEmergencyBypass(active);
    return Results.Ok(new { emergencyBypassActive = engine.EmergencyBypassActive });
});

app.MapPost("/api/v1/admin/reload-rules", ([FromServices] RulesCacheStore rules) =>
{
    var cfg = rules.LoadHubConfig();
    return Results.Ok(new { success = true, rulesCount = cfg.Rules.Count });
});

app.MapPost("/api/v1/admin/test-print", (string printerName, [FromServices] ILogger<Program> logger) =>
{
    var testText = $"--- AMBIC PRINT SERVER TEST PRINT ---\r\nNode: {Environment.MachineName}\r\nPrinter: {printerName}\r\nTimestamp: {DateTime.Now:yyyy-MM-dd HH:mm:ss}\r\nStatus: SUCCESS\r\n\r\n\r\n";
    var testData = System.Text.Encoding.UTF8.GetBytes(testText);
    var (success, error) = Win32Spooler.SendRawBytes(printerName, testData, "Print Server Diagnostic Test");
    if (success)
    {
        return Results.Ok(new { success = true, printer = printerName });
    }
    return Results.BadRequest(new { success = false, error });
});

app.Run();

public class SubmitEstimateRequest
{
    public string? JobId { get; set; }
    public string? IdempotencyKey { get; set; }
    public string? SourceNodeId { get; set; }
    public Ambic.PrintAdapters.Thermal.EstimateReceipt? Receipt { get; set; }
}

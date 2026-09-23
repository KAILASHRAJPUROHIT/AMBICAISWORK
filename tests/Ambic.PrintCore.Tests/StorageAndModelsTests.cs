using Ambic.Print.Storage.Database;
using Ambic.Print.Storage.Queues;
using Ambic.Print.Storage.Repositories;
using Ambic.PrintCore.Config;
using Ambic.PrintCore.Models;
using Xunit;

namespace Ambic.PrintCore.Tests;

public class StorageAndModelsTests : IDisposable
{
    private readonly string _testDir;
    private readonly NodeDatabase _db;
    private readonly IdempotencyStore _idempotency;
    private readonly JobRepository _jobs;
    private readonly TopologyRepository _topology;

    public StorageAndModelsTests()
    {
        _testDir = Path.Combine(Path.GetTempPath(), "APC_Test_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_testDir);
        var dbPath = Path.Combine(_testDir, "test_node.db");
        _db = new NodeDatabase(dbPath);
        _idempotency = new IdempotencyStore(_db);
        _jobs = new JobRepository(_db);
        _topology = new TopologyRepository(_db);
    }

    [Fact]
    public void Idempotency_PreventsDuplicatePrint()
    {
        var key = "test-idem-key-123";
        var sourceNode = "BILL02";
        var jobId = "APC-20260922-000001";
        var dest = LogicalPrinterId.OfficeA4;

        // First attempt: should succeed (new)
        var (isNew1, existing1) = _idempotency.TryAcquire(key, sourceNode, jobId, dest);
        Assert.True(isNew1);
        Assert.Null(existing1);

        // Second attempt with identical key and source: should be rejected (duplicate)
        var (isNew2, existing2) = _idempotency.TryAcquire(key, sourceNode, "APC-20260922-000002", dest);
        Assert.False(isNew2);
        Assert.NotNull(existing2);
        Assert.Equal(jobId, existing2!.JobId);
        Assert.Equal(key, existing2.Key);
    }

    [Fact]
    public void Topology_SeedsAndResolvesPrinters()
    {
        var nodes = _topology.GetAllNodes();
        Assert.Equal(5, nodes.Count);

        var printers = _topology.GetAllPhysicalPrinters();
        Assert.True(printers.Count >= 5);

        var binding = _topology.GetBinding(LogicalPrinterId.OfficeA4);
        Assert.NotNull(binding);
        Assert.Equal("PRN-P1007", binding!.PhysicalPrinterId);
        Assert.Equal(DefaultTopology.BillingPc1NodeId, binding.PrimaryHostNodeId);
        Assert.Equal(LogicalPrinterId.CustomerA4, binding.FallbackLogicalId);
    }

    [Fact]
    public void JobRepository_PersistsJobAndEvents()
    {
        var job = new PrintJob
        {
            JobId = "APC-TEST-001",
            IdempotencyKey = "key-001",
            DocumentType = "GST Sales Voucher",
            LogicalDestination = LogicalPrinterId.OfficeA4,
            SourceNodeId = "BILL02",
            Copies = 2,
            PayloadType = PayloadType.Raw,
            State = JobState.Received
        };

        _jobs.SaveJob(job);
        _jobs.AddEvent(job.JobId, JobState.Received, "ARADHANA-BILL02", "Job received from Ornate adapter");

        var retrieved = _jobs.GetJob(job.JobId);
        Assert.NotNull(retrieved);
        Assert.Equal(JobState.Received, retrieved!.State);
        Assert.Equal(2, retrieved.Copies);

        // Transition state
        retrieved.State = JobState.Spooled;
        retrieved.StateDetail = "Spooler OK";
        _jobs.SaveJob(retrieved);

        var updated = _jobs.GetJob(job.JobId);
        Assert.Equal(JobState.Spooled, updated!.State);
        Assert.Equal("Spooler OK", updated.StateDetail);
    }

    [Fact]
    public async Task DiskJobQueue_PerformsAtomicTransitions()
    {
        var queue = new DiskJobQueue(Path.Combine(_testDir, "jobs"));
        var payload = "Test Raw Print Content"u8.ToArray();
        var jobId = "APC-DISK-001";

        var pendingPath = await queue.EnqueueAsync(jobId, payload, PayloadType.Raw);
        Assert.True(File.Exists(pendingPath));

        var procPath = queue.MarkProcessing(jobId, PayloadType.Raw);
        Assert.NotNull(procPath);
        Assert.True(File.Exists(procPath!));
        Assert.False(File.Exists(pendingPath));

        queue.MarkCompleted(jobId, PayloadType.Raw);
        Assert.False(File.Exists(procPath));
        var completedPath = Path.Combine(_testDir, "jobs", "completed", $"{jobId}.prn");
        Assert.True(File.Exists(completedPath));
    }

    public void Dispose()
    {
        try { Directory.Delete(_testDir, true); } catch { }
    }
}

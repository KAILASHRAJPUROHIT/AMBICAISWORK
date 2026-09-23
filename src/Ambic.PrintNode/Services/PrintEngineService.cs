using Ambic.Print.Storage.Database;
using Ambic.Print.Storage.Queues;
using Ambic.Print.Storage.Repositories;
using Ambic.PrintCore.Models;
using Ambic.PrintCore.Network;
using Ambic.PrintCore.Routing;
using Ambic.PrintCore.Spooler;

namespace Ambic.PrintNode.Services;

public class PrintEngineService
{
    private readonly ILogger<PrintEngineService> _logger;
    private readonly string _nodeId;
    private readonly NodeDatabase _db;
    private readonly IdempotencyStore _idempotency;
    private readonly JobRepository _jobs;
    private readonly TopologyRepository _topology;
    private readonly DiskJobQueue _queue;
    private readonly RulesCacheStore _rules;
    private readonly NodeClient _nodeClient;
    private bool _emergencyBypassActive;

    public bool EmergencyBypassActive => _emergencyBypassActive;

    public PrintEngineService(
        ILogger<PrintEngineService> logger,
        IConfiguration config,
        NodeDatabase db,
        IdempotencyStore idempotency,
        JobRepository jobs,
        TopologyRepository topology,
        DiskJobQueue queue,
        RulesCacheStore rules,
        NodeClient nodeClient)
    {
        _logger = logger;
        _db = db;
        _idempotency = idempotency;
        _jobs = jobs;
        _topology = topology;
        _queue = queue;
        _rules = rules;
        _nodeClient = nodeClient;
        _nodeId = config["NodeId"] ?? Environment.MachineName;
    }

    public void SetEmergencyBypass(bool active)
    {
        _emergencyBypassActive = active;
        _logger.LogWarning("EMERGENCY BYPASS state changed to {Active}", active);
    }

    public async Task<SubmitJobResponse> ProcessJobSubmissionAsync(SubmitJobRequest req)
    {
        // 1. Check Emergency Bypass
        if (_emergencyBypassActive)
        {
            return new SubmitJobResponse
            {
                JobId = req.JobId,
                State = "BYPASSED",
                Detail = "Emergency Direct Printing is ACTIVE. Managed routing intercepted and bypassed."
            };
        }

        // 2. Validate Idempotency
        var (isNew, existing) = _idempotency.TryAcquire(req.IdempotencyKey, req.SourceNodeId, req.JobId, req.Destination);
        if (!isNew && existing != null)
        {
            _logger.LogInformation("Duplicate job blocked: key={Key}, originalJobId={OrigJobId}", req.IdempotencyKey, existing.JobId);
            return new SubmitJobResponse
            {
                JobId = existing.JobId,
                State = "ALREADY_ACCEPTED",
                Detail = $"Duplicate submission detected. Original job {existing.JobId} was already accepted.",
                IsDuplicate = true
            };
        }

        // 3. Decode & Hash Payload
        byte[] payloadData;
        try
        {
            payloadData = Convert.FromBase64String(req.PayloadBase64);
        }
        catch (Exception ex)
        {
            return new SubmitJobResponse
            {
                JobId = req.JobId,
                State = "REJECTED",
                Detail = $"Failed to decode base64 payload: {ex.Message}"
            };
        }

        var hash = DiskJobQueue.ComputeSha256(payloadData);
        if (!string.IsNullOrEmpty(req.Sha256) && !string.Equals(hash, req.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            return new SubmitJobResponse
            {
                JobId = req.JobId,
                State = "REJECTED",
                Detail = $"SHA-256 checksum mismatch (expected {req.Sha256}, computed {hash})"
            };
        }

        // 4. Save to Disk Queue & DB
        var savedPath = await _queue.EnqueueAsync(req.JobId, payloadData, req.PayloadType);

        var job = new PrintJob
        {
            JobId = req.JobId,
            IdempotencyKey = req.IdempotencyKey,
            DocumentType = req.DocumentType,
            LogicalDestination = req.Destination,
            SourceNodeId = req.SourceNodeId,
            SourceProcess = req.SourceProcess,
            SourceUser = req.SourceUser,
            Copies = req.Copies,
            PayloadType = req.PayloadType,
            PayloadFilePath = savedPath,
            Sha256Hash = hash,
            State = JobState.Received,
            CreatedAtUtc = DateTime.UtcNow,
            UpdatedAtUtc = DateTime.UtcNow
        };
        _jobs.SaveJob(job);
        _jobs.AddEvent(job.JobId, JobState.Received, _nodeId, "Job accepted into node queue");

        // 5. Evaluate Routing
        var ruleset = _rules.Load();
        var routingEngine = new RoutingEngine(
            ruleset,
            _nodeId,
            id => _topology.GetBinding(id),
            id => _topology.GetAllPhysicalPrinters().FirstOrDefault(p => p.PrinterId == id),
            id => _topology.GetAllNodes().FirstOrDefault(n => n.NodeId == id)
        );

        var decision = routingEngine.ResolveDestination(
            req.Destination,
            null,
            false,
            new RouteDecision { RuleVersion = ruleset.Version },
            $"Job submitted directly to logical destination {req.Destination}"
        );

        job.MatchedRuleId = decision.MatchedRuleId;
        job.RuleVersion = decision.RuleVersion;
        job.TargetPhysicalPrinterId = decision.PhysicalPrinterId;

        if (decision.IsHold)
        {
            job.State = JobState.Held;
            job.StateDetail = decision.DecisionDetail;
            _jobs.SaveJob(job);
            _jobs.AddEvent(job.JobId, JobState.Held, _nodeId, decision.DecisionDetail);
            _queue.MarkHeld(job.JobId, job.PayloadType);

            return new SubmitJobResponse
            {
                JobId = job.JobId,
                State = "HELD",
                Detail = decision.DecisionDetail
            };
        }

        // 6. Execute: Local Spool or Remote Forward
        if (decision.IsLocalSpool)
        {
            return ExecuteLocalSpool(job, decision.WindowsQueueName ?? "", payloadData);
        }
        else
        {
            return await ExecuteRemoteForwardAsync(job, decision, req);
        }
    }

    private SubmitJobResponse ExecuteLocalSpool(PrintJob job, string windowsQueueName, byte[] payloadData)
    {
        _logger.LogInformation("Spooling locally to queue '{Queue}' for job {JobId}", windowsQueueName, job.JobId);
        job.State = JobState.Spooled;
        _queue.MarkProcessing(job.JobId, job.PayloadType);

        var (success, error) = Win32Spooler.SendRawBytes(windowsQueueName, payloadData, $"APC-{job.JobId}");
        if (success)
        {
            job.State = JobState.Completed;
            job.StateDetail = $"Successfully spooled to local queue {windowsQueueName}";
            _jobs.SaveJob(job);
            _jobs.AddEvent(job.JobId, JobState.Completed, _nodeId, job.StateDetail);
            _queue.MarkCompleted(job.JobId, job.PayloadType);

            return new SubmitJobResponse
            {
                JobId = job.JobId,
                State = "COMPLETED",
                Detail = job.StateDetail
            };
        }
        else
        {
            job.State = JobState.Failed;
            job.StateDetail = error ?? "Win32 spooler write failed";
            _jobs.SaveJob(job);
            _jobs.AddEvent(job.JobId, JobState.Failed, _nodeId, job.StateDetail);
            _queue.MarkFailed(job.JobId, job.PayloadType);

            return new SubmitJobResponse
            {
                JobId = job.JobId,
                State = "FAILED",
                Detail = job.StateDetail
            };
        }
    }

    private async Task<SubmitJobResponse> ExecuteRemoteForwardAsync(PrintJob job, RouteDecision decision, SubmitJobRequest originalReq)
    {
        _logger.LogInformation("Forwarding job {JobId} to remote host {HostNode} ({Ip})", job.JobId, decision.TargetHostNodeId, decision.TargetHostIp);
        job.State = JobState.Transferred;
        job.StateDetail = $"Transferring to remote host {decision.TargetHostNodeId} ({decision.TargetHostIp})";
        _jobs.SaveJob(job);
        _jobs.AddEvent(job.JobId, JobState.Transferred, _nodeId, job.StateDetail);

        if (string.IsNullOrEmpty(decision.TargetHostIp))
        {
            job.State = JobState.Failed;
            job.StateDetail = $"Remote host {decision.TargetHostNodeId} has no resolved IP address";
            _jobs.SaveJob(job);
            _jobs.AddEvent(job.JobId, JobState.Failed, _nodeId, job.StateDetail);
            _queue.MarkFailed(job.JobId, job.PayloadType);

            return new SubmitJobResponse { JobId = job.JobId, State = "FAILED", Detail = job.StateDetail };
        }

        try
        {
            var res = await _nodeClient.SubmitJobAsync(decision.TargetHostIp, 8447, originalReq);
            if (res != null && (res.State == "COMPLETED" || res.State == "ACCEPTED" || res.State == "ALREADY_ACCEPTED"))
            {
                job.State = JobState.Completed;
                job.StateDetail = $"Accepted by remote host {decision.TargetHostNodeId}: {res.Detail}";
                _jobs.SaveJob(job);
                _jobs.AddEvent(job.JobId, JobState.Completed, _nodeId, job.StateDetail);
                _queue.MarkCompleted(job.JobId, job.PayloadType);

                return res;
            }
            else
            {
                job.State = JobState.Failed;
                job.StateDetail = res?.Detail ?? "Remote host returned empty response";
                _jobs.SaveJob(job);
                _jobs.AddEvent(job.JobId, JobState.Failed, _nodeId, job.StateDetail);
                _queue.MarkFailed(job.JobId, job.PayloadType);

                return new SubmitJobResponse { JobId = job.JobId, State = "FAILED", Detail = job.StateDetail };
            }
        }
        catch (Exception ex)
        {
            job.State = JobState.Failed;
            job.StateDetail = $"Network transfer failed to {decision.TargetHostIp}: {ex.Message}";
            _jobs.SaveJob(job);
            _jobs.AddEvent(job.JobId, JobState.Failed, _nodeId, job.StateDetail);
            _queue.MarkFailed(job.JobId, job.PayloadType);

            return new SubmitJobResponse { JobId = job.JobId, State = "FAILED", Detail = job.StateDetail };
        }
    }
}

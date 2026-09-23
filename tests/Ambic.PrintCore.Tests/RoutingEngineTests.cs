using Ambic.Print.Storage.Database;
using Ambic.Print.Storage.Repositories;
using Ambic.PrintCore.Config;
using Ambic.PrintCore.Models;
using Ambic.PrintCore.Routing;
using Xunit;

namespace Ambic.PrintCore.Tests;

public class RoutingEngineTests : IDisposable
{
    private readonly string _testDir;
    private readonly NodeDatabase _db;
    private readonly TopologyRepository _topology;
    private readonly RoutingEngine _engine;

    public RoutingEngineTests()
    {
        _testDir = Path.Combine(Path.GetTempPath(), "APC_RouteTest_" + Guid.NewGuid().ToString("N"));
        _db = new NodeDatabase(Path.Combine(_testDir, "node.db"));
        _topology = new TopologyRepository(_db);

        var ruleset = DefaultTopology.CreateDefaultRuleset();
        var localNodeId = DefaultTopology.BillingPc2NodeId; // Assume we are running on Billing PC2

        _engine = new RoutingEngine(
            ruleset,
            localNodeId,
            bindingLookup: id => _topology.GetBinding(id),
            physicalPrinterLookup: id => _topology.GetAllPhysicalPrinters().FirstOrDefault(p => p.PrinterId == id),
            nodeLookup: id => _topology.GetAllNodes().FirstOrDefault(n => n.NodeId == id)
        );
    }

    [Fact]
    public void OrnateGstVoucher_Copy1_RoutesToOfficeP1007OnBillingPc1()
    {
        var decision = _engine.Evaluate(
            process: "ONX.exe",
            screen: "Voucher Print",
            voucher: "GST Sales Voucher",
            copies: 2,
            copyNumber: 1
        );

        Assert.True(decision.IsMatched);
        Assert.False(decision.IsHold);
        Assert.Equal(LogicalPrinterId.OfficeA4, decision.LogicalDestination);
        Assert.Equal("PRN-P1007", decision.PhysicalPrinterId);
        Assert.Equal(DefaultTopology.BillingPc1NodeId, decision.TargetHostNodeId);
        Assert.False(decision.IsLocalSpool); // Billing PC2 routes remotely to Billing PC1
        Assert.Equal("192.168.0.13", decision.TargetHostIp);
    }

    [Fact]
    public void OrnateGstVoucher_Copy2_RoutesToCustomerHp355WithDuplexLetterhead()
    {
        var decision = _engine.Evaluate(
            process: "ONX.exe",
            screen: "Voucher Print",
            voucher: "GST Sales Voucher",
            copies: 2,
            copyNumber: 2
        );

        Assert.True(decision.IsMatched);
        Assert.False(decision.IsHold);
        Assert.Equal(LogicalPrinterId.CustomerA4, decision.LogicalDestination);
        Assert.Equal("PRN-HP355", decision.PhysicalPrinterId);
        Assert.Equal("CUSTOMER_LETTERHEAD_DUPLEX", decision.Transform);
        Assert.True(decision.Duplex);
    }

    [Fact]
    public void OrnateGstVoucher_CopyCountMismatch_BlocksP1007AndDiverts()
    {
        // When copy count is 1 (instead of expected 2):
        var decision = _engine.Evaluate(
            process: "ONX.exe",
            screen: "Voucher Print",
            voucher: "GST Sales Voucher",
            copies: 1, // Mismatch!
            copyNumber: 1
        );

        // Safety invariant: P1007 is NEVER routed on copy count mismatch!
        Assert.NotEqual(LogicalPrinterId.OfficeA4, decision.LogicalDestination);
        Assert.Equal(LogicalPrinterId.CustomerA4, decision.LogicalDestination); // Diverted to safe customer fallback
        Assert.Contains("Safety rule diverted", decision.DecisionDetail);
    }

    [Fact]
    public void UnknownVoucherOrScreen_HoldsJobWithoutPrinting()
    {
        var decision = _engine.Evaluate(
            process: "ONX.exe",
            screen: "Random Other Screen",
            voucher: "Estimate Memo",
            copies: 1,
            copyNumber: 1
        );

        Assert.False(decision.IsMatched);
        Assert.True(decision.IsHold);
        Assert.NotEqual(LogicalPrinterId.OfficeA4, decision.LogicalDestination);
    }

    [Fact]
    public void TabletEstimate_RoutesToEstimateThermalOnGoldPc()
    {
        var decision = _engine.Evaluate(
            process: "TabletApi",
            screen: null,
            voucher: null,
            copies: 1,
            copyNumber: 1,
            documentType: "ESTIMATE"
        );

        Assert.True(decision.IsMatched);
        Assert.False(decision.IsHold);
        Assert.Equal(LogicalPrinterId.EstimateThermal, decision.LogicalDestination);
        Assert.Equal("PRN-THERMAL", decision.PhysicalPrinterId);
        Assert.Equal(DefaultTopology.GoldPcNodeId, decision.TargetHostNodeId);
        Assert.Equal("192.168.0.15", decision.TargetHostIp);
    }

    public void Dispose()
    {
        try { Directory.Delete(_testDir, true); } catch { }
    }
}

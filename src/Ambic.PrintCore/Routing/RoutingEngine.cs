using Ambic.PrintCore.Models;
using Ambic.PrintCore.Config;

namespace Ambic.PrintCore.Routing;

public class RouteDecision
{
    public bool IsMatched { get; set; }
    public string? MatchedRuleId { get; set; }
    public string? RuleVersion { get; set; }
    public string LogicalDestination { get; set; } = string.Empty;
    public string PhysicalPrinterId { get; set; } = string.Empty;
    public string TargetHostNodeId { get; set; } = string.Empty;
    public string? TargetHostIp { get; set; }
    public string? WindowsQueueName { get; set; }
    public string? Transform { get; set; }
    public bool Duplex { get; set; }
    public bool IsLocalSpool { get; set; }
    public bool IsHold { get; set; }
    public string DecisionDetail { get; set; } = string.Empty;
}

public class RoutingEngine
{
    private readonly RulesetConfig _ruleset;
    private readonly string _localNodeId;
    private readonly Func<string, PrinterBinding?> _bindingLookup;
    private readonly Func<string, PhysicalPrinter?> _physicalPrinterLookup;
    private readonly Func<string, NodeInfo?> _nodeLookup;

    public RoutingEngine(
        RulesetConfig ruleset,
        string localNodeId,
        Func<string, PrinterBinding?> bindingLookup,
        Func<string, PhysicalPrinter?> physicalPrinterLookup,
        Func<string, NodeInfo?> nodeLookup)
    {
        _ruleset = ruleset;
        _localNodeId = localNodeId;
        _bindingLookup = bindingLookup;
        _physicalPrinterLookup = physicalPrinterLookup;
        _nodeLookup = nodeLookup;
    }

    public RouteDecision Evaluate(
        string process,
        string? screen,
        string? voucher,
        int? copies,
        int copyNumber,
        string? documentType = null)
    {
        var decision = new RouteDecision
        {
            RuleVersion = _ruleset.Version
        };

        RoutingRule? matchedRule = null;
        foreach (var rule in _ruleset.Rules.Where(r => r.Enabled))
        {
            if (!IsRuleMatch(rule, process, screen, voucher, copies, documentType))
                continue;

            matchedRule = rule;
            break;
        }

        if (matchedRule == null)
        {
            decision.IsHold = true;
            decision.DecisionDetail = $"No rule matched process={process}, screen={screen}, voucher={voucher}, copies={copies}, docType={documentType}";
            return decision;
        }

        decision.MatchedRuleId = matchedRule.Id;

        // Apply Hub Master Enable check
        if (_ruleset.HubSettings != null && !_ruleset.HubSettings.MasterEnabled)
        {
            decision.IsHold = true;
            decision.DecisionDetail = $"Master AutoPrint & smart routing is DISABLED in Hub settings. Job held.";
            return decision;
        }

        // Safety Invariant: Ornate 2-copy GST Sales Voucher MUST have copies == 2
        var expectedCopies = matchedRule.RequiredCopies > 0 ? matchedRule.RequiredCopies : matchedRule.Source.Copies;
        if (expectedCopies.HasValue && expectedCopies.Value > 0 && copies.HasValue && expectedCopies.Value != copies.Value)
        {
            var fallback = !string.IsNullOrEmpty(matchedRule.SafeFallbackDestination) ? matchedRule.SafeFallbackDestination : LogicalPrinterId.CustomerA4;
            if (matchedRule.OnMismatch == "P355_ONLY" || matchedRule.OnUncertain == UncertainRouteAction.SafeFallbackOrHold)
            {
                return ResolveDestination(fallback, null, false, decision,
                    $"Copies mismatch (expected {expectedCopies}, got {copies}). Safety rule diverted to safe fallback {fallback}.");
            }

            decision.IsHold = true;
            decision.DecisionDetail = $"Copies mismatch (expected {expectedCopies}, got {copies}). Safety rule HELD job.";
            return decision;
        }

        // Apply Hub Both Mode or Force Overrides
        if (_ruleset.HubSettings != null)
        {
            if (copyNumber == 1 && !string.IsNullOrWhiteSpace(_ruleset.HubSettings.ForceCopy1Printer))
            {
                return ResolveDestination(_ruleset.HubSettings.ForceCopy1Printer, null, false, decision,
                    $"Manual override: Force Copy 1 -> {_ruleset.HubSettings.ForceCopy1Printer}");
            }
            if (copyNumber >= 2 && !string.IsNullOrWhiteSpace(_ruleset.HubSettings.ForceCopy2Printer))
            {
                return ResolveDestination(_ruleset.HubSettings.ForceCopy2Printer, null, false, decision,
                    $"Manual override: Force Copy 2 -> {_ruleset.HubSettings.ForceCopy2Printer}");
            }

            if (_ruleset.HubSettings.BothMode.StartsWith("BOTH_P1007", StringComparison.OrdinalIgnoreCase) ||
                _ruleset.HubSettings.BothMode.StartsWith("Both copies -> Laser Printer P1007", StringComparison.OrdinalIgnoreCase) ||
                _ruleset.HubSettings.BothMode.Equals("Both copies -> P1007", StringComparison.OrdinalIgnoreCase))
            {
                return ResolveDestination(LogicalPrinterId.OfficeA4, null, false, decision,
                    $"Both copies mode override -> Office A4 (P1007)");
            }
            if (_ruleset.HubSettings.BothMode.StartsWith("BOTH_P355", StringComparison.OrdinalIgnoreCase) ||
                _ruleset.HubSettings.BothMode.StartsWith("Both copies -> Customer HP 355", StringComparison.OrdinalIgnoreCase) ||
                _ruleset.HubSettings.BothMode.Equals("Both copies -> 355", StringComparison.OrdinalIgnoreCase))
            {
                return ResolveDestination(LogicalPrinterId.CustomerA4, null, true, decision,
                    $"Both copies mode override -> Customer A4 (HP 355)");
            }
        }

        // Check if rule specifies custom printers
        if (copyNumber == 1 && !string.IsNullOrEmpty(matchedRule.Copy1Printer) && matchedRule.Copy1Printer != "(use configured default)")
        {
            return ResolveDestination(matchedRule.Copy1Printer, null, false, decision,
                $"Matched rule {matchedRule.Id} custom Copy 1 -> {matchedRule.Copy1Printer}");
        }
        if (copyNumber >= 2 && !string.IsNullOrEmpty(matchedRule.LaterPrinter) && matchedRule.LaterPrinter != "(use configured default)")
        {
            var transform = matchedRule.LetterheadOverlay == "DUPLEX_FRONT_BACK" ? "CUSTOMER_LETTERHEAD_DUPLEX" : null;
            return ResolveDestination(matchedRule.LaterPrinter, transform, matchedRule.Duplex, decision,
                $"Matched rule {matchedRule.Id} custom Copy {copyNumber} -> {matchedRule.LaterPrinter}");
        }

        // Find action for this copy number
        var action = matchedRule.Actions.FirstOrDefault(a => a.CopyNumber == copyNumber);
        if (action == null)
        {
            // If copy count > actions, default to last action or safe fallback
            action = matchedRule.Actions.LastOrDefault();
            if (action == null)
            {
                decision.IsHold = true;
                decision.DecisionDetail = $"Rule {matchedRule.Id} has no action configured for copy #{copyNumber}.";
                return decision;
            }
        }

        return ResolveDestination(action.Destination, action.Transform, action.Duplex, decision,
            $"Matched rule {matchedRule.Id} action for copy #{copyNumber} -> {action.Destination}");
    }

    public RouteDecision ResolveDestination(
        string logicalDestination,
        string? transform,
        bool duplex,
        RouteDecision decision,
        string rationale)
    {
        decision.IsMatched = true;
        decision.LogicalDestination = logicalDestination;
        decision.Transform = transform;
        decision.Duplex = duplex;
        decision.DecisionDetail = rationale;

        // Lookup binding
        var binding = _bindingLookup(logicalDestination);
        if (binding == null)
        {
            // If destination is already a physical printer ID or direct name
            var directPhysical = _physicalPrinterLookup(logicalDestination);
            if (directPhysical != null)
            {
                decision.PhysicalPrinterId = directPhysical.PrinterId;
                decision.TargetHostNodeId = directPhysical.HostNodeId;
                decision.WindowsQueueName = directPhysical.WindowsQueueName;
                decision.IsLocalSpool = string.IsNullOrWhiteSpace(directPhysical.HostNodeId) ||
                                       string.Equals(directPhysical.HostNodeId, _localNodeId, StringComparison.OrdinalIgnoreCase);
                return decision;
            }

            decision.IsHold = true;
            decision.DecisionDetail += $" | Logical destination '{logicalDestination}' has no binding. Job HELD.";
            return decision;
        }

        var physicalPrinter = _physicalPrinterLookup(binding.PhysicalPrinterId);
        if (physicalPrinter == null)
        {
            decision.IsHold = true;
            decision.DecisionDetail += $" | Physical printer '{binding.PhysicalPrinterId}' not found in registry. Job HELD.";
            return decision;
        }

        decision.PhysicalPrinterId = physicalPrinter.PrinterId;
        decision.TargetHostNodeId = string.IsNullOrWhiteSpace(binding.PrimaryHostNodeId) ? physicalPrinter.HostNodeId : binding.PrimaryHostNodeId;
        decision.WindowsQueueName = physicalPrinter.WindowsQueueName;

        // Check if destination is local or remote
        if (string.IsNullOrWhiteSpace(decision.TargetHostNodeId) ||
            string.Equals(decision.TargetHostNodeId, _localNodeId, StringComparison.OrdinalIgnoreCase))
        {
            decision.IsLocalSpool = true;
        }
        else
        {
            var targetNode = _nodeLookup(decision.TargetHostNodeId);
            decision.TargetHostIp = targetNode?.HostIp ?? physicalPrinter.HostIp;
            decision.IsLocalSpool = false;
        }

        return decision;
    }

    public static RoutingRule? FindMatchingRule(IEnumerable<RoutingRule> rules, string process, string? screen, int? copies, string? voucher = null, string? docType = null)
    {
        return rules.Where(r => r.Enabled).FirstOrDefault(r => IsRuleMatch(r, process, screen, voucher, copies, docType));
    }

    public static bool IsRuleMatch(RoutingRule rule, string process, string? screen, string? voucher, int? copies, string? docType)
    {
        // 1. Process matching
        var targetProgram = !string.IsNullOrEmpty(rule.TargetProgram) ? rule.TargetProgram : rule.Source.Process;
        if (!string.IsNullOrEmpty(targetProgram) && targetProgram != "*")
        {
            var pName = Path.GetFileName(process);
            var tName = Path.GetFileName(targetProgram);
            if (!string.Equals(pName, tName, StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(pName.Replace(".exe", "", StringComparison.OrdinalIgnoreCase), tName.Replace(".exe", "", StringComparison.OrdinalIgnoreCase), StringComparison.OrdinalIgnoreCase))
                return false;
        }

        // 2. Window title / Screen matching
        var screenPattern = !string.IsNullOrEmpty(rule.WindowTitleMatch) ? rule.WindowTitleMatch : rule.Source.Screen;
        if (!string.IsNullOrEmpty(screenPattern) && screenPattern != "*")
        {
            if (string.IsNullOrEmpty(screen) || !screen.Contains(screenPattern, StringComparison.OrdinalIgnoreCase))
                return false;
        }

        // 3. Voucher match
        if (!string.IsNullOrEmpty(rule.Source.Voucher) && rule.Source.Voucher != "*")
        {
            if (string.IsNullOrEmpty(voucher) || !voucher.Contains(rule.Source.Voucher, StringComparison.OrdinalIgnoreCase))
                return false;
        }

        // 4. Copies matching
        var reqCopies = rule.RequiredCopies > 0 ? rule.RequiredCopies : rule.Source.Copies;
        if (string.IsNullOrEmpty(rule.OnMismatch) && rule.OnUncertain != UncertainRouteAction.SafeFallbackOrHold)
        {
            if (reqCopies.HasValue && reqCopies.Value > 0 && copies.HasValue && copies.Value > 0)
            {
                if (reqCopies.Value != copies.Value)
                    return false;
            }
        }

        // 5. Document type
        if (!string.IsNullOrEmpty(rule.Source.DocumentType) && rule.Source.DocumentType != "*")
        {
            if (!string.Equals(rule.Source.DocumentType, docType, StringComparison.OrdinalIgnoreCase))
                return false;
        }

        return true;
    }
}

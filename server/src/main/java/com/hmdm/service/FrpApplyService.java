package com.hmdm.service;

import com.hmdm.persistence.AgentCommandDAO;
import com.hmdm.persistence.FrpRecoveryAccountDAO;
import com.hmdm.persistence.domain.AgentCommand;
import com.hmdm.persistence.domain.FrpRecoveryAccount;
import org.json.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import javax.inject.Singleton;
import java.util.List;

/**
 * Builds the one and only shape of FRP-enable command this fleet ever sends: an explicit,
 * ID-bearing {@code policy.apply} carrying the tenant's currently-connected, OAuth-verified
 * recovery accounts. Shared by the manual "Apply verified FRP accounts" button
 * ({@link com.hmdm.rest.resource.FrpRecoveryAccountResource}) and automatic queueing at
 * Device-Owner enrollment ({@link com.hmdm.rest.resource.AgentResource}) so both paths stay
 * byte-for-byte identical - there is no second, looser code path that could regress into the
 * old unverified-account behaviour.
 */
@Singleton
public class FrpApplyService {
    private static final Logger logger = LoggerFactory.getLogger(FrpApplyService.class);

    private final FrpRecoveryAccountDAO accounts;
    private final AgentCommandDAO commands;

    @Inject
    public FrpApplyService(FrpRecoveryAccountDAO accounts, AgentCommandDAO commands) {
        this.accounts = accounts;
        this.commands = commands;
    }

    /**
     * Queues an FRP-enable command for this device using the tenant's connected recovery
     * accounts. Silently does nothing when none are connected yet - this must never invent or
     * fall back to an unverified identity, so "no accounts" means "no command", not "some
     * default command".
     *
     * @return the queued command, or {@code null} if no recovery accounts are connected for this tenant.
     */
    public AgentCommand queueIfAccountsConnected(int customerId, String deviceNumber) {
        List<FrpRecoveryAccount> configured = accounts.list(customerId);
        if (configured.isEmpty()) {
            return null;
        }
        org.json.JSONArray ids = new org.json.JSONArray();
        for (FrpRecoveryAccount account : configured) ids.put(account.getGoogleUserId());
        AgentCommand command = new AgentCommand();
        command.setDeviceNumber(deviceNumber);
        command.setType("policy.apply");
        command.setPayload(new JSONObject().put("policy", "factoryResetProtection").put("value", true)
                .put("recoveryAccountIds", ids).toString());
        command.setRequiresCapability("policy.factoryResetProtection");
        command.setStatus("pending");
        command.setCreatedAt(System.currentTimeMillis());
        commands.insert(command);
        logger.info("FRP auto-queued for device {} ({} recovery account(s))", deviceNumber, configured.size());
        return command;
    }
}

package com.hmdm.persistence;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.FrpOAuthState;
import com.hmdm.persistence.domain.FrpRecoveryAccount;
import com.hmdm.persistence.mapper.FrpRecoveryAccountMapper;

import java.util.List;

@Singleton
public class FrpRecoveryAccountDAO {
    private final FrpRecoveryAccountMapper mapper;

    @Inject
    public FrpRecoveryAccountDAO(FrpRecoveryAccountMapper mapper) { this.mapper = mapper; }

    public List<FrpRecoveryAccount> list(int customerId) { return mapper.list(customerId); }
    public void upsert(FrpRecoveryAccount account) { mapper.upsert(account); }
    public boolean delete(int id, int customerId) { return mapper.delete(id, customerId) == 1; }
    public void insertState(FrpOAuthState state) { mapper.insertState(state); }
    public FrpOAuthState findState(String stateHash) { return mapper.findState(stateHash); }
    public boolean consumeState(int id) { return mapper.consumeState(id, System.currentTimeMillis()) == 1; }
}

package com.hmdm.persistence;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.LeaderboardSnapshot;
import com.hmdm.persistence.mapper.LeaderboardMapper;

@Singleton
public class LeaderboardDAO {
    private final LeaderboardMapper mapper;

    @Inject
    public LeaderboardDAO(LeaderboardMapper mapper) { this.mapper = mapper; }

    public void upsert(LeaderboardSnapshot snapshot) { mapper.upsert(snapshot); }
    public LeaderboardSnapshot find(int customerId) { return mapper.find(customerId); }
}

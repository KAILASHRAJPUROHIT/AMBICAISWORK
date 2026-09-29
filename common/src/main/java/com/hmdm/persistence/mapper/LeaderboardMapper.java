package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.LeaderboardSnapshot;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

public interface LeaderboardMapper {
    @Insert("INSERT INTO leaderboardSnapshot (customerId, businessDate, generatedAt, payload, receivedAt) " +
            "VALUES (#{customerId}, #{businessDate}, #{generatedAt}, #{payload}, #{receivedAt}) " +
            "ON CONFLICT (customerId) DO UPDATE SET businessDate = EXCLUDED.businessDate, " +
            "generatedAt = EXCLUDED.generatedAt, payload = EXCLUDED.payload, receivedAt = EXCLUDED.receivedAt")
    void upsert(LeaderboardSnapshot snapshot);

    @Select("SELECT * FROM leaderboardSnapshot WHERE customerId = #{customerId}")
    LeaderboardSnapshot find(@Param("customerId") int customerId);
}

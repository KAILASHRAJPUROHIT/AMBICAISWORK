package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.FrpOAuthState;
import com.hmdm.persistence.domain.FrpRecoveryAccount;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.SelectKey;
import org.apache.ibatis.annotations.Update;

import java.util.List;

public interface FrpRecoveryAccountMapper {
    @Select("SELECT * FROM frpRecoveryAccount WHERE customerId = #{customerId} ORDER BY email")
    List<FrpRecoveryAccount> list(@Param("customerId") int customerId);

    @Insert("INSERT INTO frpRecoveryAccount (customerId, googleUserId, email, connectedByUserId, connectedAt) " +
            "VALUES (#{customerId}, #{googleUserId}, #{email}, #{connectedByUserId}, #{connectedAt}) " +
            "ON CONFLICT (customerId, googleUserId) DO UPDATE SET email = EXCLUDED.email, " +
            "connectedByUserId = EXCLUDED.connectedByUserId, connectedAt = EXCLUDED.connectedAt")
    void upsert(FrpRecoveryAccount account);

    @Delete("DELETE FROM frpRecoveryAccount WHERE id = #{id} AND customerId = #{customerId}")
    int delete(@Param("id") int id, @Param("customerId") int customerId);

    @Insert("INSERT INTO frpOAuthState (stateHash, customerId, userId, expiresAt) " +
            "VALUES (#{stateHash}, #{customerId}, #{userId}, #{expiresAt})")
    @SelectKey(statement = "SELECT currval('frpoauthstate_id_seq')", keyColumn = "id", keyProperty = "id",
            before = false, resultType = int.class)
    void insertState(FrpOAuthState state);

    @Select("SELECT * FROM frpOAuthState WHERE stateHash = #{stateHash}")
    FrpOAuthState findState(@Param("stateHash") String stateHash);

    @Update("UPDATE frpOAuthState SET consumedAt = #{now} WHERE id = #{id} AND consumedAt IS NULL AND expiresAt > #{now}")
    int consumeState(@Param("id") int id, @Param("now") long now);
}

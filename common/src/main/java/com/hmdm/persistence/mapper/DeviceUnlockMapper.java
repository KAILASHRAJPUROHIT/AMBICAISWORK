package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.DeviceUnlockOtp;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

public interface DeviceUnlockMapper {
    @Insert("INSERT INTO deviceUnlockOtp (deviceNumber, salt, codeHash, createdAt, expiresAt, attempts) " +
            "VALUES (#{deviceNumber}, #{salt}, #{codeHash}, #{createdAt}, #{expiresAt}, 0)")
    void insert(DeviceUnlockOtp otp);

    @Select("SELECT * FROM deviceUnlockOtp WHERE deviceNumber = #{device} AND usedAt IS NULL AND expiresAt > #{now} " +
            "ORDER BY createdAt DESC LIMIT 1")
    DeviceUnlockOtp latestOpen(@Param("device") String deviceNumber, @Param("now") long now);

    @Update("UPDATE deviceUnlockOtp SET attempts = attempts + 1 WHERE id = #{id}")
    void bumpAttempts(@Param("id") int id);

    /** Atomic: only the first caller can use a code. */
    @Update("UPDATE deviceUnlockOtp SET usedAt = #{now} WHERE id = #{id} AND usedAt IS NULL")
    int markUsed(@Param("id") int id, @Param("now") long now);

    @Select("SELECT COUNT(*) FROM deviceUnlockOtp WHERE deviceNumber = #{device} AND createdAt > #{since}")
    int countSince(@Param("device") String deviceNumber, @Param("since") long since);

    @Delete("DELETE FROM deviceUnlockOtp WHERE expiresAt < #{before}")
    void purge(@Param("before") long before);
}

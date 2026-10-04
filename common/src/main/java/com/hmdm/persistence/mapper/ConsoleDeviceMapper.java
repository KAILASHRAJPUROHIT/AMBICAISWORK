package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.ConsoleLoginOtp;
import com.hmdm.persistence.domain.ConsoleTrustedDevice;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

public interface ConsoleDeviceMapper {
    @Select("SELECT * FROM consoleTrustedDevice WHERE userId = #{userId} AND fingerprintHash = #{fp}")
    ConsoleTrustedDevice findTrusted(@Param("userId") int userId, @Param("fp") String fingerprintHash);

    @Select("SELECT * FROM consoleTrustedDevice WHERE userId = #{userId} ORDER BY lastSeenAt DESC")
    List<ConsoleTrustedDevice> listTrusted(@Param("userId") int userId);

    @Insert("INSERT INTO consoleTrustedDevice (userId, fingerprintHash, label, userAgent, ipAddress, createdAt, lastSeenAt) " +
            "VALUES (#{userId}, #{fingerprintHash}, #{label}, #{userAgent}, #{ipAddress}, #{createdAt}, #{lastSeenAt}) " +
            "ON CONFLICT (userId, fingerprintHash) DO UPDATE SET lastSeenAt = EXCLUDED.lastSeenAt")
    void upsertTrusted(ConsoleTrustedDevice device);

    @Update("UPDATE consoleTrustedDevice SET lastSeenAt = #{now} WHERE id = #{id}")
    void touchTrusted(@Param("id") int id, @Param("now") long now);

    @Delete("DELETE FROM consoleTrustedDevice WHERE id = #{id} AND userId = #{userId}")
    int deleteTrusted(@Param("id") int id, @Param("userId") int userId);

    @Insert("INSERT INTO consoleLoginOtp (userId, fingerprintHash, salt, codeHash, createdAt, expiresAt, attempts) " +
            "VALUES (#{userId}, #{fingerprintHash}, #{salt}, #{codeHash}, #{createdAt}, #{expiresAt}, 0)")
    void insertOtp(ConsoleLoginOtp otp);

    /** The newest code for this user and device that is neither used nor expired. */
    @Select("SELECT * FROM consoleLoginOtp WHERE userId = #{userId} AND fingerprintHash = #{fp} " +
            "AND usedAt IS NULL AND expiresAt > #{now} ORDER BY createdAt DESC LIMIT 1")
    ConsoleLoginOtp latestOpenOtp(@Param("userId") int userId, @Param("fp") String fingerprintHash, @Param("now") long now);

    @Update("UPDATE consoleLoginOtp SET attempts = attempts + 1 WHERE id = #{id}")
    void bumpAttempts(@Param("id") int id);

    /** Atomic: only the first caller can use a code. */
    @Update("UPDATE consoleLoginOtp SET usedAt = #{now} WHERE id = #{id} AND usedAt IS NULL")
    int markUsed(@Param("id") int id, @Param("now") long now);

    @Select("SELECT COUNT(*) FROM consoleLoginOtp WHERE userId = #{userId} AND createdAt > #{since}")
    int countOtpSince(@Param("userId") int userId, @Param("since") long since);

    @Delete("DELETE FROM consoleLoginOtp WHERE expiresAt < #{before}")
    void purgeOtp(@Param("before") long before);
}

package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.SilentCandidate;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

public interface DeviceSilentMapper {
    /** Enrolled devices whose last check-in is older than {@code cutoff} (epoch millis). */
    @Select("SELECT number AS deviceNumber, customerId, lastUpdate FROM devices " +
            "WHERE agentSecretHash IS NOT NULL AND lastUpdate IS NOT NULL AND lastUpdate > 0 AND lastUpdate < #{cutoff}")
    List<SilentCandidate> listStale(@Param("cutoff") long cutoff);

    /** Devices already flagged silent that have checked in again since {@code cutoff}. */
    @Select("SELECT d.number AS deviceNumber, d.customerId AS customerId, d.lastUpdate AS lastUpdate " +
            "FROM devices d JOIN deviceSilentState s ON s.deviceNumber = d.number WHERE d.lastUpdate >= #{cutoff}")
    List<SilentCandidate> listRecovered(@Param("cutoff") long cutoff);

    @Select("SELECT deviceNumber FROM deviceSilentState")
    List<String> listSilentNumbers();

    @Insert("INSERT INTO deviceSilentState (deviceNumber, silentSince) VALUES (#{deviceNumber}, #{since}) " +
            "ON CONFLICT (deviceNumber) DO NOTHING")
    void markSilent(@Param("deviceNumber") String deviceNumber, @Param("since") long since);

    @Delete("DELETE FROM deviceSilentState WHERE deviceNumber = #{deviceNumber}")
    void clearSilent(@Param("deviceNumber") String deviceNumber);

    /** Retention for the location breadcrumb trail. */
    @Delete("DELETE FROM device_location WHERE capturedAt < #{before}")
    int deleteLocationsOlderThan(@Param("before") long before);
}

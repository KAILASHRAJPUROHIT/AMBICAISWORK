package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.Geofence;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

/** CRUD + evaluation lookup for {@code geofence}, matching {@link AlertRuleMapper}'s shape. */
public interface GeofenceMapper {

    @Insert({"INSERT INTO geofence (customerId, name, centerLat, centerLon, radiusMeters, enabled, createdAt) " +
            "VALUES (#{customerId}, #{name}, #{centerLat}, #{centerLon}, #{radiusMeters}, #{enabled}, #{createdAt})"})
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void insert(Geofence geofence);

    @Update({"UPDATE geofence SET name = #{name}, centerLat = #{centerLat}, centerLon = #{centerLon}, " +
            "radiusMeters = #{radiusMeters}, enabled = #{enabled} WHERE id = #{id} AND customerId = #{customerId}"})
    void update(Geofence geofence);

    @Delete({"DELETE FROM geofence WHERE id = #{id} AND customerId = #{customerId}"})
    void delete(@Param("id") int id, @Param("customerId") int customerId);

    @Select({"SELECT * FROM geofence WHERE customerId = #{customerId} ORDER BY id"})
    List<Geofence> listByCustomer(@Param("customerId") int customerId);

    @Select({"SELECT * FROM geofence WHERE customerId = #{customerId} AND enabled = TRUE"})
    List<Geofence> listEnabled(@Param("customerId") int customerId);

    /** Last-known inside/outside state for this device against one geofence; null if never evaluated. */
    @Select({"SELECT inside FROM geofence_device_state WHERE geofenceId = #{geofenceId} AND deviceNumber = #{deviceNumber}"})
    Boolean getState(@Param("geofenceId") int geofenceId, @Param("deviceNumber") String deviceNumber);

    /** Upserts the device's current inside/outside state for one geofence. */
    @Insert({"INSERT INTO geofence_device_state (geofenceId, deviceNumber, inside, updatedAt) " +
            "VALUES (#{geofenceId}, #{deviceNumber}, #{inside}, #{updatedAt}) " +
            "ON CONFLICT (geofenceId, deviceNumber) DO UPDATE SET inside = #{inside}, updatedAt = #{updatedAt}"})
    void upsertState(@Param("geofenceId") int geofenceId, @Param("deviceNumber") String deviceNumber,
                      @Param("inside") boolean inside, @Param("updatedAt") long updatedAt);
}

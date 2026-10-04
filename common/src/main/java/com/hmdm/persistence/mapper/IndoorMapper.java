package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.IndoorFingerprint;
import com.hmdm.persistence.domain.IndoorMap;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

public interface IndoorMapper {
    @Insert("INSERT INTO indoorMap (customerId, plan, image, updatedAt) " +
            "VALUES (#{customerId}, #{plan}, #{image}, #{updatedAt}) " +
            "ON CONFLICT (customerId) DO UPDATE SET plan = EXCLUDED.plan, image = EXCLUDED.image, " +
            "updatedAt = EXCLUDED.updatedAt")
    void upsertMap(IndoorMap map);

    @Select("SELECT * FROM indoorMap WHERE customerId = #{customerId}")
    IndoorMap findMap(@Param("customerId") int customerId);

    @Insert("INSERT INTO indoorFingerprint (customerId, x, y, rssi, mag, createdAt, createdBy) " +
            "VALUES (#{customerId}, #{x}, #{y}, #{rssi}, #{mag}, #{createdAt}, #{createdBy})")
    void insertFingerprint(IndoorFingerprint fingerprint);

    @Select("SELECT * FROM indoorFingerprint WHERE customerId = #{customerId} ORDER BY id")
    List<IndoorFingerprint> listFingerprints(@Param("customerId") int customerId);

    @Select("SELECT COUNT(*) FROM indoorFingerprint WHERE customerId = #{customerId}")
    int countFingerprints(@Param("customerId") int customerId);

    @Delete("DELETE FROM indoorFingerprint WHERE id = #{id} AND customerId = #{customerId}")
    int deleteFingerprint(@Param("id") int id, @Param("customerId") int customerId);

    @Delete("DELETE FROM indoorFingerprint WHERE customerId = #{customerId}")
    int clearFingerprints(@Param("customerId") int customerId);
}

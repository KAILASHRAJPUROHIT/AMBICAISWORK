package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.RemoteSnapshot;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/** MyBatis mapper for {@code remoteSnapshot} — the "remote view" session's latest per-kind
 *  screen/camera/mic capture. Auto-registered via the mapper package scan. */
public interface RemoteSnapshotMapper {

    @Insert({"INSERT INTO remoteSnapshot (customerId, deviceNumber, kind, capturedAt, contentType, data) " +
            "VALUES (#{customerId}, #{deviceNumber}, #{kind}, #{capturedAt}, #{contentType}, #{data}) " +
            "ON CONFLICT (deviceNumber, kind) DO UPDATE SET " +
            "capturedAt = EXCLUDED.capturedAt, contentType = EXCLUDED.contentType, data = EXCLUDED.data"})
    void upsert(RemoteSnapshot snapshot);

    /** Metadata only (no `data`) — for the console's "what's available" summary. */
    @Select({"SELECT id, customerId, deviceNumber, kind, capturedAt, contentType FROM remoteSnapshot " +
            "WHERE deviceNumber = #{deviceNumber}"})
    List<RemoteSnapshot> listMetaByDevice(@Param("deviceNumber") String deviceNumber);

    /** One full row (including `data`) — for actually streaming a snapshot's bytes. */
    @Select({"SELECT * FROM remoteSnapshot WHERE deviceNumber = #{deviceNumber} AND kind = #{kind}"})
    RemoteSnapshot findByDeviceAndKind(@Param("deviceNumber") String deviceNumber, @Param("kind") String kind);

    @Delete({"DELETE FROM remoteSnapshot WHERE deviceNumber = #{deviceNumber}"})
    void deleteByDevice(@Param("deviceNumber") String deviceNumber);
}

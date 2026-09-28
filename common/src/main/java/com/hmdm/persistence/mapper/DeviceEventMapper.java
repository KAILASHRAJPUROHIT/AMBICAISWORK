package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.AppUsageRow;
import com.hmdm.persistence.domain.DeviceEvent;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/** MyBatis mapper for the agent lifecycle event stream ({@link DeviceEvent}). */
public interface DeviceEventMapper {

    @Insert({"INSERT INTO device_event (deviceNumber, type, ts, detail) " +
            "VALUES (#{deviceNumber}, #{type}, #{ts}, #{detail})"})
    void insert(DeviceEvent event);

    @Select({"SELECT id, deviceNumber, type, ts, detail FROM device_event " +
            "WHERE deviceNumber = #{deviceNumber} AND ts >= #{since} ORDER BY ts DESC, id DESC LIMIT #{limit}"})
    List<DeviceEvent> list(@Param("deviceNumber") String deviceNumber,
                           @Param("since") long since, @Param("limit") int limit);

    /** Retention: delete events of one type older than {@code before} (epoch ms). */
    @Delete({"DELETE FROM device_event WHERE type = #{type} AND ts < #{before}"})
    int deleteTypeOlderThan(@Param("type") String type, @Param("before") long before);

    /** Retention: delete all events older than {@code before} (epoch ms). */
    @Delete({"DELETE FROM device_event WHERE ts < #{before}"})
    int deleteOlderThan(@Param("before") long before);

    /**
     * App-time report: sums the agent's {@code appUsage} events ("pkg|Label|seconds") per device, local day
     * (Asia/Kolkata) and app, for one customer's devices. A session is bucketed by the day it started.
     */
    @Select({"SELECT e.deviceNumber AS deviceNumber, " +
            "to_char(to_timestamp(e.ts / 1000.0) AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD') AS day, " +
            "split_part(e.detail, '|', 1) AS pkg, max(split_part(e.detail, '|', 2)) AS label, " +
            "sum(CASE WHEN split_part(e.detail, '|', 3) ~ '^[0-9]{1,9}$' THEN split_part(e.detail, '|', 3)::bigint ELSE 0 END) AS seconds, " +
            "count(*)::int AS sessions " +
            "FROM device_event e JOIN devices d ON d.number = e.deviceNumber " +
            "WHERE d.customerId = #{customerId} AND e.type = 'appUsage' AND e.ts >= #{from} AND e.ts < #{to} " +
            "AND (#{deviceNumber}::text IS NULL OR e.deviceNumber = #{deviceNumber}) " +
            "GROUP BY 1, 2, 3 ORDER BY 1, 2, 5 DESC"})
    List<AppUsageRow> appUsage(@Param("customerId") int customerId, @Param("from") long from, @Param("to") long to,
                               @Param("deviceNumber") String deviceNumber);
}

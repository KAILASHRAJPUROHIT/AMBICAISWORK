package com.hmdm.persistence.mapper;

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
}

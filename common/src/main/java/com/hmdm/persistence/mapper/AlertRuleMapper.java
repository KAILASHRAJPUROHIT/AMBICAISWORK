package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.AlertRule;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

/** CRUD + event-match lookup for {@code alert_rule}. Kept separate from the shared
 *  {@link DeviceMapper}, matching the {@link AgentDeviceMapper} convention for
 *  agent-v1-adjacent features that don't need to touch the core device mapper. */
public interface AlertRuleMapper {

    @Insert({"INSERT INTO alert_rule (customerId, eventType, webhookUrl, email, enabled, createdAt) " +
            "VALUES (#{customerId}, #{eventType}, #{webhookUrl}, #{email}, #{enabled}, #{createdAt})"})
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void insert(AlertRule rule);

    @Update({"UPDATE alert_rule SET eventType = #{eventType}, webhookUrl = #{webhookUrl}, " +
            "email = #{email}, enabled = #{enabled} WHERE id = #{id} AND customerId = #{customerId}"})
    void update(AlertRule rule);

    @Delete({"DELETE FROM alert_rule WHERE id = #{id} AND customerId = #{customerId}"})
    void delete(@Param("id") int id, @Param("customerId") int customerId);

    @Select({"SELECT * FROM alert_rule WHERE customerId = #{customerId} ORDER BY id"})
    List<AlertRule> listByCustomer(@Param("customerId") int customerId);

    /** Rules that should fire for this event: enabled, this customer, and either a matching
     *  eventType or a null/empty eventType ("any event"). */
    @Select({"SELECT * FROM alert_rule WHERE customerId = #{customerId} AND enabled = TRUE " +
            "AND (eventType IS NULL OR eventType = '' OR eventType = #{eventType})"})
    List<AlertRule> listMatching(@Param("customerId") int customerId, @Param("eventType") String eventType);
}

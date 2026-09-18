/*
 *
 * Headwind MDM: Open Source Android MDM Software
 * https://h-mdm.com
 *
 * Copyright (C) 2019 Headwind Solutions LLC (http://h-sms.com)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *       http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */

package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.AgentRollout;
import com.hmdm.persistence.domain.RolloutCommandStatusRow;
import com.hmdm.persistence.domain.RolloutDeviceRow;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.SelectKey;
import org.apache.ibatis.annotations.Update;

import java.util.List;

/** MyBatis mapper for staged agent-APK rollouts. Auto-registered via the mapper package scan. */
public interface RolloutMapper {

    @Insert({"INSERT INTO agentRollout (customerId, targetVersion, packageName, apkUrl, apkSha256, apkVersionCode, stage, createdAt, updatedAt, trackingMode, displayName) " +
            "VALUES (#{customerId}, #{targetVersion}, #{packageName}, #{apkUrl}, #{apkSha256}, #{apkVersionCode}, #{stage}, #{createdAt}, #{updatedAt}, #{trackingMode}, #{displayName})"})
    @SelectKey(statement = "SELECT currval('agentrollout_id_seq')", keyColumn = "id", keyProperty = "id",
            before = false, resultType = int.class)
    void insertRollout(AgentRollout rollout);

    @Insert({"INSERT INTO agentRolloutCanary (rolloutId, deviceNumber) VALUES (#{rolloutId}, #{deviceNumber}) " +
            "ON CONFLICT DO NOTHING"})
    void insertCanary(@Param("rolloutId") int rolloutId, @Param("deviceNumber") String deviceNumber);

    /** Most recent active ("version"-tracked, i.e. the agent's own) rollout — the Settings page's
     *  single "Agent rollout" card. Package-scoped so a concurrent Library-app rollout never
     *  shadows it (and vice versa via {@link #findActiveByCustomerAndPackage}). */
    @Select({"SELECT * FROM agentRollout WHERE customerId = #{customerId} AND trackingMode = 'version' " +
            "AND stage IN ('canary','fleet') ORDER BY id DESC LIMIT 1"})
    AgentRollout findActiveByCustomer(@Param("customerId") int customerId);

    @Select({"SELECT * FROM agentRollout WHERE customerId = #{customerId} AND packageName = #{packageName} " +
            "AND stage IN ('canary','fleet') ORDER BY id DESC LIMIT 1"})
    AgentRollout findActiveByCustomerAndPackage(@Param("customerId") int customerId, @Param("packageName") String packageName);

    /** Every active "command"-tracked (Library-app) rollout for this customer — the Apps page's
     *  per-app progress cards. */
    @Select({"SELECT * FROM agentRollout WHERE customerId = #{customerId} AND trackingMode = 'command' " +
            "AND stage IN ('canary','fleet') ORDER BY id DESC"})
    List<AgentRollout> listActiveAppRollouts(@Param("customerId") int customerId);

    @Select({"SELECT * FROM agentRollout WHERE id = #{id}"})
    AgentRollout findById(@Param("id") int id);

    @Update({"UPDATE agentRollout SET stage = #{stage}, updatedAt = #{updatedAt} WHERE id = #{id}"})
    void updateStage(@Param("id") int id, @Param("stage") String stage, @Param("updatedAt") long updatedAt);

    @Select({"SELECT deviceNumber FROM agentRolloutCanary WHERE rolloutId = #{rolloutId}"})
    List<String> listCanaryNumbers(@Param("rolloutId") int rolloutId);

    @Select({"SELECT d.number AS deviceNumber, s.agentVersion AS agentVersion, d.agentCapabilities AS capabilitiesJson " +
            "FROM devices d LEFT JOIN device_state s ON s.deviceNumber = d.number WHERE d.customerId = #{customerId}"})
    List<RolloutDeviceRow> listCustomerDevices(@Param("customerId") int customerId);

    @Select({"SELECT DISTINCT c.deviceNumber FROM agentCommand c JOIN devices d ON d.number = c.deviceNumber " +
            "WHERE d.customerId = #{customerId} AND c.type = 'app.install' AND c.status IN ('pending','delivered')"})
    List<String> listPendingInstallNumbers(@Param("customerId") int customerId);

    /** Records which live {@code agentCommand} row is this "command"-tracked rollout's install
     *  attempt for one device, so progress can be read straight off that command's own status. */
    @Insert({"INSERT INTO agentRolloutCommand (rolloutId, deviceNumber, commandId) VALUES (#{rolloutId}, #{deviceNumber}, #{commandId}) " +
            "ON CONFLICT (rolloutId, deviceNumber) DO UPDATE SET commandId = EXCLUDED.commandId"})
    void upsertRolloutCommand(@Param("rolloutId") int rolloutId, @Param("deviceNumber") String deviceNumber, @Param("commandId") int commandId);

    @Select({"SELECT rc.deviceNumber AS deviceNumber, c.status AS status FROM agentRolloutCommand rc " +
            "JOIN agentCommand c ON c.id = rc.commandId WHERE rc.rolloutId = #{rolloutId}"})
    List<RolloutCommandStatusRow> listCommandStatuses(@Param("rolloutId") int rolloutId);
}

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

package com.hmdm.persistence.domain;

import java.io.Serializable;

/** The latest screen/camera/mic capture for one device + kind — see the {@code remoteSnapshot}
 *  table comment. {@code kind} is one of {@code screen | cameraFront | cameraBack | mic}. */
public class RemoteSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private Integer id;
    private Integer customerId;
    private String deviceNumber;
    private String kind;
    private Long capturedAt;
    private String contentType;
    private byte[] data;

    public Integer getId() { return id; }
    public void setId(Integer id) { this.id = id; }

    public Integer getCustomerId() { return customerId; }
    public void setCustomerId(Integer customerId) { this.customerId = customerId; }

    public String getDeviceNumber() { return deviceNumber; }
    public void setDeviceNumber(String deviceNumber) { this.deviceNumber = deviceNumber; }

    public String getKind() { return kind; }
    public void setKind(String kind) { this.kind = kind; }

    public Long getCapturedAt() { return capturedAt; }
    public void setCapturedAt(Long capturedAt) { this.capturedAt = capturedAt; }

    public String getContentType() { return contentType; }
    public void setContentType(String contentType) { this.contentType = contentType; }

    public byte[] getData() { return data; }
    public void setData(byte[] data) { this.data = data; }
}

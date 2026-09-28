package com.hmdm.persistence.domain;

import java.io.Serializable;

/** One device x day x app total, aggregated from the agent's {@code appUsage} events ("pkg|Label|seconds"). */
public class AppUsageRow implements Serializable {
    private static final long serialVersionUID = 1L;
    private String deviceNumber;
    /** Local calendar day (Asia/Kolkata), "yyyy-MM-dd". */
    private String day;
    private String pkg;
    private String label;
    private Long seconds;
    private Integer sessions;

    public String getDeviceNumber() { return deviceNumber; }
    public void setDeviceNumber(String v) { this.deviceNumber = v; }
    public String getDay() { return day; }
    public void setDay(String v) { this.day = v; }
    public String getPkg() { return pkg; }
    public void setPkg(String v) { this.pkg = v; }
    public String getLabel() { return label; }
    public void setLabel(String v) { this.label = v; }
    public Long getSeconds() { return seconds; }
    public void setSeconds(Long v) { this.seconds = v; }
    public Integer getSessions() { return sessions; }
    public void setSessions(Integer v) { this.sessions = v; }
}

package com.hmdm.persistence;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.DeviceUnlockOtp;
import com.hmdm.persistence.mapper.DeviceUnlockMapper;

@Singleton
public class DeviceUnlockDAO {
    private final DeviceUnlockMapper mapper;

    @Inject
    public DeviceUnlockDAO(DeviceUnlockMapper mapper) { this.mapper = mapper; }

    public void insert(DeviceUnlockOtp o) { mapper.insert(o); }
    public DeviceUnlockOtp latestOpen(String deviceNumber) { return mapper.latestOpen(deviceNumber, System.currentTimeMillis()); }
    public void bumpAttempts(int id) { mapper.bumpAttempts(id); }
    public boolean markUsed(int id) { return mapper.markUsed(id, System.currentTimeMillis()) == 1; }
    public int countSince(String deviceNumber, long since) { return mapper.countSince(deviceNumber, since); }
    public void purge() { mapper.purge(System.currentTimeMillis() - 24L * 3600_000L); }
}

package com.hmdm.persistence;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.ConsoleLoginOtp;
import com.hmdm.persistence.domain.ConsoleTrustedDevice;
import com.hmdm.persistence.mapper.ConsoleDeviceMapper;

import java.util.List;

@Singleton
public class ConsoleDeviceDAO {
    private final ConsoleDeviceMapper mapper;

    @Inject
    public ConsoleDeviceDAO(ConsoleDeviceMapper mapper) { this.mapper = mapper; }

    public ConsoleTrustedDevice findTrusted(int userId, String fp) { return mapper.findTrusted(userId, fp); }
    public List<ConsoleTrustedDevice> listTrusted(int userId) { return mapper.listTrusted(userId); }
    public void upsertTrusted(ConsoleTrustedDevice d) { mapper.upsertTrusted(d); }
    public void touchTrusted(int id) { mapper.touchTrusted(id, System.currentTimeMillis()); }
    public boolean deleteTrusted(int id, int userId) { return mapper.deleteTrusted(id, userId) == 1; }
    public void insertOtp(ConsoleLoginOtp o) { mapper.insertOtp(o); }
    public ConsoleLoginOtp latestOpenOtp(int userId, String fp) { return mapper.latestOpenOtp(userId, fp, System.currentTimeMillis()); }
    public void bumpAttempts(int id) { mapper.bumpAttempts(id); }
    public boolean markUsed(int id) { return mapper.markUsed(id, System.currentTimeMillis()) == 1; }
    public int countOtpSince(int userId, long since) { return mapper.countOtpSince(userId, since); }
    public void purgeOtp() { mapper.purgeOtp(System.currentTimeMillis() - 24L * 3600_000L); }
}

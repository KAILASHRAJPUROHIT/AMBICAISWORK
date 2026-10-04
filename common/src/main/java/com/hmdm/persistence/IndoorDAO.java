package com.hmdm.persistence;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.IndoorFingerprint;
import com.hmdm.persistence.domain.IndoorMap;
import com.hmdm.persistence.mapper.IndoorMapper;

import java.util.List;

@Singleton
public class IndoorDAO {
    private final IndoorMapper mapper;

    @Inject
    public IndoorDAO(IndoorMapper mapper) { this.mapper = mapper; }

    public void saveMap(IndoorMap map) { mapper.upsertMap(map); }
    public IndoorMap findMap(int customerId) { return mapper.findMap(customerId); }
    public void addFingerprint(IndoorFingerprint f) { mapper.insertFingerprint(f); }
    public List<IndoorFingerprint> listFingerprints(int customerId) { return mapper.listFingerprints(customerId); }
    public int countFingerprints(int customerId) { return mapper.countFingerprints(customerId); }
    public boolean deleteFingerprint(int id, int customerId) { return mapper.deleteFingerprint(id, customerId) > 0; }
    public int clearFingerprints(int customerId) { return mapper.clearFingerprints(customerId); }
}

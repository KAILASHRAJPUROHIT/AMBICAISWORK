package com.hmdm.persistence;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import com.hmdm.persistence.domain.RemoteSnapshot;
import com.hmdm.persistence.mapper.RemoteSnapshotMapper;

import java.util.List;

/** DAO for the "remote view" session's latest screen/camera/mic capture. Thin wrapper over
 *  {@link RemoteSnapshotMapper}. */
@Singleton
public class RemoteSnapshotDAO {

    private final RemoteSnapshotMapper mapper;

    @Inject
    public RemoteSnapshotDAO(RemoteSnapshotMapper mapper) {
        this.mapper = mapper;
    }

    public void upsert(RemoteSnapshot snapshot) {
        mapper.upsert(snapshot);
    }

    public List<RemoteSnapshot> listMetaByDevice(String deviceNumber) {
        return mapper.listMetaByDevice(deviceNumber);
    }

    public RemoteSnapshot findByDeviceAndKind(String deviceNumber, String kind) {
        return mapper.findByDeviceAndKind(deviceNumber, kind);
    }

    public void deleteByDevice(String deviceNumber) {
        mapper.deleteByDevice(deviceNumber);
    }
}

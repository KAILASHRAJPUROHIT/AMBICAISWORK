package com.mdmesh.core.store

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.adminPasscodeDataStore: DataStore<Preferences> by
    preferencesDataStore(name = "mdm_admin_passcode")

/**
 * Persists the fleet-wide admin passcode hash delivered on every check-in
 * ([com.mdmesh.proto.AgentCheckInResponse.adminPasscodeHash]), so it survives process death and is
 * available to [com.mdmesh.agent.KioskLauncherActivity.promptExit] even if the device is offline
 * when someone tries to exit kiosk. Only the hash is ever stored — the raw passcode never reaches
 * the device.
 */
interface AdminPasscodeStore {
    suspend fun save(hash: String?)
    suspend fun load(): String?
    fun flow(): Flow<String?>
}

class DataStoreAdminPasscodeStore(private val context: Context) : AdminPasscodeStore {

    override suspend fun save(hash: String?) {
        context.adminPasscodeDataStore.edit {
            if (hash.isNullOrBlank()) it.remove(KEY) else it[KEY] = hash
        }
    }

    override suspend fun load(): String? =
        context.adminPasscodeDataStore.data.map { it[KEY] }.first()

    override fun flow(): Flow<String?> = context.adminPasscodeDataStore.data.map { it[KEY] }

    private companion object {
        val KEY = stringPreferencesKey("admin_passcode_hash")
    }
}

/** In-memory [AdminPasscodeStore] for unit tests. */
class InMemoryAdminPasscodeStore(initial: String? = null) : AdminPasscodeStore {
    private val state = MutableStateFlow(initial)

    override suspend fun save(hash: String?) {
        state.value = hash
    }

    override suspend fun load(): String? = state.value

    override fun flow(): Flow<String?> = state
}

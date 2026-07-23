# Data Layer

The Bosch eBike Flow app uses **4 separate Room databases** plus DataStore and SharedPreferences for local persistence. This document covers the database schemas, repository pattern, and data flow.

## Room Databases

### 1. RoomBikesDatabase (Bike Registration Data)

The primary database storing bike registration, component data, and cloud sync queue.

**Location:** `smali_classes2/com/bosch/ebike/appcore/bike/internal/datasources/local/room/`

**Version:** 100+ (auto-migrations from 31 through 100, plus manual migration 13→31)

### DAOs

| DAO | Purpose |
|---|---|
| `BikeDao` | CRUD operations on bikes |
| `BluetoothComponentDao` | CRUD operations on BLE components |
| `WiredComponentDao` | CRUD operations on wired components |
| `CloudSyncRequestDao` | Pending cloud sync queue |

### Entities

**Core Entities:**

| Entity | Purpose |
|---|---|
| `RoomBike` | Core bike entity (name, ID, registration data) |
| `RoomBluetoothComponent` | BLE components (with `PeripheralProfile`) |
| `RoomWiredComponent` | Wired components |
| `RoomCloudSyncRequest` | Pending cloud sync queue items |
| `RoomRegistration` | Bike registration data |
| `RoomCustomData` | Custom user data per bike |

**Component Models (nested in `RoomComponent`):**

| Component | Data |
|---|---|
| `Battery` | SoC, voltage, temperature, serial number |
| `AggregatedBattery` | Combined battery stats |
| `ConnectModule` | GPS/cellular module info |
| `DriveUnit` | Motor info with `AssistMode`, `Application`, `Lock` |
| `HeadUnit` | Display unit info |
| `RemoteControl` | Handlebar remote with `Button`, `EShift` |
| `AntiLockBrakeSystem` | ABS module info |

**Diagnostic Entities:**

| Entity | Purpose |
|---|---|
| `RoomComponentFailure` | Component failure records |
| `RoomComponentIssue` | Component issue records |

### Operations

High-level persistence operations with database transactions:

| Operation | Purpose |
|---|---|
| `StoreRegistration` | Store bike registration |
| `ReadAllRegistrations` | Read all registered bikes |
| `StoreComponents` | Store all components for a bike |
| `InsertComponent` | Insert single component |
| `DeleteComponent` | Delete component |

**Key file:** `smali_classes2/com/bosch/ebike/appcore/bike/internal/datasources/local/room/RoomPersistence.smali`

---

### 2. TheftDetectionDatabase (GPS Coordinates for Theft Tracking)

Stores GPS coordinates for the theft detection/alarm system.

**Location:** `smali_classes2/com/bosch/ebike/antitheft/datasources/room/`

**Version:** 1

### DAO

| DAO | Purpose |
|---|---|
| `TheftDetectionLocationDao` | CRUD operations on theft detection locations |

### Entity

| Entity | Purpose |
|---|---|
| `RoomTheftDetectionLocation` | GPS coordinates (lat, lon, timestamp) for theft tracking |

### Type Converters

| Converter | Purpose |
|---|---|
| `InstantConverter` | Converts `java.time.Instant` to/from Long |

### Data Source

| Class | Purpose |
|---|---|
| `RoomTheftDetectionLocalDataSource` | Wraps DAO with Flow-based access |
| `ClearTheftDetectionDatabase` / `RoomClearTheftDetectionDatabase` | Database cleanup on logout |

**Key file:** `smali_classes2/com/bosch/ebike/antitheft/datasources/room/RoomTheftDetectionLocalDataSource.smali`

---

### 3. ActivityDatabase (Ride Tracking)

Stores ride samples, assist mode usage, and upload state.

**Location:** `smali_classes2/com/bosch/ebike/activitytracking/datasources/local/database/`

**Version:** 10 (migrations 1→10, with destructive migration fallback)

### DAOs

| DAO | Purpose |
|---|---|
| `SampleDao` | Ride sample data (per-second telemetry) |
| `SampleTrickStatsDao` | Trick stats (jump distance, air time) |
| `SampledActivityInfoDao` | Activity metadata |
| `SampleAssistModeUsageDao` | Assist mode usage tracking |
| `UploadingInfoDao` | Upload state tracking |

### Type Converters

| Converter | Purpose |
|---|---|
| `ActivityIdConverter` | Activity ID conversion |
| `BikeIdConverter` | Bike ID conversion |
| `DurationConverter` | Duration conversion |
| `LengthConverter` | Length/distance conversion |
| `UuidConverter` | UUID conversion |

### Storage

| Class | Purpose |
|---|---|
| `SampledActivityStorageImpl` | Stores ride samples and assist mode usage with transactions |
| `UploaderStorageImpl` | Tracks upload state for ride data |

**Key file:** `smali_classes2/com/bosch/ebike/activitytracking/datasources/local/database/SampledActivityStorageImpl.smali`

---

### 4. UpdateSetsDatabase (FOTA Firmware Updates)

Stores metadata for firmware over-the-air updates.

**Location:** `smali_classes3/com/bosch/ebike/fota/datasources/local/updatesetsdatabase/`

**Version:** 1

### DAOs

| DAO | Purpose |
|---|---|
| `UpdateSetApplicationDao` | Application firmware metadata |
| `UpdateSetAssistModeDao` | Assist mode firmware metadata |
| `UpdateSetInfoDao` | Update set info |
| `UpdateSetMetadataDao` | Update set metadata |
| `UpdateSetSoftwareDao` | Software component metadata |

### Entities

| Entity | Purpose |
|---|---|
| `FotaUpdateSetId` | Update set identifier |
| `FotaUpdateSetPki` | PKI (public key infrastructure) data |
| `UpdateSetFile` | Update set file metadata |

### Type Converters

| Converter | Purpose |
|---|---|
| `FotaUpdateSetPkiConverter` | PKI data conversion |

**Key file:** `smali_classes3/com/bosch/ebike/fota/datasources/local/updatesetsdatabase/`

---

## Repository Pattern

The app uses a generic **cache-then-network** repository pattern.

### Repository Interface

```kotlin
interface Repository<K, E> {
    fun entityFlow(entityKeyFlow: Flow<K>): Flow<E>
}
```

### CachedApiRepository

**Location:** `smali_classes4/com/bosch/ebike/repository/CachedApiRepository.smali`

Generic implementation that:
1. Loads cached entity from local storage
2. Emits cached entity if found
3. Fetches fresh data from network
4. On success: emits new entity, saves to cache
5. On 404: removes cached entry, emits null
6. On other errors: logs via `retrofit2.HttpException` handling

**Constructor parameters:**
- `fetch: suspend (K) -> E` -- Network fetch function
- `loadCachedEntity: suspend (K) -> E?` -- Local cache read
- `saveCachedEntity: suspend (K, E) -> Unit` -- Local cache write
- `removeCachedEntity: suspend (K) -> Unit` -- Cache eviction
- `ioContext: CoroutineContext` -- Dispatcher (usually `Dispatchers.IO`)
- `entityName: String` -- For logging

**Implementation:**
```kotlin
fun entityFlow(entityKeyFlow: Flow<K>): Flow<E> =
    entityKeyFlow
        .transformLatest { key ->
            // Emit cached data first
            val cached = loadCachedEntity(key)
            if (cached != null) emit(cached)
            
            // Fetch from network
            fetchAndEmitEntity(key)
        }
        .flowOn(ioContext)
```

### Usage Example

```kotlin
val bikeProfileRepository = CachedApiRepository<BikeId, BikeProfile>(
    fetch = { bikeId -> api.getBikeProfile(bikeId) },
    loadCachedEntity = { bikeId -> roomBikeDao.getBike(bikeId) },
    saveCachedEntity = { bikeId, profile -> roomBikeDao.insert(profile) },
    removeCachedEntity = { bikeId -> roomBikeDao.delete(bikeId) },
    ioContext = Dispatchers.IO,
    entityName = "BikeProfile"
)

// Observe bike profile (emits cached first, then network)
bikeProfileRepository.entityFlow(bikeIdFlow).collect { profile ->
    updateUi(profile)
}
```

## DataStore

The app uses **Jetpack DataStore** for key-value storage.

### Use Cases

| DataStore | Purpose |
|---|---|
| `AuthTokenDataStore` | OAuth2 tokens (encrypted) |
| User preferences | UI settings, onboarding state |
| Feature flags | Remote config cache |
| Debug settings | Developer options |

### Encrypted DataStore

Sensitive data (auth tokens) uses encrypted DataStore:

**Key file:** `smali_classes2/com/bosch/ebike/authentication/datasources/SecureAuthDataStoreFactory.smali`

## SharedPreferences

Legacy key-value storage for simple preferences.

### Use Cases

| Preference | Purpose |
|---|---|
| `app_config` | App configuration |
| `debug_settings` | Developer options |
| `onboarding_state` | Onboarding completion flags |

## Data Flow Examples

### Example 1: Reading Bike Profile

```
1. UI observes bikeProfileRepository.entityFlow(bikeId)
2. Repository loads cached bike from RoomBikesDatabase
3. Repository emits cached bike to UI
4. Repository fetches bike from Rider Profile API
5. On success: saves to Room, emits to UI
6. On 404: removes from Room, emits null
7. On error: logs error, keeps showing cached data
```

### Example 2: Syncing Bike Components to Cloud

```
1. BLE reads component data via MessageBus
2. Component data mapped to CloudSync DTOs
3. CloudSyncRequest queued in RoomBikesDatabase
4. WorkManager triggers CloudSync worker
5. Worker reads pending CloudSyncRequests
6. Worker serializes DTOs to JSON:API format
7. Worker POSTs to Rider Profile API
8. On success: deletes CloudSyncRequest from Room
9. On error: keeps request for retry
```

### Example 3: Recording Ride Activity

```
1. User starts ride (Riding screen)
2. ActivityTracking service subscribes to MessageBus data points
3. Per-second telemetry written to ActivityDatabase
4. GPS coordinates written to ActivityDatabase
5. Heart rate data written to ActivityDatabase (if sensor connected)
6. User stops ride
7. Activity marked as complete
8. WorkManager triggers upload worker
9. Worker reads activity from ActivityDatabase
10. Worker maps to BES3 ActivityService protobuf
11. Worker uploads to Ingestion API
12. On success: marks as uploaded in UploadingInfoDao
```

## Database Migrations

### RoomBikesDatabase

The database has undergone extensive schema evolution:
- **Version 13**: Initial schema
- **Version 13 → 31**: Manual migration (major schema change)
- **Version 31 → 100**: Auto-migrations (incremental changes)

This suggests a major refactoring occurred between versions 13 and 31, likely related to the component model restructuring.

### ActivityDatabase

- **Version 1 → 10**: Incremental migrations
- **Destructive migration fallback**: If migration fails, database is recreated

This suggests the activity tracking schema is still evolving.

## Data Security

### Encryption

- **Auth tokens**: Encrypted DataStore
- **BLE bonding keys**: Managed by Android system
- **Sensitive user data**: Not stored locally (fetched on-demand from API)

### Data Wiping

On logout, the app wipes all local data:

| Data | Wiped By |
|---|---|
| Auth tokens | `AuthTokenDataStore.clear()` |
| Bike registration | `RoomBikesDatabase.clearAllTables()` |
| Theft detection locations | `ClearTheftDetectionDatabase` |
| Activity data | `ActivityDatabase.clearAllTables()` |
| FOTA metadata | `UpdateSetsDatabase.clearAllTables()` |
| SharedPreferences | `SharedPreferences.clear()` |

**Key file:** `smali_classes2/com/bosch/ebike/authentication/logoutcleanup/`

### Backup Disabled

```xml
<application android:allowBackup="false"
             android:fullBackupContent="false"
             android:dataExtractionRules="@xml/data_extraction_rules">
```

No automatic backup of app data to Google Drive.

## Performance Considerations

### Database Optimization

- **Indexes**: Frequently queried fields are indexed (e.g., `bike_id`, `timestamp`)
- **Transactions**: Batch operations use transactions for atomicity and performance
- **Flow-based DAOs**: Enable reactive UI updates without polling
- **Paging**: Large lists use Paging 3 library for efficient loading

### Cloud Sync Queue

The `CloudSyncRequest` table acts as an outbox:
- Prevents data loss during offline periods
- Enables batch uploads when connectivity is restored
- Supports retry logic with exponential backoff

### Image Caching

Coil library handles image caching:
- **Memory cache**: LRU cache for recently viewed images
- **Disk cache**: Persistent cache for offline access
- **Network**: OkHttp for image downloads

## Further Reading

- [Architecture Overview](architecture.md) -- High-level system design
- [Backend & API](backend-api.md) -- Cloud services and authentication
- [BLE Communication](ble-communication.md) -- How the app talks to the bike
- [Feature Modules](feature-modules.md) -- How features use the data layer

# Architecture Overview

## High-Level System Design

The Bosch eBike Flow app follows a **modular monolith** architecture with clear domain boundaries. The app is structured around ~100 feature modules, each following a consistent `datasources -> services -> views` layering pattern.

```
┌─────────────────────────────────────────────────────────────────┐
│                         UI Layer (Views)                         │
│  Fragments (XML + Compose) ← ViewModels ← Compose Fragments     │
├─────────────────────────────────────────────────────────────────┤
│                      Service Layer (Business Logic)              │
│  Use cases, state management, orchestration                      │
├─────────────────────────────────────────────────────────────────┤
│                     Data Source Layer                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  Room DB │  │ REST API │  │ MessageBus│  │ DataStore/   │   │
│  │ (local)  │  │ (cloud)  │  │  (BLE)   │  │ SharedPreferences│
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                    Infrastructure Layer                          │
│  Koin DI │ Ktor/OkHttp │ Room │ BLE GATT │ Protobuf │ Coroutines│
└─────────────────────────────────────────────────────────────────┘
```

## Module Layering Convention

Every feature module follows this pattern:

```
com.bosch.ebike.<module>/
  datasources/         # Data access (Room DAOs, API clients, BLE readers)
    local/             # Room database, DataStore, SharedPreferences
    remote/            # REST API clients
    ble/               # MessageBus data point readers
  services/            # Business logic, use cases, state management
  views/               # UI fragments and ViewModels
  model/               # Domain models (optional)
  analytics/           # Analytics tracking (optional)
```

This separation ensures:
- **Testability**: Services can be tested without UI or data layer
- **Reusability**: Data sources can be shared across features
- **Clarity**: Clear boundaries between concerns

## Core Subsystems

### 1. BLE Communication Stack

The app communicates with the eBike via Bluetooth Low Energy. The stack has 4 layers:

```
┌─────────────────────────────────────────┐
│         Feature Modules                 │
│  (Riding, Antitheft, FOTA, etc.)        │
├─────────────────────────────────────────┤
│         MessageBus (Application)        │
│  Typed DataPoints per component         │
│  Read/Write/Subscribe/RPC operations    │
├─────────────────────────────────────────┤
│    CommunicationStack (Protocol)        │
│  Binary message encoding/decoding       │
│  Sequence numbers, routing              │
├─────────────────────────────────────────┤
│    BluetoothCommunication (Transport)   │
│  GATT operations (read/write/notify)    │
│  Connection lifecycle, bonding          │
├─────────────────────────────────────────┤
│         Android BLE API                 │
│  BluetoothLeScanner, BluetoothGatt      │
└─────────────────────────────────────────┘
```

**Key packages:**
- `ble/` -- Low-level GATT wrapper
- `bluetoothcommunication/` -- Connection management, GATT config
- `communicationstack/` -- Binary protocol, message bus gateway
- `messagebus/` -- Typed DataPoint API for features
- `pocketmode/` -- Background auto-reconnection

See [BLE Communication](ble-communication.md) for details.

### 2. Backend API Layer

The app uses a **dual HTTP client architecture** during a migration from OkHttp+Retrofit to Ktor+Ktorfit:

- **New services** (bike profile, ownership, access management): Ktor + Ktorfit
- **Legacy services** (activity, bike lock, theft detection): OkHttp + Retrofit

All APIs are hosted on `*.connected-biking.cloud` with environment-specific subdomains.

**Authentication:** OAuth2 Authorization Code flow via AppAuth library against Bosch Keycloak instances.

**Key packages:**
- `httprest/` -- HTTP clients, interceptors, authenticators
- `authentication/` -- OAuth2 flow, token management
- `backend/` -- Protobuf models for telemetry ingestion

See [Backend & API](backend-api.md) for details.

### 3. Data Persistence

The app uses **4 separate Room databases** plus DataStore/SharedPreferences:

| Database | Purpose | Version |
|---|---|---|
| `RoomBikesDatabase` | Bike registration, components, cloud sync queue | 100+ |
| `TheftDetectionDatabase` | GPS coordinates for theft tracking | 1 |
| `ActivityDatabase` | Ride samples, assist mode usage | 10 |
| `UpdateSetsDatabase` | FOTA firmware update metadata | 1 |

**Repository pattern:** `CachedApiRepository<K, E>` implements cache-then-network: emit cached data first, then fetch from network, handle 404s by clearing cache.

See [Data Layer](data-layer.md) for details.

### 4. Dependency Injection (Koin)

The app uses **Koin** for dependency injection. Modules are composed hierarchically:

```
appModules (root)
  ├─ WorkManagerInitializerModule
  ├─ MessageBusInitializerModule
  ├─ AppExtensionsInitializerModule
  ├─ mainViewsModule (MainViewModel with 18 dependencies)
  └─ ModuleCompositionKt (30+ domain module sets)
       ├─ authModules
       ├─ antiTheftModules (13 modules)
       ├─ activityTrackingModules
       ├─ navigationModules (15+ modules)
       ├─ fotaModules (17 modules)
       ├─ mapModules
       ├─ bikePairingModules
       ├─ ... (20+ more)
```

Each domain module set aggregates the datasources/services/views modules for that feature.

**Key files:**
- `onebikeapp/ModulesKt.smali` -- Root module definitions
- `onebikeapp/ModuleCompositionKt.smali` -- Domain module composition

### 5. UI & Navigation

The app is a **single-activity architecture** with Jetpack Navigation Component:

- **MainActivity** hosts a single `NavHostFragment`
- **Root nav graph** (`global_nav_graph.xml`) includes 80+ sub-graphs
- **Bottom navigation** has 4 tabs: Home, Profile, Planning, Activity Statistics
- **UI framework**: Hybrid XML + Jetpack Compose (mid-migration)
  - Older/complex screens: XML layouts with ViewBinding
  - Newer screens: Jetpack Compose via `ComposeFragment` base class
  - Design system v2 is fully Compose

**Deep links:** Custom URI schemes `onebikeapp://` and `flowApp://` for navigation.

See [UI & Navigation](ui-navigation.md) for details.

## Data Flow Examples

### Example 1: Reading Bike Battery Level

```
1. User opens Home screen
2. HomeViewModel observes MessageBus.Battery.stateOfCharge (DataPoint)
3. MessageBus routes read request to Broker
4. Broker sends ReadMessage to InternalGateway
5. InternalGateway encodes message to binary protocol
6. CommunicationStack writes to BLE GATT characteristic (MCSP send)
7. Bike responds via BLE notification (MCSP receive)
8. CommunicationStack decodes response
9. Broker routes response back to MessageBus
10. MessageBus.Battery.stateOfCharge emits new value
11. HomeViewModel updates UI
```

### Example 2: Syncing Bike Profile to Cloud

```
1. User changes assistance mode setting
2. BikeSettingsViewModel writes new value to MessageBus.DriveUnit.assistMode
3. MessageBus sends WriteMessage to bike via BLE
4. Bike acknowledges, CloudSyncRequest is queued in Room database
5. CloudSync worker runs (WorkManager)
6. CloudSync reads pending requests from Room
7. Maps BES3 protobuf data to CloudSync DTOs (kotlinx.serialization)
8. Sends POST request to Rider Profile API (Ktor/Retrofit)
9. Backend acknowledges, CloudSyncRequest is deleted from Room
```

### Example 3: FOTA Firmware Update

```
1. FotaCheckAvailability queries backend for available updates
2. Backend returns UpdateSet metadata (compatible components, versions)
3. User initiates update from FOTA settings screen
4. FotaDownloadService downloads firmware binary from backend
5. FotaTransferService transfers binary to bike component via BLE
   - Uses LargeBinaryTransport protocol (chunked transfer)
   - Progress shown in UI
6. FotaInstallationService triggers installation on component
7. Component reboots with new firmware
8. FotaReportService generates installation report
9. CloudSync uploads report to backend
```

## Key Design Patterns

### 1. Reactive Streams (Kotlin Flow)

The app is heavily reactive. Most data sources expose `Flow<T>`:
- Room DAOs return `Flow<List<Entity>>`
- MessageBus DataPoints expose `Flow<Value>` for subscriptions
- Network responses are wrapped in `Flow<Resource<T>>`
- ViewModels expose `StateFlow<ViewState>`

### 2. Coroutine-First

All I/O operations are suspend functions. The app uses:
- `viewModelScope` for ViewModel coroutines
- `lifecycleScope` for Fragment/Activity coroutines
- Custom `CoroutineScope` for services (e.g., pocket mode)
- `Dispatchers.IO` for database/network operations

### 3. Sealed Classes for State

State is modeled with sealed classes/enums:
- `LoginStatus` (LoggedIn, LoggedOut, InvalidToken)
- `SubscriptionStatus` (Active, NotActive)
- `ConnectionState` (Connecting, Connected, Disconnecting, Disconnected)
- `BikeUnlockError` (20+ variants)

### 4. Error Handling

Errors are typed and handled explicitly:
- Network errors: `retrofit2.HttpException` with status codes
- BLE errors: `BluetoothFailureReason` sealed class
- Business errors: Domain-specific sealed classes (e.g., `PurchaseSubscription.Error`)

### 5. Feature Flags

The app uses remote configuration for feature flags:
- `FeatureFlags` module reads from backend
- `ConfigurationContainerService` provides runtime config
- A/B testing via `abtesting/` module (Adjust SDK)

## Performance Considerations

### 1. Background Processing

- **WorkManager** for deferrable background work (cloud sync, cleanup)
- **Foreground services** for BLE reconnection (pocket mode)
- **Companion Device Manager** for efficient background BLE scanning

### 2. Database Optimization

- Room databases use indexes on frequently queried fields
- Cloud sync queue prevents data loss during offline periods
- Flow-based DAOs enable reactive UI updates

### 3. Network Optimization

- HTTP caching via OkHttp interceptors
- Protobuf for compact BLE telemetry
- Chunked binary transfer for FOTA (LargeBinaryTransport)

### 4. Memory Management

- Coil for efficient image loading with memory/disk caching
- Lazy initialization of heavy modules (Mapbox, navigation)
- Coroutine cancellation on screen exit

## Security Considerations

### 1. Authentication

- OAuth2 Authorization Code flow (not Implicit)
- Tokens stored in encrypted DataStore
- Automatic token refresh with mutex-guarded thread safety
- Logout cleanup wipes all local data

### 2. BLE Security

- BLE bonding (pairing) required for all communication
- GATT database hash detection to detect tampering
- Component ownership verification for sensitive operations (lock/unlock)

### 3. Data Protection

- `android:allowBackup="false"` -- no ADB backup
- `android:fullBackupContent="false"` -- no auto backup
- Encrypted DataStore for sensitive data (auth tokens)
- Secure store for encryption keys (AES)

### 4. Network Security

- `android:usesCleartextTraffic="false"` -- HTTPS only
- Custom network security config (`res/xml/network_security_config.xml`)
- Certificate pinning (likely, via OkHttp interceptors)

## Testing Strategy

The decompiled code shows evidence of:
- **Unit tests**: Test files in `androidTest/` and `test/` directories (not included in APK)
- **Integration tests**: `messagebusmock/` module for testing without real BLE
- **UI tests**: Compose test utilities in `commonui/`
- **Factory tests**: `testerinterface/` module for production line testing

## Build & Release

### Build System

The app uses **Android App Bundles** (AAB) with split APKs:
- `base.apk` -- Core app code and resources
- `split_config.<abi>.apk` -- Architecture-specific native libs (armeabi_v7a, arm64_v8a, x86, x86_64)
- `split_config.<dpi>.apk` -- Density-specific resources (mdpi, hdpi, xhdpi, xxhdpi, xxxhdpi, tvdpi, ldpi)

### Release Channels

The APK's `ReleaseCategory` determines the backend environment:
- Category 1 → STAGE
- Category 2 → QA
- Category 3 → QA
- Category 4 → PRODUCTION

### Versioning

- `versionName`: 1.34.6 (user-facing)
- `versionCode`: 1125 (internal, monotonically increasing)

## Further Reading

- [BLE Communication](ble-communication.md) -- Deep dive into BLE stack
- [Backend & API](backend-api.md) -- Cloud services and authentication
- [Data Layer](data-layer.md) -- Room databases and repositories
- [UI & Navigation](ui-navigation.md) -- Screens and design system
- [Feature Modules](feature-modules.md) -- Major feature deep dives
- [Module Catalog](module-catalog.md) -- Complete module listing

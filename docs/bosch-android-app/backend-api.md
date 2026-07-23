# Backend & API

The Bosch eBike Flow app communicates with a suite of backend services hosted on
`*.connected-biking.cloud`. This document covers the HTTP client architecture,
authentication, API services, and environment configuration.

## HTTP Client Architecture

The app is mid-migration from **OkHttp + Retrofit** to **Ktor + Ktorfit**. Both
stacks coexist:

| Stack                 | Status                     | Used By                                                                                                                  |
| --------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Ktor + Ktorfit**    | Active (new services)      | Bike profile, ownership, access management, field data, stolen marker                                                    |
| **OkHttp + Retrofit** | Legacy (existing services) | Activity, bike lock, theft detection, push notifications, service book, route service, subscription, ingestion, and more |

### Ktor + Ktorfit (New)

**Key files:**

- `smali_classes3/com/bosch/ebike/httprest/KtorfitHelper.smali` -- Builds
  Ktorfit instances per base URL
- `smali_classes3/com/bosch/ebike/httprest/KtorCloudClient.smali` -- Ktor-based
  HTTP client
- `smali_classes2/com/bosch/ebike/cloud/internal/DefaultCloudDataSourceServiceCreator.smali`
  -- Creates Ktorfit service implementations

**Services using Ktorfit:**

- `AccessManagementCloudService`
- `BikeProfileCloudService`
- `FieldDataCloudService`
- `OwnershipCloudService`
- `StolenMarkerCloudService`

### OkHttp + Retrofit (Legacy)

**Key files:**

- `smali_classes3/com/bosch/ebike/httprest/OkHttpCloudClient.smali` --
  OkHttp3-based client
- `smali_classes3/com/bosch/ebike/httprest/RestInterfaceCreator.smali` --
  Retrofit interface factory
- `smali_classes3/com/bosch/ebike/httprest/RestInterfaceCreatorImpl.smali` --
  Creates Retrofit service implementations

**Services using Retrofit (created via `RestInterfaceCreator`):**

- `createActivity` -- Ride activity data
- `createBikeLock` -- Bike lock/unlock
- `createBikePass` -- Digital bike pass
- `createConsumption` -- Energy consumption
- `createFieldData` -- Field data
- `createIngestionUploader` -- Telemetry upload
- `createObcBikeProfile` -- Bike profile
- `createObcRiderProfile` -- Rider profile
- `createOemTheme` -- OEM theming
- `createPushNotifications` -- Push notification registration
- `createReleaseManagement` -- App release management
- `createRouteService` -- Navigation routes
- `createServiceBook` -- Service history
- `createStatisticFilesUpload` -- Statistics upload
- `createSubscription` -- Subscription management
- `createTheftDetection` -- Theft detection
- `createFormcycleS3Bucket` -- Form cycle S3 uploads
- `createActivityReverseGeoCoding` -- Reverse geocoding

### HTTP Interceptors

The OkHttp client uses these interceptors:

| Interceptor                           | Purpose                                     |
| ------------------------------------- | ------------------------------------------- |
| `HttpAuthenticationHeaderInterceptor` | Adds `Authorization: Bearer <token>` header |
| `HttpDefaultHeaderInterceptor`        | Adds default headers (Content-Type, Accept) |
| `HttpUserAgentInterceptor`            | Adds `User-Agent` header with app version   |
| `HttpRequestIdHeaderInterceptor`      | Adds unique request ID for tracing          |
| `HttpLogger` / `FlowCtLogger`         | HTTP request/response logging               |

**Key file:**
`smali_classes3/com/bosch/ebike/httprest/HttpAuthenticationHeaderInterceptor.smali`

### HTTP Authenticator

When a 401 response is received, the `CloudAuthenticator` refreshes the token:

```
401 Response
    ↓
CloudAuthenticator.authenticate()
    ↓
AuthTokenRefresher.refreshToken()
    ↓ (uses AppAuth AuthorizationService)
    ↓ (mutex-guarded for thread safety)
    ↓ (30-second timeout)
New tokens written to AuthTokenStore
    ↓
Original request retried with new token
```

**Key files:**

- `smali_classes3/com/bosch/ebike/httprest/CloudAuthenticator.smali`
- `smali_classes3/com/bosch/ebike/httprest/AuthTokenRefresher.smali`

## Authentication

### OAuth2 Authorization Code Flow

The app uses the **AppAuth for Android** library (`net.openid.appauth`) for
OAuth2.

**Flow:**

1. App opens browser to Keycloak authorization endpoint
2. User authenticates (username/password, MFA, etc.)
3. Keycloak redirects back to app with authorization code
4. App exchanges code for access token + refresh token
5. Tokens stored in encrypted DataStore
6. Access token used for API calls
7. Refresh token used to get new access token when expired

**Key files:**

- `smali_classes2/com/bosch/ebike/authentication/services/login/internal/AppAuthCodeFlowService.smali`
  -- Core OAuth2 implementation
- `smali_classes2/com/bosch/ebike/authentication/services/configuration/AuthorizationRequestsKt.smali`
  -- Builds authorization requests
- `smali_classes2/com/bosch/ebike/authentication/datasources/AuthTokenDataStore.smali`
  -- Token storage

### Identity Provider (Keycloak)

Bosch uses **Keycloak** as the identity provider with the "Single Key ID" (SKID)
system for unified identity across Bosch eBike services.

| Environment | Auth Server URL                                |
| ----------- | ---------------------------------------------- |
| DEV         | `https://p4.authz.bosch.com/auth/realms/obc/`  |
| STAGE       | `https://p8.authz.bosch.com/auth/realms/obc/`  |
| QA          | `https://p10.authz.bosch.com/auth/realms/obc/` |
| PRODUCTION  | `https://p9.authz.bosch.com/auth/realms/obc/`  |

**Key files:**

- `smali_classes2/com/bosch/ebike/authentication/services/configuration/DefaultAuthConfigurationService.smali`
  -- Provides Keycloak hint value `"skid"` and registration URLs
- `smali_classes2/com/bosch/ebike/authentication/services/login/SingleKeyIdDataSource.smali`
  -- SKID integration

### Token Management

- **`AuthTokenStore`** -- Interface for token persistence
- **`AuthTokenDataStore`** -- Encrypted DataStore implementation
- **`BoschAuthTokens`** -- Token data class (access token, refresh token,
  expiry)
- **`ForceTokenRefresh`** -- Forces immediate token refresh
- **`SecureAuthDataStoreFactory`** -- Creates encrypted DataStore

### Deep Link Redirect

The OAuth2 redirect URI is handled by `RedirectUriReceiverActivity`:

```xml
<activity android:exported="true" android:name="net.openid.appauth.RedirectUriReceiverActivity">
    <intent-filter>
        <action android:name="android.intent.action.VIEW"/>
        <category android:name="android.intent.category.DEFAULT"/>
        <category android:name="android.intent.category.BROWSABLE"/>
        <data android:scheme="onebikeapp-android"/>
        <data android:host="com.bosch.ebike.onebikeapp"/>
        <data android:path="/oauth2redirect"/>
    </intent-filter>
</activity>
```

## Environment Configuration

### Backend Environments

The `BackendEnvironment` enum defines 4 environments:

```kotlin
enum class BackendEnvironment {
    DEV,
    STAGE,
    QA,
    PRODUCTION
}
```

The environment is selected based on the APK's `ReleaseCategory`:

- Category 1 → STAGE
- Category 2 → QA
- Category 3 → QA
- Category 4 → PRODUCTION
- (dev builds) → DEV

**Key file:**
`smali_classes2/com/bosch/ebike/backend/BackendEnvironmentKt.smali`

### Base URLs

All API base URLs follow the pattern:
`https://{service}.{env}.connected-biking.cloud/`

**Key file:**
`smali_classes3/com/bosch/ebike/httprest/DefaultHttpRestSettings.smali`

### Complete Service URL List

| Service                          | Production URL                                                       |
| -------------------------------- | -------------------------------------------------------------------- |
| **Rider Profile**                | `https://obc-rider-profile.prod.connected-biking.cloud/`             |
| **Rider Activity**               | `https://obc-rider-activity.prod.connected-biking.cloud/`            |
| **Bike Lock**                    | `https://lock.prod.connected-biking.cloud/`                          |
| **Theft Detection**              | `https://theft-detection.prod.connected-biking.cloud/`               |
| **Notification**                 | `https://notification.prod.connected-biking.cloud/`                  |
| **Remote Configuration**         | `https://remote-configuration.prod.connected-biking.cloud/`          |
| **Service Book**                 | `https://service-book.prod.connected-biking.cloud/`                  |
| **Ingestion** (telemetry upload) | `https://ingestion.prod.connected-biking.cloud/`                     |
| **Field Data**                   | `https://field-data.prod.connected-biking.cloud/`                    |
| **Commerce**                     | `https://commerce.prod.connected-biking.cloud/`                      |
| **Subscription / IAP**           | `https://in-app-purchase.prod.connected-biking.cloud/`               |
| **Bike Pass**                    | `https://bike-pass.prod.connected-biking.cloud/`                     |
| **Release Management**           | `https://release-management-backend.prod.connected-biking.cloud/`    |
| **Navigation: Geocoding**        | `https://navigation-geocoding.prod.connected-biking.cloud/`          |
| **Navigation: Route Service**    | `https://navigation-routeservice.prod.connected-biking.cloud/`       |
| **Navigation: Consumption**      | `https://navigation-consumptionservice.prod.connected-biking.cloud/` |
| **Komoot Facade**                | `https://komoot-facade.prod.connected-biking.cloud`                  |
| **Strava Facade**                | `https://strava-facade.prod.connected-biking.cloud`                  |
| **Trek Facade**                  | `https://trek-facade.prod.connected-biking.cloud`                    |
| **OEM Theming**                  | `https://theming-api.prod.connected-biking.cloud/`                   |
| **App Highlights (CDN)**         | `https://flowapp.cloudfront-demo.prod.connected-biking.cloud/`       |
| **Legal Content**                | `https://flow.bosch-ebike.com/legal/`                                |
| **Trek Service Tool**            | `https://btss.trekbikes.com/bes3/landing`                            |
| **Legacy API**                   | `https://api.bosch-ebike.com/`                                       |

## CloudSync (Bike Profile Sync)

The `cloudsync/` package synchronizes bike profile data between the app and the
Bosch backend.

### Data Format

The cloud API uses **JSON:API** format. All DTOs are Kotlin-serialized using
`kotlinx.serialization`.

**Key files:** `smali_classes3/com/bosch/ebike/cloudsync/generated/models/`

### DTO Categories

| Category            | Examples                                                                                      |
| ------------------- | --------------------------------------------------------------------------------------------- |
| **Bike Profile**    | `BikeProfileGetDto`, `BikeProfilePostDto`, `BikeProfileV2GetDto`, `BikeRegisterPostDto`       |
| **Drive Unit**      | `DriveUnitGetDto`, `DriveUnitPostDto`, `DriveUnitAssistModesDto`                              |
| **Battery**         | `BatteryDto`, `BatteryPostDto`, `NumberOfFullChargeCyclesDto`                                 |
| **Head Unit**       | `HeadUnitDto`, `HeadUnitPostDto`                                                              |
| **Remote Control**  | `RemoteControlDto`, `RemoteControlPostDto`                                                    |
| **Connect Module**  | `ConnectedModuleDto`, `ConnectedModulePostDto`                                                |
| **Anti-lock Brake** | `AntiLockBrakeSystemDto`, `AntiLockBrakeSystemPostDto`                                        |
| **Settings**        | `AdjustmentsDto`, `AlarmFeatureSettingsDto`, `AssistModeDto`, `BikeLightDto`, `WalkAssistDto` |
| **Metadata**        | `ProductDto`, `OemDto`, `StatisticsDto`, `ServiceDueDto`, `TuningDetectionDto`                |
| **Security**        | `LockDto`, `PseudoBikeIdDto`, `PseudoUserIdDto`                                               |
| **JSON:API**        | `JsonApiDocument*`, `JsonApiResource*`, `JsonApiRelationship`, `JsonApiRequest*`              |

### Sync Flow

```
1. BLE reads component data via MessageBus
2. Data is mapped from BES3 protobuf types to CloudSync DTOs
3. DTOs are serialized to JSON:API format
4. POST request sent to Rider Profile API
5. Backend acknowledges
6. CloudSyncRequest deleted from Room database
```

Conversely, bike profile configurations from the cloud are deserialized and
written to the bike via MessageBus.

## Protobuf Telemetry Ingestion

The `backend/` package defines the Protocol Buffers schema for bike telemetry
data sent to the cloud.

**Key file:** `smali_classes2/backend/Backend.smali`

### Protobuf Messages

**Envelope:**

```protobuf
message Envelope {
    string correlation_id = 1;
    int32 sequence_number = 2;
    TimeReference time_reference = 3;
    repeated Message messages = 4;
    string user_id = 5;
    string device_id = 6;
    int64 timestamp = 7;
    string sender = 8;
    string user_agent = 9;
}
```

**Message:**

```protobuf
message Message {
    Duration time_relative = 1;
    int32 dataPointAddress = 2;
    bytes payload = 3;
}
```

**Heartbeat:**

```protobuf
message Heartbeat {
    int64 time = 1;
    string team = 2;
    string service = 3;
    string component = 4;
    string podName = 5;
}
```

**BatteryHealthStatusUpdate:**

```protobuf
message BatteryHealthStatusUpdate {
    ClientType clientType = 1;
    repeated HarmfulEvent harmfulEvents = 2;
}
```

## Push Notifications

The app uses **Firebase Cloud Messaging** (FCM) for push notifications.

**Key files:**

- `smali_classes4/com/bosch/ebike/pushnotifications/internal/firebase/FlowFirebaseMessagingService.smali`
  -- FCM message handler
- `smali_classes4/com/bosch/ebike/pushnotifications/` -- Notification models and
  handling

**Manifest declaration:**

```xml
<service android:exported="false"
         android:name="com.bosch.ebike.pushnotifications.internal.firebase.FlowFirebaseMessagingService">
    <intent-filter>
        <action android:name="com.google.firebase.MESSAGING_EVENT"/>
    </intent-filter>
</service>
```

## Network Security

### HTTPS Only

```xml
<application android:usesCleartextTraffic="false">
```

All network traffic is HTTPS-only.

### Network Security Config

Custom network security config at `res/xml/network_security_config.xml` likely
includes:

- Certificate pinning for production domains
- Debug overrides for staging environments
- Trust anchors for Bosch internal CAs

### Data Extraction Rules

```xml
<application android:dataExtractionRules="@xml/data_extraction_rules"
             android:fullBackupContent="false">
```

No automatic backup of app data.

## Error Handling

### HTTP Errors

- **401 Unauthorized**: Token refresh via `CloudAuthenticator`
- **404 Not Found**: Cache entry cleared in `CachedApiRepository`
- **Other errors**: Logged via `retrofit2.HttpException`

### Network Errors

- **Timeout**: OkHttp default timeouts (likely 30s connect, 30s read, 30s write)
- **No connectivity**: `NetworkStatusFlowProvider` exposes network status as
  Flow
- **SSL errors**: Handled by OkHttp with custom trust managers

## Further Reading

- [Architecture Overview](architecture.md) -- High-level system design
- [BLE Communication](ble-communication.md) -- How the app talks to the bike
- [Data Layer](data-layer.md) -- Local storage and repositories

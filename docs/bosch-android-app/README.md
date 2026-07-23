# Bosch eBike Flow Android App -- Developer Onboarding

This directory contains developer documentation for the Bosch eBike Flow Android app (v1.34.6), reconstructed from the decompiled APK. The original source code was not available, so this documentation was created by analyzing the decompiled smali bytecode, resources, and assets.

## Quick Start

### What is this app?

The Bosch eBike Flow app is the companion app for Bosch eBike systems. It connects to eBikes via Bluetooth Low Energy (BLE) and provides:

- Real-time ride dashboard with telemetry (speed, power, cadence, battery)
- Bike configuration (assistance modes, display settings, light control)
- Anti-theft features (bike lock, theft alarm, crash detection, GPS tracking)
- Turn-by-turn navigation with Mapbox
- Activity tracking and ride history
- Firmware over-the-air (FOTA) updates for all bike components
- Subscription management (Flow Plus premium features)
- Third-party integrations (Strava, Komoot, Trek)

### App Identity

| Property | Value |
|---|---|
| Package name | `com.bosch.ebike.onebikeapp` |
| App label | `@string/general_appName` (Bosch eBike Flow) |
| Min SDK | 26 (Android 8.0) |
| Target SDK | 36 (Android 16) |
| Version | 1.34.6 (build 1125) |
| Theme | `@style/Theme.Flow` |
| Application class | `com.bosch.ebike.onebikeapp.App` |
| Main activity | `com.bosch.ebike.onebikeapp.MainActivity` (single-activity) |

### Repository Layout

```
android-app/
  com.bosch.ebike.onebikeapp_1.34.6-1125_...apk   # Original split APK from APKMirror
  com.bosch.ebike.onebikeapp_1.34.6-1125/          # Initial extraction (split APKs)
  extracted/base.apk                                # Extracted base APK
  decompiled-base/                                  # apktool decompilation of base.apk
    AndroidManifest.xml
    apktool.yml
    assets/
    res/
    smali/               # Dex 1 (10,088 files: AndroidX, coroutines, root classes)
    smali_classes2/      # Dex 2 (12,858 files: core Bosch modules)
    smali_classes3/      # Dex 3 (12,083 files: BLE comm, BES3 protobuf, navigation)
    smali_classes4/      # Dex 4 (14,124 files: riding, antitheft, messagebus, FOTA)
    smali_classes5/      # Dex 5 (7,816 files: BES3 protobuf continuation)
    smali_classes6/      # Dex 6 (7,673 files: third-party libs, BES3 continuation)
    smali_classes7/      # Dex 7 (1,517 files: BES3 protobuf final)
```

Total: ~76,159 smali files across 7 dex files.

### How to Navigate Smali Code

Smali is a human-readable representation of Android DEX bytecode. Key patterns:

- **Class files**: `ClassName.smali` -- each Java/Kotlin class is one file
- **Inner classes**: `OuterClass$InnerClass.smali`
- **Lambda/synthetic**: `ClassName$$ExternalSyntheticLambda0.smali`
- **Kotlin file facades**: `FileNameKt.smali` (top-level functions from a Kotlin file)
- **Companion objects**: `ClassName$Companion.smali`
- **Sealed/enum variants**: `SealedClass$VariantName.smali`

Common smali instructions:
- `invoke-virtual`, `invoke-interface`, `invoke-static` -- method calls
- `iget-object`, `sget-object` -- field access
- `new-instance`, `const-string`, `const/4` -- object/string creation
- `.field public` / `.field private` -- field declarations
- `.method public` / `.method private` -- method declarations

### Reading Order

We recommend reading the docs in this order:

1. [Architecture Overview](architecture.md) -- high-level system design
2. [BLE Communication](ble-communication.md) -- how the app talks to the bike
3. [Backend & API](backend-api.md) -- cloud services and authentication
4. [Data Layer](data-layer.md) -- local storage and repositories
5. [UI & Navigation](ui-navigation.md) -- screens, fragments, and design system
6. [Feature Modules](feature-modules.md) -- deep dives into major features
7. [Module Catalog](module-catalog.md) -- complete listing of all ~100 modules

## Key Technologies

| Layer | Technology |
|---|---|
| Language | Kotlin (compiled to JVM bytecode) |
| UI | Hybrid: XML Layouts + Jetpack Compose (mid-migration) |
| Navigation | Jetpack Navigation Component (Fragment-based, 80+ nav graphs) |
| DI | Koin |
| Networking (new) | Ktor + Ktorfit |
| Networking (legacy) | OkHttp + Retrofit |
| Serialization | kotlinx.serialization, Gson, Protobuf |
| Auth | AppAuth (OAuth2/OIDC against Bosch Keycloak) |
| Database | Room (4 separate databases) |
| BLE | Android BluetoothLeScanner + custom GATT wrapper |
| Maps | Mapbox SDK (maps + navigation) |
| Image loading | Coil |
| Analytics | Firebase Analytics, Adjust |
| Crash reporting | Firebase Crashlytics |
| Push notifications | Firebase Cloud Messaging |
| Billing | Google Play Billing Library 8.0.0 |

## Environment Configuration

The app supports 4 backend environments, selected by the APK's release category:

| Release Category | Environment | Auth Server |
|---|---|---|
| 1 | STAGE | `p8.authz.bosch.com` |
| 2 | QA | `p10.authz.bosch.com` |
| 3 | QA | `p10.authz.bosch.com` |
| 4 | PRODUCTION | `p9.authz.bosch.com` |
| (dev) | DEV | `p4.authz.bosch.com` |

All API base URLs follow the pattern: `https://{service}.{env}.connected-biking.cloud/`

See [Backend & API](backend-api.md) for the full list of 23+ service URLs.

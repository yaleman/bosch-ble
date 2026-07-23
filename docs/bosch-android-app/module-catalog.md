# Module Catalog

Complete listing of all ~100 feature modules in the Bosch eBike Flow app, organized by domain area.

## Module Legend

| Symbol | Meaning |
|---|---|
| **DS** | datasources/ sub-package |
| **SVC** | services/ sub-package |
| **V** | views/ sub-package |
| **M** | model/ sub-package |

---

## Infrastructure & Core

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `onebikeapp` | 83 | 4 | flat | Application class, MainActivity, MainViewModel, Koin modules |
| `appcore` | 3,444 | 2 | DS, SVC, V, M | Core bike/rider logic, component models, use cases |
| `app` | 17 | 2 | extension/ | App extensions framework |
| `common` | 128 | 3 | DS, extensions, file, permission, storage, units, utils, V | Shared utilities |
| `commonui` | 215 | 3 | compose, extension, navigation, playstore, span | Shared UI components |
| `commonworkmanager` | 3 | 3 | flat | WorkManager utilities |
| `coroutineutils` | 19 | 3 | flat | Coroutine utilities |
| `flowutils` | 27 | 3 | flat | Kotlin Flow extensions |
| `initializers` | 19 | 3 | flat | Koin/WorkManager initialization |
| `logging` | 32 | 4 | extension/ | Logging framework |
| `sendlogs` | 14 | 4 | flat | Log export/sharing |
| `cleanuplogs` | 11 | 3 | flat | Log cleanup |
| `localization` | 9 | 4 | flat | Localization utilities |
| `securestore` | 17 | 4 | flat | AES encryption, secure storage |
| `serialization` | 3 | 4 | protobuf/ | Protobuf serialization |
| `repository` | 5 | 4 | flat | Generic CachedApiRepository |
| `nativeinteroperability` | 6 | 4 | coroutines/, storage/ | Kotlin/Native interop |
| `kmpdatastore` | 2 | 3 | flat | Kotlin Multiplatform DataStore |

## BLE & Communication

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `ble` | 76 | 3 | companiondevice/, wrapper/ | Low-level GATT wrapper, Companion Device Manager |
| `bluetoothcommunication` | 150 | 3 | config/, connection/, DS, errors, internal/ | GATT connection, config interfaces |
| `communicationstack` | 196 | 3 | flat | Binary protocol, message encoding/decoding |
| `messagebus` | 1,056 | 4 | constants/, errors, gateway/, internal/, logging/, message/ | Typed DataPoint API for bike components |
| `messagebusmock` | 141 | 4 | flat | Mock MessageBus for testing |
| `mcsp` | 85 | 4 | internal/ | MCSP GATT config |
| `transporter` | 9 | 4 | flat | Packet transport layer |
| `largebinarytransport` | 111 | 3 | message/, server/ | Chunked binary transfer for FOTA |
| `pocketmode` | 130 | 4 | SVC/ | Background auto-reconnection |
| `blecomponentpairingservices` | 14 | 3 | flat | BLE component pairing logic |
| `blecomponentpairingviews` | 273 | 3 | flat | BLE component pairing UI |
| `communication` | 13 | 3 | analytics/ | Communication analytics |
| `bcmlivedata` | 257 | 3 | cloud/, management/, providers/, SVC/ | BCM (Connect Module) live data |
| `bcmservices` | 108 | 3 | debugviews/ | BCM services |

## Bike Data & Protocol

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `bes3` | ~3,163 | 3-7 | messagebus/ | Protobuf data model for all bike data |
| `datamodel` | 23 | 3 | mobileapp/ | Mobile app data model |
| `fielddata` | 18 | 3 | generated/ | Field data protobuf |
| `backend` | 5 | 2 | flat | Protobuf telemetry ingestion format |
| `featurestreamingservice` | 118 | 3 | datapoints/, distractingalert/ | Real-time feature data streaming |

## Bike Management

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `bikepairing` | 558 | 3 | SVC/, V/ | Bike pairing flow |
| `bikeconnection` | 44 | 3 | V/ | Bike connection UI |
| `bikesettings` | 1,382 | 3 | bikename/, SVC/, V/ | Bike configuration |
| `bikepass` | 483 | 3 | DS, SVC/, V/ | Digital bike pass |
| `bikesharing` | 506 | 3 | DS, SVC/, V/ | Bike sharing integration |
| `bikespec` | 96 | 3 | DS, SVC/, V/ | Bike specifications |
| `bikevisual` | 85 | 3 | SVC/, V/ | Bike visual rendering |
| `bikename` | 25 | 3 | SVC/ | Bike name management |
| `bikecontentfilesuploader` | 32 | 3 | upload/ | Bike content file upload |
| `bike` | 11 | 3 | diagnostic/ | Bike diagnostic |
| `diagnostic` | 36 | 3 | SVC/ | Diagnostic services |
| `componentvisual` | 11 | 3 | V/ | Component visual rendering |
| `componentsassets` | 1 | 3 | flat | Component drawable resources |
| `partsid` | 17 | 4 | V/ | Parts ID display |

## Riding & Activity

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `riding` | 1,677 | 4 | analytics, DS, eshift/, options/, SVC/, snail/, V/, walkassist/ | Main ride screen and logic |
| `ridestarttracking` | 16 | 4 | flat | Ride start detection |
| `stopriding` | 34 | 4 | SVC/, V/ | Ride stop flow |
| `activitytracking` | 1,201 | 2 | DS, locationfilters/, M/, optionspanel/, provider/, SVC/, settings/, V/ | Ride recording and upload |
| `activitystatistics` | 662 | 2 | DS, overview/, SVC/, V/ | Ride statistics and history |
| `range` | 130 | 4 | V/ | Range estimation display |
| `erange` | 318 | 3 | library/, SVC/ | eRange range estimation |
| `autowakeup` | 39 | 2 | SVC/ | Auto-wake bike on app open |

## Anti-Theft & Security

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `antitheft` | 3,352 | 2 | DS, SVC/, V/ | Bike lock, theft detection, crash detection, alarm |
| `stolenmarker` | 27 | 4 | generated/ | Mark bike as stolen |

## Firmware Updates (FOTA)

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `fota` | 1,422 | 3 | DS, report/, SVC/, systemtest/, V/ | Firmware over-the-air updates |

## Navigation & Maps

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `navigation` | 1,708 | 4 | analytics/, common/, DS, debug/, favoritelocations/, SVC/, V/ | Turn-by-turn navigation |
| `route` | 554 | 4 | DS, V/ | Route display and management |
| `routeservice` | 267 | 4 | api/, config/, gpx/, M/, myroutes/, name/, routplanning/, save/, simulation/, testing/, usecase/, userspecificspeed/, waypoints/ | Route planning service |
| `routing` | 134 | 4 | api/, M/, utils/ | Route calculation |
| `trailnavigation` | 695 | 4 | clipping/, config/, display/, engine/, mapentityextractor/, mapentityprovider/, M/, platform/, positionextrapolation/, SVC/, session/, utils/ | Trail navigation |
| `map` | 351 | 4 | camera/, chooseLocation/, databinding/, extensions/, flowrouteline/, layers/, line/, mapcomponents/ | Mapbox map components |
| `onebikemap` | 18 | 4 | marker/ | Map markers |
| `mapboxvectortiles` | 48 | 4 | decoder/ | Vector tile decoder |
| `location` | 3 | 4 | flat | Location utilities |
| `locationservices` | 35 | 4 | flat | Location services |
| `locationpermissionservices` | 4 | 4 | internal/ | Location permission handling |
| `backgroundlocationpermissionservices` | 5 | 2 | internal/ | Background location permission |

## Display & Configuration

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `displayconfiguration` | 81 | 3 | V/ | Display configuration |
| `stripeconfigurationdatasources` | 18 | 4 | localstore/ | Display stripe data |
| `stripeconfigurationservices` | 109 | 4 | deviceselection/, multiplatformsupport/ | Display stripe logic |
| `stripeconfigurationviews` | 383 | 4 | composeui/ | Display stripe UI |
| `appcoredisplayconfiguration` | 18 | 2 | flat | ViewStripe models |
| `configurationcontainer` | 103 | 3 | service/ | Configuration container |
| `config` | 16 | 3 | flat | Remote config |
| `configuration` | 7 | 3 | production/ | Production configuration |

## User & Auth

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `authentication` | 177 | 2 | commonui/, DS, logoutcleanup/, SVC/, V/ | OAuth2 login, token management |
| `accessmanagement` | 45 | 2 | generated/, util/ | Access control |
| `ownership` | 315 | 4 | DS, V/ | Bike ownership management |
| `ownershipreset` | 156 | 4 | SVC/, V/ | Ownership reset flow |
| `ownerships` | 60 | 4 | generated/ | Ownership data models |
| `userregistration` | 117 | 4 | V/ | User registration flow |
| `usersettings` | 350 | 4 | DS, SVC/, V/ | User settings |
| `userinfodatapoint` | 15 | 4 | provider/ | User info data points |
| `termsandconditions` | 555 | 4 | DS, SVC/, V/ | T&C acceptance |
| `onboarding` | 7 | 4 | DS/ | Onboarding flow |

## Commerce & Subscriptions

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `subscription` | 768 | 4 | billing/, DS, SVC/, V/ | Flow+ subscription management |
| `promotions` | 507 | 4 | bcmretrofit/, DS, flowplus/, SVC/, V/ | Promotions and upselling |
| `flowplusreseller` | 92 | 3 | DS, SVC/ | Flow+ reseller codes |
| `performanceupgrade` | 274 | 4 | DS, M/, SVC/, V/ | Performance upgrade purchases |
| `dealermap` | 189 | 3 | DS, SVC/, V/ | Dealer locator map |
| `favouritedealer` | 76 | 3 | DS, SVC/, V/ | Favorite dealers |
| `oem` | 201 | 4 | DS, M/, SVC/, V/ | OEM theming and branding |

## Content & Help

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `home` | 2,412 | 3 | DS, SVC/, V/ | Home dashboard |
| `actionablecards` | 115 | 2 | DS, SVC/, V/ | Actionable cards |
| `contentcards` | 59 | 3 | DS, M/, SVC/, V/ | Content cards |
| `apphighlights` | 99 | 2 | SVC/, V/ | App feature highlights |
| `connectionassistant` | 164 | 3 | V/ | Connection troubleshooting |
| `legacyconnectionassistant` | 94 | 4 | V/ | Legacy connection assistant |
| `ledremoteonboarding` | 337 | 4 | dialog/, V/ | LED remote onboarding |
| `guidedHelp` | 40 | 3 | SVC/ | Guided help |
| `guidedhelp.1` | 162 | 3 | onboarding/, SVC/ | Guided help (new) |
| `guidedhelpdebug` | 10 | 3 | V/ | Guided help debug |
| `helpFeedback` | 9 | 3 | SVC/, V/ | Help and feedback |
| `helpfeedback.1` | 235 | 3 | DS, SVC/, V/ | Help and feedback (new) |
| `servicebook` | 221 | 4 | common/, DS, SVC/, systemtest/, V/ | Service history book |

## Third-Party Integrations

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `thirdparty` | 346 | 4 | SVC/, V/ | Strava, Komoot, Trek integrations |
| `deutschedienstrad` | 9 | 3 | SVC/ | Deutsche Dienstrad integration |

## Analytics & Telemetry

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `analytics` | 59 | 2 | adjust/, composition/, firebase/, firmwarestatustracking/, internal/, testing/ | Analytics framework |
| `analyticsbikecommunication` | 32 | 2 | internal/ | Bike communication analytics |
| `analyticsbikeperformancetracking` | 11 | 2 | internal/ | Bike performance tracking |
| `onebikeanalytics` | 508 | 4 | 20+ sub-packages | Per-feature analytics tracking |
| `adjust` | 19 | 2 | initializer/ | Adjust SDK initialization |
| `adjustanalytics` | 10 | 2 | flat | Adjust analytics events |
| `appstarttracking` | 11 | 2 | flat | App start tracking |
| `abtesting` | 6 | 2 | SVC/ | A/B testing |
| `featureflags` | 4 | 3 | flat | Feature flags |

## Push Notifications

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `pushnotifications` | 154 | 4 | internal/, M/ | Firebase push notifications |

## Graphs & Charts

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `graph` | 46 | 3 | darkcharts/, databinding/, elevation/, formatter/, graphproviders/ | Chart/graph rendering |

## HTTP & Networking

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `httprest` | 90 | 3 | flat | HTTP clients (Ktor + OkHttp), interceptors |
| `cloudsync` | 182 | 3 | generated/ | Cloud sync DTOs (JSON:API) |

## Measurement & Units

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `measurement` | 14 | 4 | flat | Unit types |
| `unitsformatting` | 1 | 4 | flat | Unit formatting |

## Debug & Testing

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `debug` | 89 | 3 | DS/ | Debug tools |
| `debugapp` | 3 | 3 | launcher/ | Debug app launcher |
| `testerinterface` | 3 | 4 | SVC/ | Factory test interface |

## Misc

| Module | Files | Dex | Sub-packages | Purpose |
|---|---|---|---|---|
| `apprating` | 48 | 2 | DS, SVC/ | App store rating prompt |
| `customtabs` | 8 | 3 | flat | Chrome Custom Tabs |
| `datasources` | 8 | 3 | gettingstartedcards/ | Getting started cards |
| `optionspanel` | 60 | 4 | api/, internal/ | Options panel framework |
| `textreference` | 6 | 4 | flat | Text references |
| `util` | 2 | 4 | flat | General utilities |
| `utils` | 14 | 4 | time/ | Time utilities |
| `extensions` | 1 | 3 | flat | Kotlin extensions |
| `navgraphids` | 1 | 4 | flat | Navigation graph IDs |
| `stopriding` | 34 | 4 | SVC/, V/ | Ride stop flow |
| `appstarttracking` | 11 | 2 | flat | App start tracking |
| `services` | 53 | 4 | gettingstartedcards/, ownership/ | General services |
| `designsystem` | 701 | 3 | compose/, databinding/, DS, v2/ | Design system (v1 + v2) |

---

## Module Count Summary

| Domain Area | Module Count | Total Files |
|---|---|---|
| Infrastructure & Core | 18 | ~4,200 |
| BLE & Communication | 14 | ~2,200 |
| Bike Data & Protocol | 5 | ~3,300 |
| Bike Management | 14 | ~3,400 |
| Riding & Activity | 8 | ~4,100 |
| Anti-Theft & Security | 2 | ~3,400 |
| Firmware Updates | 1 | ~1,400 |
| Navigation & Maps | 12 | ~4,000 |
| Display & Configuration | 7 | ~700 |
| User & Auth | 10 | ~1,800 |
| Commerce & Subscriptions | 7 | ~2,000 |
| Content & Help | 13 | ~3,900 |
| Third-Party | 2 | ~350 |
| Analytics & Telemetry | 9 | ~700 |
| Push Notifications | 1 | ~150 |
| Graphs & Charts | 1 | ~50 |
| HTTP & Networking | 2 | ~270 |
| Measurement & Units | 2 | ~15 |
| Debug & Testing | 3 | ~90 |
| Misc | 14 | ~200 |
| **Total** | **~100** | **~76,000** |

---

## Module Dependencies (Key Relationships)

```
onebikeapp (root)
  ├─ appcore (bike/rider models)
  │    ├─ bikepairing
  │    ├─ bikesettings
  │    └─ bikepass
  ├─ messagebus (BLE data API)
  │    ├─ communicationstack (protocol)
  │    │    ├─ bluetoothcommunication (GATT)
  │    │    └─ ble (wrapper)
  │    ├─ riding
  │    ├─ antitheft
  │    ├─ fota
  │    └─ bikesettings
  ├─ bes3 (protobuf models)
  │    ├─ cloudsync (DTOs)
  │    ├─ activitytracking
  │    └─ messagebus
  ├─ authentication
  │    ├─ httprest (API clients)
  │    └─ cloudsync
  ├─ navigation
  │    ├─ map (Mapbox)
  │    ├─ route
  │    └─ routeservice
  ├─ subscription
  │    ├─ antitheft (gated features)
  │    └─ promotions
  └─ home (dashboard)
       ├─ actionablecards
       ├─ contentcards
       └─ apphighlights
```

## Further Reading

- [Architecture Overview](architecture.md) -- High-level system design
- [Feature Modules](feature-modules.md) -- Deep dives into major features
- [BLE Communication](ble-communication.md) -- How the app talks to the bike

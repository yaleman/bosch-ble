# UI & Navigation

The Bosch eBike Flow app uses a **single-activity architecture** with Jetpack Navigation Component. The UI is in an active migration from XML layouts to Jetpack Compose, resulting in a hybrid approach.

## Activity Architecture

### Single Activity

The app has one `AppCompatActivity`:

| Property | Value |
|---|---|
| Class | `com.bosch.ebike.onebikeapp.MainActivity` |
| Layout | `res/layout/activity_main.xml` |
| Orientation | Portrait (locked) |
| Soft input | `adjustPan` |

**Layout:** A single `FragmentContainerView` hosting a `NavHostFragment`:

```xml
<FragmentContainerView
    android:id="@+id/navHostFragment"
    android:name="androidx.navigation.fragment.NavHostFragment"
    app:navGraph="@navigation/global_nav_graph"
    app:defaultNavHost="true" />
```

### Deep Link Receiver

`DeepLinkReceiverActivity` handles all deep links and forwards them to `MainActivity`:

**Key file:** `smali_classes4/com/bosch/ebike/onebikeapp/DeepLinkReceiverActivity.smali`

**Supported deep link schemes:**
- `onebikeapp://` -- Internal app navigation
- `onebike://` -- Legacy scheme
- `flowApp://` -- Feature-specific navigation
- `https://flow.bosch-ebike.com/` -- Web deep links
- Bosch help center URLs
- Bike sharing URLs

## Navigation Graph Structure

### Root Graph

**File:** `res/navigation/global_nav_graph.xml`

The root graph includes **80+ sub-navigation graphs**. Start destination is `splash_nav_graph`.

### Key Navigation Graphs

| Graph | Purpose |
|---|---|
| `splash_nav_graph` | Initial loading, routes to auth/home/pairing |
| `auth_login_nav_graph` | Login flow |
| `auth_signup_nav_graph` | Signup flow |
| `auth_logout_nav_graph` | Logout flow |
| `terms_and_conditions_nav_graph` | T&C, profile setup, analytics consent |
| `main_nav_graph` | Main app shell (start: `NavBarFragment`) |
| `nav_bar_nav_graph` | Bottom navigation tabs |
| `bike_pairing_nav_graph` | Bike pairing flow |
| `riding_nav_graph` | Riding screen |
| `route_planning_nav_graph` | Route planning |
| `subscription_nav_graph` | Flow+ subscription |

### Bottom Navigation (4 Tabs)

**File:** `res/navigation/nav_bar_nav_graph.xml`

| Tab | Fragment | Purpose |
|---|---|---|
| Home | `HomeFragment` | Main dashboard with cards |
| Profile | `ProfileFragment` | User settings |
| Planning | Routes to `route_planning_nav_graph` | Map-based route planning |
| Activity | Routes to `activity_summaries_list_nav_graph` | Ride history |

### Navigation Helpers

**Screen transitions:**
- `smali_classes3/com/bosch/ebike/commonui/navigation/ScreenTransitionsKt.smali`
- Pre-built `NavOptions` for horizontal/vertical slides with standard animations

**WebView navigation:**
- `smali_classes3/com/bosch/ebike/commonui/navigation/WebViewNavOptionsKt.smali`
- Navigation options for WebView screens

## UI Framework: Hybrid XML + Compose

The app is mid-migration from XML to Jetpack Compose.

### XML-Based Screens

Older and more complex screens use XML layouts with ViewBinding:

**Examples:**
- `RoutePlanningFragment` -- Uses `FragmentRoutePlanningBinding`
- `DealerMapFragment` -- Uses `FragmentDealerMapBinding`
- `NavBarFragment` -- Uses `FragmentNavBarBinding`

### Compose-Based Screens

Newer and simpler screens use Jetpack Compose via a base class:

**Base class:** `smali_classes3/com/bosch/ebike/common/views/ComposeFragment.smali`

```kotlin
abstract class ComposeFragment : Fragment() {
    override fun onCreateView(inflater, container, savedInstanceState): View {
        return ComposeView(requireContext()).apply {
            setContent {
                FlowTheme {
                    Content()
                }
            }
        }
    }
    
    @Composable
    abstract fun Content()
}
```

**Examples of fully-Compose fragments:**
- `IssuesFragment`
- `IssueDetailsFragment`
- `ThirdPartyFragment`
- `CommunicationSettingsFragment`
- `ServiceBookFragment`
- `RangeControlIntroductionFragment`
- `RoutesListFragment`
- `PerformanceUpgrade*Fragment`
- `LedRemote*Fragment`
- `BikeNotConnectedFragment`

### Hybrid Screens

Some XML-based fragments embed `ComposeView` for specific sub-components:

**Example:** `RoutePlanningFragment` has 10+ ComposeView overlays for dialogs, map overlays, and banners.

### Bottom Navigation Bar

The bottom navigation bar itself is a ComposeView embedded in the XML-based `NavBarFragment`:

```kotlin
// In NavBarFragment
binding.bottomNavigationBar.apply {
    setContent {
        FlowTheme {
            BottomNavigationBar(...)
        }
    }
}
```

## Design System

The app has two generations of design system components.

### v1 (XML/Custom Views)

**Location:** `smali_classes3/com/bosch/ebike/designsystem/`

Custom View components:
- `FlowContextualBanner`
- `FlowSpinner`
- `FlowSpinnerButton`
- `FlowChecklistItemView`

ViewBinding-based layouts for preferences, lists, and checklists.

### v2 (Jetpack Compose)

**Location:** `smali_classes3/com/bosch/ebike/designsystem/v2/`

The active design system, fully Compose-based.

#### Theme

**File:** `smali_classes3/com/bosch/ebike/designsystem/v2/theme/FlowThemeKt.smali`

`FlowTheme` wraps Material3's `MaterialTheme` via `CompositionLocalProvider`:

```kotlin
@Composable
fun FlowTheme(
    content: @Composable () -> Unit
) {
    val colors = if (isSystemInDarkTheme()) ColorsDark else ColorsLight
    CompositionLocalProvider(
        LocalFlowColors provides colors,
        LocalFlowTypography provides Typography,
        LocalFlowShapes provides Shapes,
        LocalFlowSpacings provides Spacings,
        // ... other tokens
    ) {
        MaterialTheme(content = content)
    }
}
```

#### Design Tokens

**Colors:**
- `FlowColors` interface with semantic tokens
- `ColorsLight` and `ColorsDark` implementations
- Tokens: `accentBgPrimary`, `neutralFgPrimary`, `errorFgOnPrimary`, etc.

**Typography:**
- `FlowTypography` -- Custom typography scale
- Based on Material3 typography

**Shapes:**
- `FlowShapes` -- Custom shape definitions
- `FlowShapeSize` -- Size variants
- `ShapeSize` -- Enum: ExtraSmall, Small, Medium, Large, ExtraLarge

**Spacing:**
- `FlowSpacings` -- Spacing scale
- `Spacings` -- Named spacing values
- `FlowLayoutMargin` -- Layout margins
- `FlowBorderWidth` -- Border widths

**Other tokens:**
- `FlowShadow` -- Shadow definitions
- `FlowOpacity` -- Opacity values
- `FlowTouchTarget` -- Touch target sizes
- `FlowIconSize` -- Icon sizes
- `TextCase` -- Text case transformations

#### Components

**Location:** `smali_classes3/com/bosch/ebike/designsystem/v2/view/`

18 component categories:

| Category | Components |
|---|---|
| `badge/` | `FlowBadge`, `FlowConnectionBadge`, `FlowAssistModeBadge` |
| `banner/` | `FlowContextualBanner` |
| `button/` | `FlowPrimaryButton`, `FlowSecondaryButton`, `FlowGhostButton`, `FlowIconButton`, `FlowFloatingActionButton`, `FlowExtendedFloatingActionButton` |
| `dialog/` | `FlowDialog` |
| `input/` | `FlowTextField`, `FlowSelectionField` |
| `link/` | `FlowLink` |
| `listitem/` | `FlowListItem` |
| `menu/` | `FlowMenu` |
| `pageview/` | `FlowPagerIndicator` |
| `progress/` | `FlowProgressBar` |
| `selectioncontrol/` | `FlowCheckbox`, `FlowRadioButton`, `FlowSwitch` |
| `sheet/` | `FlowModalBottomSheet` |
| `slider/` | `FlowSlider` |
| `snackbar/` | `FlowSnackbar` |
| `tabs/` | `FlowTabs` |
| `template/` | `AccessibleModalTemplate`, `ImageTitleContentActionsTemplate` |
| `topappbar/` | `FlowTopAppBar` |
| `utils/` | Utility composables |

#### Style Variants

Each component has extensive style variants defined in `Style$*` hierarchy:

**Example:** `Style$Button` has variants:
- `Primary`
- `Secondary`
- `Ghost`
- `Icon`
- `FloatingAction`
- `ExtendedFloatingAction`

## Main Screens

### Splash Screen

Initial loading screen that routes to:
- Auth flow (if not logged in)
- Home screen (if logged in)
- Bike pairing (if no bike registered)

### Authentication Screens

**Login flow:**
1. Splash → Login screen
2. User enters credentials
3. App opens browser to Keycloak
4. User authenticates
5. Keycloak redirects back to app
6. App exchanges code for tokens
7. Routes to home or onboarding

**Signup flow:**
1. Splash → Signup screen
2. User enters email
3. App opens browser to Keycloak registration
4. User completes registration
5. Keycloak redirects back to app
6. Routes to onboarding

### Onboarding Screens

**File:** `res/navigation/terms_and_conditions_nav_graph.xml`

1. Terms & Conditions acceptance
2. Profile setup (name, weight, height)
3. Analytics consent
4. Bike pairing

### Home Screen (Dashboard)

**File:** `smali_classes3/com/bosch/ebike/home/`

Main dashboard with cards:
- Battery info (SoC, range)
- Maintenance reminders
- Mileage stats
- Tracking mode status
- Getting started cards
- Bike issues
- App highlights
- Promotions (Flow+, PowerMore, Komoot, BCM)

### Riding Screen

**File:** `smali_classes4/com/bosch/ebike/riding/`

Live ride screen with:
- Map view (Mapbox)
- Speed, power, cadence metrics
- Assist mode selector
- Battery info
- Navigation instructions (if active)
- Heart rate (if sensor connected)
- Walk assist controls
- eShift controls (if equipped)

### Route Planning Screen

**File:** `smali_classes4/com/bosch/ebike/route/`

Map-based route planning with:
- Mapbox map
- Destination search
- Favorite locations
- Route options (avoid highways, tolls)
- Elevation profile
- Turn-by-turn navigation

### Activity Statistics Screen

**File:** `smali_classes3/com/bosch/ebike/activitystatistics/`

Ride history with:
- List of past rides
- Ride details (map, metrics, elevation)
- Statistics (distance, time, elevation gain)
- Export to GPX

### Bike Settings Screen

**File:** `smali_classes3/com/bosch/ebike/bikesettings/`

Bike configuration:
- Assistance modes (customize levels)
- Ride settings (light, walk assist)
- Bike info (name, components)
- Communication settings
- Display configuration

### Anti-Theft Screen

**File:** `smali_classes2/com/bosch/ebike/antitheft/`

Security features:
- Bike lock/unlock
- Theft detection onboarding
- Crash detection settings
- Mark as stolen
- Insurance info
- Parking location

### FOTA Screen

**File:** `smali_classes3/com/bosch/ebike/fota/`

Firmware updates:
- Check for updates
- Download firmware
- Transfer to bike
- Installation progress
- Release notes

### Subscription Screen

**File:** `smali_classes4/com/bosch/ebike/subscription/`

Flow+ subscription:
- Feature details
- Plan selection (monthly/yearly)
- Pricing
- Purchase flow
- Success confirmation

## OEM Theming

The app supports per-OEM theme customization.

**Key files:**
- `smali_classes4/com/bosch/ebike/oem/` -- OEM theme services
- `res/navigation/oem_theme_preview` -- Theme preview graph

OEMs can customize:
- Colors
- Logos
- App name
- Splash screen
- Navigation bar theme

## Accessibility

The app includes accessibility features:

**Key files:**
- `smali_classes3/com/bosch/ebike/commonui/compose/AccessibleModalTemplate.smali`
- Accessibility helpers in `commonui/`

Features:
- Content descriptions for all interactive elements
- Touch target sizes meet WCAG guidelines
- Screen reader support
- High contrast mode support

## Animations

Standard animations defined in `res/anim/`:
- `anim_flow_slide_in_right`
- `anim_flow_slide_out_left`
- `anim_flow_slide_in_left`
- `anim_flow_slide_out_right`

Used via `ScreenTransitionsKt` for navigation transitions.

## Further Reading

- [Architecture Overview](architecture.md) -- High-level system design
- [Feature Modules](feature-modules.md) -- Deep dives into major features
- [Module Catalog](module-catalog.md) -- Complete module listing

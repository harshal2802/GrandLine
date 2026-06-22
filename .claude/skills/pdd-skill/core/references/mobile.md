# PDD Reference: Mobile Projects

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for mobile projects (iOS native, Android native, React Native, Flutter, Expo, and related stacks).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Native (Swift/Kotlin), cross-platform (React Native, Flutter), or managed (Expo)?
- Target platforms: iOS only, Android only, or both?
- Minimum OS versions supported? (iOS 16+, Android 10+, etc.)
- How is the app distributed? (App Store, Google Play, enterprise, TestFlight)
- Is there an existing backend / API? (URL, auth method, SDK)
- How is offline support handled? (local DB, cache, sync strategy)
- Are there device permissions required? (camera, location, notifications, biometrics)
- Any platform-specific features? (widgets, deep links, push notifications, in-app purchases)

### Extended `pdd/context/project.md` sections for mobile

```markdown
## Platform targets
- iOS: minimum version
- Android: minimum API level
- Distribution: App Store / Google Play / enterprise / TestFlight

## Offline & sync
- Local storage: (SQLite, Core Data, Room, AsyncStorage, MMKV)
- Sync strategy: (online-only / offline-first / background sync)
- Conflict resolution approach:

## Device features used
- Permissions required:
- Native modules / plugins:
- Push notifications: yes / no + provider

## Backend integration
- API base URL:
- Auth method:
- SDK or REST?
```

---

## Conventions Starter (Workflow 2)

```markdown
# Mobile Conventions

## Project structure
- Feature-based folder organization (not type-based)
- Each feature: screens/, components/, hooks/, services/
- Shared code in a top-level shared/ or common/ folder

## Naming
- Screens: PascalCase, suffixed with Screen (e.g. `UserProfileScreen`)
- Components: PascalCase
- Hooks: camelCase, prefixed with `use`
- Services: camelCase, suffixed with Service (e.g. `authService`)
- Constants: UPPER_SNAKE_CASE

## Navigation
- Stack navigator for hierarchical flows
- Tab navigator for peer-level sections
- Deep link routes documented in context/decisions.md
- No business logic in navigation handlers

## State management
- Local component state for UI-only state
- [Zustand / Redux / MobX / Provider — pick one] for shared app state
- Async state (loading/error/data) via React Query or similar

## Offline-first rules
- All API calls go through a service layer that handles retry and caching
- User-initiated actions must work offline with sync on reconnect
- Never block UI waiting for network — optimistic updates preferred

## Performance
- FlatList / RecyclerView for all long lists — never ScrollView with map()
- Images: always specify dimensions, use lazy loading
- Avoid anonymous functions in render — use useCallback for handlers passed to lists

## Platform differences
- Platform.OS checks isolated to a single platform utility file
- No platform-specific logic scattered in component files
- Platform-specific files use .ios.tsx / .android.tsx extensions
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New screen

```markdown
# Prompt: <ScreenName>

## Task
Create a <ScreenName> screen that <does what>.

## Navigation
- Accessible from: <parent screen or navigator>
- Params received: <param name and type>
- Navigates to: <child screens, if any>

## Data
- Source: <API endpoint / local store / props>
- Loading state: show skeleton / spinner
- Error state: show retry option
- Empty state: show <message or illustration>

## UI
- <describe layout and key elements>
- <any platform-specific behavior>

## Constraints
- Use existing navigation pattern (do not introduce new navigator)
- Follow component naming conventions
- Handle offline state — show cached data if available
```

### API integration / data sync

```markdown
# Prompt: <FeatureName> Data Sync

## Task
Implement data fetching and local caching for <feature> using <library/approach>.

## Data shape
<describe the API response structure>

## Behavior
- Fetch on mount and on pull-to-refresh
- Cache result locally for offline access
- Background sync every <N> minutes when app is active
- Show stale data with a "last updated" indicator while refreshing

## Constraints
- Use existing service layer pattern
- Do not make API calls directly from components
- Handle 401 (trigger re-auth) and 5xx (show retry) distinctly
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Platform correctness**
- [ ] Behavior tested on both iOS and Android (or scoped correctly)?
- [ ] Platform-specific UI conventions respected? (back button Android, swipe iOS)
- [ ] Safe area / notch / dynamic island handled?
- [ ] Keyboard avoidance behavior correct?

**Performance**
- [ ] FlatList (not ScrollView + map) for lists?
- [ ] Image dimensions specified?
- [ ] No heavy computation on the main thread (JS thread for RN)?
- [ ] useCallback / useMemo used where handlers are passed to list items?

**Offline / reliability**
- [ ] Graceful behavior when offline?
- [ ] Network errors handled with user-visible feedback?
- [ ] Retry logic in place for failed requests?

**Permissions**
- [ ] Permissions requested at the right moment (not on launch)?
- [ ] Graceful fallback if permission denied?
- [ ] Permission rationale shown before system prompt?

**App store readiness**
- [ ] No hardcoded strings (i18n-ready structure)?
- [ ] No test / debug code shipped?
- [ ] Deep links handled correctly?
- [ ] Crash-free — no unhandled promise rejections or uncaught exceptions?

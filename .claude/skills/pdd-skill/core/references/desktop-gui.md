# PDD Reference: Desktop / Native GUI

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for desktop application projects — native GUI apps built with Tauri, Electron, Flutter desktop, SwiftUI, Qt, .NET MAUI, WPF, or similar frameworks targeting macOS, Windows, and/or Linux.

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Framework (Tauri, Electron, Flutter, SwiftUI, Qt, .NET MAUI, WPF)?
- Target platforms (macOS, Windows, Linux — which subset)?
- Language (Rust, TypeScript, Dart, Swift, C++, C#)?
- Does it need native OS integrations (file system, tray, notifications, global shortcuts)?
- Single window or multi-window?
- Auto-update mechanism needed?
- Distribution channels (direct download, Mac App Store, Microsoft Store, Snap/Flatpak)?
- Offline-first or requires network connectivity?
- Accessibility requirements (screen reader support, keyboard navigation)?
- Does it process large files or datasets locally?

### Extended `pdd/context/project.md` sections for desktop / native GUI

```markdown
## Framework and Architecture
- Framework: (Tauri, Electron, Flutter, SwiftUI, Qt, .NET MAUI, WPF)
- Architecture: (main process + renderer, single-process, native bridge pattern)
- Language: (Rust, TypeScript, Dart, Swift, C++, C#)
- UI layer: (web-based renderer, native widgets, custom rendering engine)
- IPC model: (Tauri commands, Electron IPC, platform channels, COM)

## Target Platforms and OS Versions
- Platforms: (macOS, Windows, Linux — which subset)
- Minimum OS versions: (macOS 13+, Windows 10 21H2+, Ubuntu 22.04+)
- Architecture targets: (x64, arm64, universal binary)
- Platform-specific behavior: (what differs per OS — document explicitly)

## Window Model
- Window type: (single window, multi-window, tabbed interface)
- Modal dialogs: (native OS dialogs, in-app modals, sheets)
- Menu bar: (native menu bar, in-app menu, both)
- System tray: (tray icon, tray menu, minimize-to-tray)
- Title bar: (native, custom/frameless, hybrid with traffic lights/controls)

## Native OS Integration Points
- File system: (open/save dialogs, drag-and-drop, file associations, recent files)
- Notifications: (native push notifications, badge counts, notification center)
- Global shortcuts: (keyboard shortcuts that work when app is not focused)
- System tray: (tray icon, context menu, status updates)
- Deep links: (custom URL scheme, universal links)
- Clipboard: (text, images, custom types)
- OS events: (sleep/wake, display changes, theme changes, network changes)
- Accessibility: (screen reader announcements, keyboard navigation, focus management)

## Data Storage
- Local database: (SQLite, LevelDB, Realm, Core Data, file-based)
- Configuration: (OS-native preferences, JSON/TOML config file, registry on Windows)
- Secrets: (OS keychain — Keychain on macOS, Credential Manager on Windows, Secret Service on Linux)
- File paths: (XDG on Linux, ~/Library/ on macOS, %APPDATA% on Windows)
- Cache strategy: (OS cache directory, size limits, eviction policy)

## Auto-Update Strategy
- Update mechanism: (Tauri updater, electron-updater, Sparkle, WinSparkle, custom)
- Update channels: (stable, beta, canary)
- Update UX: (silent background, prompt user, mandatory for security patches)
- Delta updates: (full download vs binary diff)
- Rollback: (keep previous version, downgrade path)

## Code Signing and Notarization
- macOS: (Developer ID certificate, notarization with Apple, hardened runtime)
- Windows: (Authenticode code signing, EV certificate for SmartScreen, MSIX signing)
- Linux: (GPG signing for packages, AppImage signature)
- CI/CD integration: (where certificates live, how signing is automated)

## Distribution Pipeline
- macOS: (DMG, pkg installer, Mac App Store, Homebrew cask)
- Windows: (MSI, NSIS installer, Microsoft Store, MSIX, WinGet)
- Linux: (AppImage, deb, rpm, Snap, Flatpak, AUR)
- Auto-update server: (self-hosted, GitHub Releases, S3, framework-provided)

## Accessibility Compliance
- Level: (WCAG 2.1 AA, platform-native guidelines, Section 508)
- Screen reader support: (VoiceOver, NVDA/JAWS, Orca)
- Keyboard navigation: (full keyboard access, tab order, focus indicators)
- High contrast and scaling: (respects OS settings, custom themes)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Desktop / Native GUI Conventions

## Platform Behavior
- Respect OS conventions — native menu bar on macOS, system tray on Windows, XDG paths on Linux
- Never hardcode file paths — use platform-appropriate APIs (app_data_dir, home_dir, cache_dir)
- Follow each platform's HIG (Apple Human Interface Guidelines, Windows Design, GNOME HIG)
- Dark/light mode follows OS system preference by default — custom override is optional
- Handle DPI scaling correctly — never use fixed pixel sizes for layout

## Process Architecture
- Keep the main process lightweight — heavy computation goes in background threads or worker processes
- Never block the UI thread with synchronous I/O, network calls, or CPU-intensive work
- IPC between main and renderer (Electron/Tauri) must be typed and minimal — don't pass large payloads
- Validate all IPC messages from the renderer — treat it as an untrusted boundary (Electron/Tauri)
- Clean up child processes and file handles on app exit — handle SIGTERM, SIGINT, and OS shutdown events

## Window Management
- Remember window position, size, and state (maximized/minimized) across sessions
- Restore windows to the correct display — handle display disconnection gracefully
- Native menu bar is required on macOS — never replace it with an in-app hamburger menu
- Keyboard shortcuts must follow platform conventions (Cmd on macOS, Ctrl on Windows/Linux)
- Support standard window operations: minimize, maximize, close, full-screen (macOS)

## File System and Storage
- Platform-correct paths: ~/Library/Application Support/ (macOS), %APPDATA% (Windows), ~/.config/ or XDG (Linux)
- Store secrets in the OS keychain — never in plain-text config files
- Use atomic writes for config files — partial writes corrupt data on crash or power loss
- Respect OS file locking — check for locks before writing shared files
- Handle missing or corrupted config gracefully — fall back to defaults, don't crash

## Memory and Performance
- Target < 200MB RAM for typical desktop apps — users notice memory hogs
- Profile and fix memory leaks — desktop apps run for hours or days, not minutes
- For Electron/Tauri: manage renderer processes — don't leak hidden windows
- Lazy-load heavy resources (images, data files) — don't load everything at startup
- Measure and optimize cold start time — users expect < 3 seconds to first paint

## Distribution and Updates
- Code-sign all binaries — unsigned apps trigger security warnings and may not install
- macOS: notarize with Apple — mandatory since macOS 10.15 for apps distributed outside the App Store
- Windows: Authenticode signing — unsigned apps trigger SmartScreen warnings
- Auto-update must be non-destructive — verify download integrity, keep rollback path
- Test installation and updates on clean OS images — developer machines hide missing dependencies

## Accessibility
- All interactive elements must be keyboard-navigable — never require mouse
- Provide meaningful labels for screen readers — not just "Button 1"
- Respect OS accessibility settings (high contrast, reduced motion, increased text size)
- Test with VoiceOver (macOS), NVDA (Windows), and Orca (Linux)
- Focus management: dialogs trap focus, closing returns focus to trigger element
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New window or dialog

```markdown
# Prompt: <WindowName> window

## Task
Create a new <window type> (main window, dialog, sheet, preferences pane) for <feature>.

## Window Design
- Window type: <modal dialog, modeless window, sheet (macOS), preferences tab>
- Size: <fixed, resizable with min/max, responsive to content>
- Title bar: <native, custom/frameless, hybrid>
- Menu bar items: <new items to add, or N/A>

## Layout
- Component tree: <describe the UI hierarchy>
- Platform adaptations: <what differs on macOS vs Windows vs Linux>
- Keyboard shortcuts: <Cmd/Ctrl + key assignments>
- Tab order: <logical focus progression>

## State
- Window state: <position, size, open/closed — persisted across sessions?>
- Data binding: <what data drives this window, how does it update>
- IPC: <what messages does this window send/receive from the main process>

## Accessibility
- Screen reader labels: <for every interactive element>
- Keyboard navigation: <full tab order, arrow keys for lists/grids>
- Focus management: <what gets focus on open, where focus goes on close>

## Constraints
- Must follow platform HIG (native controls, standard shortcuts)
- Must work on all target platforms
- Must handle DPI scaling and dark/light mode
- No fixed pixel layouts — use responsive sizing

## Output format
- Window component/view implementation
- Menu bar additions (if any)
- IPC handlers (if any)
- Keyboard shortcut registrations
- Tests: renders correctly, keyboard navigation works, IPC messages handled
```

### Native OS integration

```markdown
# Prompt: <Integration> OS integration

## Task
Implement <native feature> (system tray, notifications, file associations, global shortcuts, deep links, drag-and-drop).

## Platform Behavior
- macOS: <expected behavior per Apple HIG>
- Windows: <expected behavior per Windows guidelines>
- Linux: <expected behavior per GNOME/KDE HIG, or N/A>

## API Layer
- Framework API: <Tauri command, Electron API, native module, FFI>
- Permissions: <what OS permissions are needed, how to request>
- Fallback: <behavior when feature is unsupported or permission denied>

## Integration Points
- Trigger: <what user action or app event triggers this feature>
- Lifecycle: <setup on app start, cleanup on quit, persist across sessions>
- IPC: <messages between main process and UI for this feature>

## Constraints
- Must degrade gracefully on platforms that don't support the feature
- Must not require elevated permissions unless absolutely necessary
- Must clean up resources on app exit (tray icons, shortcuts, listeners)
- Must handle OS permission denial without crashing

## Output format
- Native integration module (per platform if needed)
- IPC command/event definitions
- Permission request flow
- Fallback behavior implementation
- Tests: feature works on all platforms, handles permission denial, cleans up on exit
```

### Auto-update system

```markdown
# Prompt: Auto-update system

## Task
Implement auto-update for the desktop application across all target platforms.

## Update Mechanism
- Framework: <Tauri updater, electron-updater, Sparkle/WinSparkle, custom>
- Update server: <GitHub Releases, S3, self-hosted, framework-provided>
- Check frequency: <on startup, periodic interval, manual check>
- Channels: <stable only, or stable + beta + canary>

## Update Flow
- Check: <HTTP request to update server, compare versions>
- Download: <background download, progress indicator, pause/resume>
- Verify: <signature verification, checksum validation>
- Install: <restart required, hot-swap, install on next launch>
- Rollback: <keep previous version, automatic rollback on failure>

## UX
- Notification: <system notification, in-app banner, dialog>
- User control: <auto-install, prompt before install, skip this version>
- Progress: <download progress bar, install progress>
- Mandatory updates: <for critical security patches — force update flow>

## Code Signing
- macOS: <notarized update bundle, Sparkle DSA/EdDSA signature>
- Windows: <Authenticode-signed installer, NSIS/MSI>
- Linux: <GPG-signed AppImage, signed package>

## Constraints
- Updates must be cryptographically verified before installation
- Failed updates must not brick the app — rollback or keep current version
- Update check must not block app startup
- Must work behind corporate proxies (respect system proxy settings)
- Must handle metered connections (don't auto-download on cellular/metered)

## Output format
- Update checker service
- Download and verification module
- Install/restart logic per platform
- Update UI (notification, progress, restart prompt)
- Tests: version comparison, signature verification, rollback on failure, proxy support
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Platform correctness**
- [ ] App launches and renders correctly on all target platforms?
- [ ] Native menu bar used on macOS (no hamburger menus)?
- [ ] Keyboard shortcuts follow platform conventions (Cmd on macOS, Ctrl on Windows/Linux)?
- [ ] File paths use platform-correct locations (XDG on Linux, ~/Library/ on macOS, %APPDATA% on Windows)?
- [ ] Dark/light mode follows OS system preference?
- [ ] DPI scaling handled correctly — no blurry or clipped UI at non-100% scaling?
- [ ] OS events handled (sleep/wake, display change, theme change, network change)?

**Window management**
- [ ] Window position, size, and state persisted across sessions?
- [ ] Multi-display support — windows restore to correct display, handle disconnection?
- [ ] Modal dialogs block parent window correctly?
- [ ] Standard window operations work (minimize, maximize, close, full-screen)?
- [ ] Focus management correct — dialogs trap focus, closing restores focus?

**Native integration**
- [ ] System tray icon and menu work on all platforms?
- [ ] Native notifications work per platform?
- [ ] File associations and drag-and-drop work correctly?
- [ ] Global shortcuts register and unregister properly?
- [ ] Graceful behavior when OS permissions are denied (file access, notifications)?
- [ ] Resources cleaned up on app exit (tray icons, shortcuts, listeners)?

**Process architecture**
- [ ] UI thread never blocked by synchronous I/O or heavy computation?
- [ ] IPC messages between main and renderer are typed and validated?
- [ ] No leaked renderer/child processes?
- [ ] Proper shutdown sequence — all processes and file handles cleaned up?

**Distribution and signing**
- [ ] Code-signed and notarized (macOS) / signed (Windows) — installs without security warnings?
- [ ] Auto-update works end-to-end (check, download, verify, install, restart)?
- [ ] Update signature verification in place?
- [ ] Installer creates correct file associations, Start Menu / Dock entries?
- [ ] Uninstaller removes all app data (or offers to keep preferences)?

**Performance and resources**
- [ ] Memory usage within budget (< 200MB for typical apps)?
- [ ] No memory leaks during extended use (hours/days)?
- [ ] Cold start time acceptable (< 3 seconds to first paint)?
- [ ] Large file/dataset processing doesn't freeze the UI?

**Accessibility**
- [ ] All interactive elements keyboard-navigable?
- [ ] Screen reader labels on all controls (VoiceOver, NVDA, Orca)?
- [ ] Focus order is logical and complete?
- [ ] High contrast and increased text size settings respected?
- [ ] Reduced motion preference respected for animations?

**Platform store requirements** (if applicable)
- [ ] App meets Mac App Store review guidelines (sandbox, entitlements)?
- [ ] App meets Microsoft Store certification requirements?
- [ ] App meets Snap/Flatpak packaging requirements (confined permissions)?

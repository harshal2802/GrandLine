# PDD Reference: Game Development

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for game development projects (Unity, Unreal, Godot, Bevy, custom engines, and similar game frameworks targeting PC, console, mobile, or web platforms).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Engine / framework (Unity, Unreal, Godot, Bevy, custom)?
- Language (C#, C++, GDScript, Rust)?
- Target platforms (PC, console, mobile, web/WebGL)?
- Game genre and core loop?
- Multiplayer? If so, architecture (client-server, P2P, rollback netcode)?
- Art pipeline (2D sprites, 3D models, procedural)?
- Audio middleware (FMOD, Wwise, built-in)?
- Target frame rate and performance budget?

### Extended `pdd/context/project.md` sections for game development

```markdown
## Engine
- Engine and version:
- Build system and toolchain:
- Editor extensions or custom tooling:

## Core Game Loop
- Genre:
- Core loop description: (what the player does every 30 seconds / 5 minutes / session)
- Game states: (menu, gameplay, pause, cutscene, loading, etc.)

## Architecture
- Entity/component system: (ECS, scene graph, MonoBehaviour, Actor/Component, custom)
- State management approach: (FSM, behavior trees, blackboard, etc.)
- Scripting layer: (visual scripting, Lua, native only)

## Asset Pipeline
- Art style: (2D sprites, 3D models, pixel art, procedural)
- Asset formats: (FBX, glTF, PNG, Aseprite, custom)
- Import and processing pipeline:
- Streaming and LOD strategy:

## Networking
- Multiplayer model: (single-player, client-server, P2P, rollback netcode, none)
- Netcode library or framework:
- Tick rate and latency budget:
- Authority model: (server-authoritative, client-predicted, hybrid)

## Platform and Certification
- Target platforms:
- Certification requirements: (console TRC/XR, app store guidelines)
- Input methods: (keyboard/mouse, gamepad, touch, motion)
- Min spec and performance targets:

## Performance Budgets
- Target frame rate: (30 / 60 / 120 / uncapped)
- Frame time budget: (16.6ms for 60fps, 33.3ms for 30fps)
- Draw call budget:
- Memory budget: (RAM, VRAM)
- GC policy: (avoid per-frame allocations, pooling strategy)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Game Development Conventions

## Architecture
- Prefer composition over inheritance — use ECS or component patterns, not deep class hierarchies
- Keep game logic decoupled from rendering — logic should be testable without a running engine
- Use state machines or behavior trees for complex entity behavior, not nested if/else
- Separate data from behavior — components hold data, systems operate on it

## Performance
- Never allocate in hot paths (update loops, physics ticks, render callbacks)
- Use object pools for frequently spawned/destroyed objects (projectiles, particles, enemies)
- Profile before optimizing — measure frame time, draw calls, and memory, don't guess
- Keep per-frame GC pressure near zero — cache collections, reuse buffers, avoid boxing

## Asset Management
- All assets go through the pipeline — no raw files referenced at runtime
- Use asset bundles or addressables for streaming and memory control
- LOD everything that appears at variable distances — meshes, textures, audio
- Preload assets needed for the next scene during transitions, not on first use

## Input Handling
- Abstract input behind an action map — never hardcode key/button references
- Support rebinding for accessibility and platform portability
- Buffer inputs for action games — don't drop inputs between frames
- Handle multiple input methods (keyboard, gamepad, touch) through the same action layer

## Scene and Level Organization
- One scene/level per playable area — keep scenes small and composable
- Use additive loading for shared systems (UI, audio, managers)
- Persistent data (player state, inventory) lives outside scene lifecycle
- Name scenes and prefabs descriptively — `forest_level_01`, not `Scene3`

## Testing
- Unit test game logic (damage calculation, inventory rules, state transitions) without the engine
- Integration test critical systems (save/load, networking) with engine in headless mode
- Playtest regularly — automated tests catch logic bugs, not feel issues
- Profile on target hardware, not just dev machines
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New game system

```markdown
# Prompt: <SystemName> system (e.g., inventory, combat, movement)

## Task
Create a <SystemName> system that <does what>.

## Components
- <ComponentName: fields — description, for each data component>

## Behavior
- <core system behavior — what happens each tick/frame>
- <player interactions — input triggers, feedback>
- <edge cases: empty inventory, zero health, max stack, boundary conditions>

## Integration
- Which existing systems does this interact with? (physics, animation, UI, audio)
- Event/message contracts: <event name — payload — when fired>
- Save/load: what state must persist across sessions?

## Constraints
- No per-frame allocations — use pools or pre-allocated buffers
- Frame budget: <X>ms max for this system's update
- Must work with the existing ECS/component architecture
- Decouple from rendering — logic testable in isolation

## Output format
- Component definitions (data only)
- System implementation (logic only)
- Unit tests for core logic (no engine dependency)
- Integration notes: how to wire into existing update loop
```

### Multiplayer feature with netcode

```markdown
# Prompt: <Feature> with netcode

## Task
Add networked <feature> (e.g., player movement sync, ability casting, item trading) supporting <architecture: client-server / P2P / rollback>.

## Network Model
- Authority: <server-authoritative / client-predicted / owner-authoritative>
- Sync frequency: <every tick / on change / on event>
- Payload: <what data is sent per update>

## Behavior
- <what the owning client sees (immediate feedback)>
- <what remote clients see (interpolated / extrapolated)>
- <what happens on desync or packet loss>
- <conflict resolution: server wins, latest-write-wins, rollback>

## Constraints
- Latency budget: <X>ms round trip before degraded experience
- Bandwidth budget: <X> bytes per update per player
- Must handle: packet loss, out-of-order delivery, player disconnect mid-action
- Anti-cheat: server validates all state-changing actions
- No client-only state that affects gameplay outcomes

## Output format
- Network message definitions (serialized payload)
- Client-side prediction and reconciliation logic
- Server-side validation and broadcast logic
- Tests: simulated latency, packet loss, desync recovery
```

### Performance optimization pass

```markdown
# Prompt: Optimize <system/scene/feature>

## Task
Reduce <metric: frame time / draw calls / memory / GC spikes / load time> for <target system or scene>.

## Current Profile
- Current metric value: <measured value>
- Target metric value: <goal>
- Profiler hotspots: <top 3 functions/systems by time or allocation>

## Constraints
- No visible quality regression — maintain current visual fidelity
- Must still hit target frame rate on min-spec hardware: <spec>
- Don't break existing save files or network protocol
- Changes must be measurable — before/after profiler captures required

## Approach (pick applicable)
- [ ] Object pooling for frequent spawn/destroy
- [ ] Batch draw calls / reduce material count
- [ ] LOD tuning or culling improvements
- [ ] Cache / precompute values currently recalculated per frame
- [ ] Reduce GC pressure (remove per-frame allocations)
- [ ] Async loading / streaming for large assets

## Output format
- Optimized implementation
- Before/after profiler comparison methodology
- Tests verifying behavior unchanged
- Notes on tradeoffs made (e.g., memory vs. CPU, quality vs. performance)
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Performance**
- [ ] Frame time within budget? No spikes above target (16.6ms for 60fps)?
- [ ] Draw calls within budget? Batching applied where possible?
- [ ] No per-frame heap allocations in update loops? Object pools used for spawning?
- [ ] No GC spikes during gameplay? Profiled on target hardware?
- [ ] Memory within budget? No leaking references to destroyed objects?

**Architecture**
- [ ] Uses composition / ECS patterns? No deep inheritance hierarchies?
- [ ] Game logic decoupled from rendering? Testable without running the engine?
- [ ] State machines or behavior trees for complex behavior? No nested if/else chains?
- [ ] Components hold data, systems hold logic? No god objects?

**Assets**
- [ ] Assets loaded through the pipeline, not raw file paths?
- [ ] Streaming and LOD configured for variable-distance assets?
- [ ] Memory pools used for frequently instantiated objects?
- [ ] Preloading during transitions, not on first use during gameplay?

**Input**
- [ ] Input abstracted behind action maps? No hardcoded key/button references?
- [ ] Responsive — input buffer for action timing? No dropped inputs between frames?
- [ ] Rebinding supported for accessibility?
- [ ] Multiple input methods handled (keyboard, gamepad, touch)?

**Multiplayer** (if applicable)
- [ ] Server-authoritative for gameplay-affecting state?
- [ ] Deterministic where required? Same inputs produce same results?
- [ ] Latency compensation implemented (interpolation, prediction, rollback)?
- [ ] Handles packet loss, disconnect, and reconnect gracefully?
- [ ] Bandwidth within budget per player?

**Platform**
- [ ] Builds and runs on all target platforms?
- [ ] Meets certification requirements (TRC, XR, app store guidelines)?
- [ ] Input methods correct for each platform (gamepad on console, touch on mobile)?
- [ ] Performance targets met on min-spec hardware, not just dev machines?

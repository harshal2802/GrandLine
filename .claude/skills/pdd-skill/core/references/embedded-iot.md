# PDD Reference: Embedded / IoT Projects

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for embedded systems and IoT projects (MCU firmware, RTOS applications, bare-metal drivers, sensor networks, edge devices, and similar hardware-constrained software).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Target hardware (MCU family, SoC, SBC)?
- RTOS vs bare-metal vs Linux-based?
- Language and toolchain (C, C++, Rust, MicroPython, Arduino framework)?
- Memory constraints (RAM, flash)?
- Communication protocols (MQTT, BLE, Zigbee, LoRa, CAN bus)?
- OTA update mechanism?
- Power source and budget (battery, mains, energy harvesting)?
- Safety certification requirements (IEC 61508, DO-178C, etc.)?

### Extended `pdd/context/project.md` sections for embedded / IoT

```markdown
## Hardware Target and Constraints
- MCU / SoC / SBC:
- Clock speed:
- RAM:
- Flash:
- External memory (EEPROM, SD, QSPI flash):

## RTOS / Scheduler Details
- RTOS or bare-metal:
- RTOS name and version: (FreeRTOS, Zephyr, RT-Thread, etc.)
- Task / thread model:
- Tick rate and scheduling policy:
- Stack sizes per task:

## Communication Protocol and Data Format
- Primary protocol: (MQTT, BLE, Zigbee, LoRa, CAN bus, Wi-Fi, cellular)
- Data serialization: (Protobuf, CBOR, JSON, raw binary)
- Broker / gateway: (cloud endpoint, local hub, mesh)
- QoS / reliability requirements:

## Power Management Strategy
- Power source: (battery, mains, energy harvesting, USB)
- Sleep modes used: (light sleep, deep sleep, hibernation)
- Wake sources: (timer, GPIO, RTC, radio)
- Target battery life:

## OTA Update and Rollback Mechanism
- OTA transport: (MQTT, HTTP, BLE DFU, custom)
- Dual-bank / A-B partition scheme:
- Rollback trigger: (boot count, watchdog, health check)
- Signature / verification:

## Pin Mapping and Peripheral Usage
- GPIO assignments:
- Bus peripherals: (SPI, I2C, UART, ADC, PWM — which pins, which devices)
- Interrupt-driven vs polled peripherals:
- DMA channels:
```

---

## Conventions Starter (Workflow 2)

```markdown
# Embedded / IoT Conventions

## Memory Management
- Prefer static allocation — all buffers, queues, and task stacks sized at compile time
- No dynamic allocation (malloc/free) in ISRs or real-time tasks
- Use memory pools for variable-size allocations where unavoidable
- Document worst-case memory usage per module in comments or a memory map file
- Stack overflow detection enabled in RTOS config (or manual canary checks in bare-metal)

## Interrupt Safety
- ISRs do minimal work — set a flag or enqueue to a buffer, then return
- Never call blocking functions (mutex lock, printf, malloc) from ISR context
- Use volatile for shared variables accessed from ISR and main context
- Document interrupt priorities and ensure no priority inversion
- Critical sections as short as possible — disable interrupts only when necessary

## Naming Conventions
- Modules prefixed by subsystem: `sensor_read()`, `comms_send()`, `power_enter_sleep()`
- Hardware register access through HAL functions, never raw addresses in application code
- Constants for pin numbers, register offsets, and magic values — no bare literals
- ISR handlers named `<peripheral>_IRQHandler` matching vector table entries

## Power Management
- Default to lowest power state; wake only for scheduled work or external events
- Peripherals powered down when not in use
- Document power budget per operational mode (active, idle, sleep, deep sleep)
- Test and measure actual current draw — don't rely solely on datasheet estimates

## Error Handling
- No silent failures — every error path must log, set a flag, or trigger a safe state
- Watchdog timer enabled with appropriate timeout
- Define safe states for each subsystem (e.g., motor off, radio silent, LED error pattern)
- Assert on impossible states during development; degrade gracefully in production

## Testing
- Unit test business logic on host (x86) with mocked HAL
- Integration test on target hardware with logic analyzer or protocol sniffer
- Test interrupt-driven paths with stress scenarios (burst input, queue full)
- Power cycle and brown-out recovery tests
- OTA update and rollback tested on real hardware before release
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New peripheral driver

```markdown
# Prompt: <peripheral> driver

## Task
Write a driver for <peripheral> (e.g., BME280 sensor, SSD1306 OLED, W25Q flash) connected via <bus> (SPI / I2C / UART).

## Hardware
- Part number and datasheet reference:
- Bus: <SPI / I2C / UART> on <pins>
- Interrupt pin (if any):
- DMA channel (if any):

## Interface
- Init function: configure bus, verify device ID, set default operating mode
- Read function(s): <what data — temperature, acceleration, status register, etc.>
- Write function(s): <what data — configuration, commands, display buffer, etc.>
- Power control: enable/disable or enter low-power mode

## Constraints
- No dynamic allocation — all buffers statically sized
- Bus transaction timeout and retry logic
- Thread-safe if accessed from multiple RTOS tasks (mutex or designate single owner task)
- Return error codes, not booleans — caller decides how to handle
- HAL-abstracted bus access — no direct register writes to SPI/I2C peripheral

## Output format
- Driver header (.h) with public API and types
- Driver implementation (.c / .cpp / .rs)
- Unit tests using mocked bus (run on host)
- Example usage snippet
```

### OTA update mechanism

```markdown
# Prompt: OTA firmware update

## Task
Implement an OTA firmware update mechanism that <downloads and applies firmware over [MQTT / HTTP / BLE DFU]>.

## Architecture
- Dual-bank (A/B) or single-bank with staging area:
- Transport: <MQTT, HTTPS, BLE DFU, custom>
- Image format: <raw binary, signed binary, compressed>
- Verification: <CRC32, SHA-256, ECDSA signature>

## Update Flow
1. Check for update (poll or push notification)
2. Download image to <staging area / inactive bank>
3. Verify integrity and signature
4. Mark new image as pending, reboot into bootloader
5. Bootloader validates and swaps / boots new image
6. Application confirms health; if no confirmation within <N> boots, rollback

## Constraints
- Download must be resumable — handle network interruption mid-transfer
- Never erase active bank before new image is fully received and verified
- Rollback on failed boot (watchdog timeout or health check failure)
- Log update attempts, successes, and failures to persistent storage
- Power loss at any point must not brick the device

## Output format
- OTA manager module (download, verify, apply, rollback)
- Bootloader integration notes or bootloader code (if applicable)
- Test plan: successful update, interrupted download, corrupted image, power loss during write, rollback
```

### Communication protocol handler

```markdown
# Prompt: <protocol> handler

## Task
Implement a <protocol> (MQTT / BLE / Zigbee / LoRa / CAN bus) communication handler for <purpose — telemetry upload, command reception, mesh networking, etc.>.

## Protocol Details
- Protocol and version: <e.g., MQTT 3.1.1, BLE 5.0 GATT, CAN 2.0B>
- Broker / peer: <cloud endpoint, gateway, other devices>
- Topics / services / message IDs: <list>
- QoS / reliability: <at-most-once, at-least-once, exactly-once, ACK required>
- Data format: <JSON, CBOR, Protobuf, raw binary>

## Behavior
- Connection management: connect, reconnect with backoff, disconnect cleanly
- Send: serialize and transmit messages with appropriate QoS
- Receive: parse incoming messages, validate, dispatch to handler callbacks
- Buffering: queue outbound messages when disconnected, send when reconnected

## Constraints
- Fixed-size message buffers — no dynamic allocation
- Timeout on all network operations
- Thread-safe: send from any task, receive callback runs in dedicated task
- Power-aware: support duty-cycled operation (connect, exchange, disconnect, sleep)
- Log connection state changes and errors

## Output format
- Protocol handler module (init, connect, send, receive, disconnect)
- Message serialization / deserialization helpers
- Unit tests with mocked transport layer
- Integration test plan for real hardware
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Memory and allocation**
- [ ] All buffers statically allocated or from fixed-size pools?
- [ ] No malloc/free in ISR context?
- [ ] Stack sizes sufficient for worst-case call depth (verified, not guessed)?
- [ ] Total RAM usage within budget (static analysis or linker map checked)?
- [ ] No unbounded data structures (dynamic arrays, growing lists)?

**Interrupt safety**
- [ ] ISRs do minimal work (set flag, enqueue, return)?
- [ ] No blocking calls in ISR context (no mutex lock, no printf, no malloc)?
- [ ] Shared variables between ISR and main context marked volatile?
- [ ] Interrupt priorities documented and free of priority inversion?
- [ ] Critical sections as short as possible?

**Power management**
- [ ] Peripherals powered down when not in use?
- [ ] Sleep mode entered when idle (not busy-wait)?
- [ ] Wake sources correctly configured and tested?
- [ ] Power budget documented for each operational mode?

**Cross-compilation and target**
- [ ] Code compiles for target architecture with no warnings (-Wall -Werror)?
- [ ] No host-only assumptions (sizeof(int), endianness, alignment)?
- [ ] Linker script and memory map match target hardware?
- [ ] Flash usage within budget (checked via build output or linker map)?

**Communication and protocols**
- [ ] Reconnection logic with exponential backoff?
- [ ] Message buffers bounded and overflow handled?
- [ ] Timeouts on all network and bus operations?
- [ ] Data serialization matches protocol spec (endianness, field order, padding)?
- [ ] Graceful degradation when communication is unavailable?

**Safety and reliability**
- [ ] Watchdog timer enabled and fed correctly (not blindly in a timer ISR)?
- [ ] Safe state defined for all failure modes?
- [ ] Power-loss recovery tested (no corruption of persistent data)?
- [ ] OTA rollback tested and functional?
- [ ] Error paths log or signal — no silent failures?

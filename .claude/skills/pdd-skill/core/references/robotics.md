# PDD Reference: Robotics / ROS

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for robotics projects — autonomous robots, manipulator arms, drones, mobile robots, and autonomous vehicles built with ROS/ROS2 or custom frameworks, including simulation-first development, real-time control, and safety-critical systems.

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Robot type (manipulator arm, mobile robot, drone, humanoid, autonomous vehicle)?
- Framework (ROS1, ROS2, custom)?
- ROS2 middleware (DDS implementation — Fast-DDS, Cyclone DDS, etc.)?
- Simulation environment (Gazebo, Isaac Sim, MuJoCo, PyBullet)?
- Language (C++, Python, or mixed)?
- Real-time requirements (hard real-time control loops, soft real-time perception)?
- Sensor suite (LiDAR, cameras, IMU, force/torque, encoders)?
- Actuators and control interface (CAN bus, EtherCAT, PWM, serial)?
- Safety certification requirements (ISO 13849, IEC 62443, DO-178C)?
- Deployment target (on-robot compute, edge, cloud offload)?

### Extended `pdd/context/project.md` sections for robotics / ROS

```markdown
## Robot Platform and Hardware
- Robot type: (manipulator arm, mobile robot, drone, humanoid, autonomous vehicle)
- Hardware platform: (custom, commercial — model name, manufacturer)
- Compute: (Jetson, Raspberry Pi, industrial PC, x86 workstation — specify model)
- Actuators: (servo motors, stepper motors, hydraulic — interface: CAN, EtherCAT, PWM, serial)
- Power system: (battery capacity, voltage, estimated runtime)

## ROS2 Workspace and Package Structure
- ROS2 distribution: (Humble, Iron, Jazzy, Rolling)
- Middleware/DDS: (Fast-DDS, Cyclone DDS, Connext)
- Workspace layout: (monorepo, multi-repo, colcon workspace structure)
- Package organization: (one package per node, per subsystem, or per feature)
- Build system: (colcon, CMake, ament_cmake, ament_python)

## Node Graph Architecture
- Node list: (name, purpose, language — one line per node)
- Topics: (name, message type, publisher, subscriber(s), frequency, QoS profile)
- Services: (name, srv type, server node, client node(s), expected latency)
- Actions: (name, action type, server node, client node(s), typical duration)
- Lifecycle nodes: (which nodes use managed lifecycle — configure, activate, deactivate, shutdown)
- Composition: (which nodes are composed into a single process for performance)

## Control Loop Requirements
- Control frequency: (e.g., 1kHz for joint control, 100Hz for navigation, 30Hz for perception)
- Maximum acceptable jitter: (e.g., < 5% of loop period)
- Real-time executor: (single-threaded, multi-threaded, dedicated real-time thread)
- Hard real-time nodes: (list — these must be C++ with real-time guarantees)
- Soft real-time nodes: (list — Python acceptable, best-effort timing)

## Sensor Pipeline
- Sensors: (type, model, interface, data rate, message type)
- Processing stages: (raw → filtered → fused → decision — per sensor modality)
- Time synchronization: (message_filters, approximate time sync, exact time sync)
- Calibration: (intrinsic, extrinsic, stored where, recalibration procedure)
- Data quality: (outlier rejection, sanity checks, sensor health monitoring)

## Coordinate Frames and TF Tree
- Base frame: (base_link, base_footprint)
- Sensor frames: (one per sensor, static or dynamic transform)
- World frames: (map, odom, earth — which are used)
- TF publishers: (robot_state_publisher, joint_state_publisher, SLAM, odometry)
- Static transforms: (defined where — URDF, launch file, static_transform_publisher)

## Simulation Setup
- Simulator: (Gazebo Classic, Gazebo Sim/Ignition, Isaac Sim, MuJoCo, PyBullet)
- Robot model: (URDF, SDF, Xacro — where it lives)
- World/environment: (predefined, custom, procedurally generated)
- Sim-to-real gap strategy: (domain randomization, system identification, parameter tuning)
- Physics fidelity: (contact model, friction, gravity, sensor noise simulation)
- Sim-only vs shared code: (what runs only in sim, what runs on both sim and hardware)

## Safety Systems
- E-stop: (hardware e-stop, software e-stop, both — integration method)
- Watchdog: (heartbeat monitoring, timeout action — safe stop, hold position, power off)
- Workspace limits: (joint limits, Cartesian workspace boundaries, virtual walls)
- Collision checking: (self-collision, environment collision — method: FCL, Bullet, custom)
- Graceful degradation: (behavior when sensor fails, actuator fails, comms lost)
- Safety certification: (ISO 13849, IEC 62443, DO-178C — or none for research)

## Deployment and OTA Updates
- Deployment method: (Docker containers, Snap, deb packages, direct binary)
- OTA updates: (full image, differential, package-level — rollback strategy)
- Configuration management: (launch parameters, YAML config, environment-specific overrides)
- Remote monitoring: (ROS2 topics over network, custom dashboard, Foxglove, PlotJuggler)

## Logging and Data Recording
- Rosbag recording: (which topics, trigger conditions, storage location, retention policy)
- Log levels: (per-node configuration, runtime adjustable)
- Telemetry: (what metrics are published for monitoring — CPU, memory, loop timing, sensor health)
- Post-mortem analysis: (rosbag replay, log aggregation, crash dump collection)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Robotics / ROS Conventions

## Node Architecture
- One node, one responsibility — don't combine perception and control in a single node
- Use lifecycle nodes for anything that manages hardware or expensive resources
- Compose performance-critical nodes into a single process — avoid unnecessary serialization
- Node names are lowercase_snake_case — match the package name where practical
- Every node has a health topic publishing diagnostic status at 1Hz minimum

## Topics, Services, and Actions
- Topic names follow ROS2 conventions: lowercase, slashes for namespacing (e.g., /robot/joint_states)
- Use services for request-reply with fast responses (< 100ms) — never for long-running operations
- Use actions for long-running operations with feedback (motion planning, navigation goals)
- QoS profiles match the data pattern: RELIABLE for commands, BEST_EFFORT for high-rate sensors, TRANSIENT_LOCAL for latched configuration
- Document every topic's message type, expected frequency, and QoS in the package README

## Real-Time and Performance
- Control loops run in C++ with a dedicated real-time executor — never in Python
- Never allocate memory in a real-time loop — preallocate buffers, use fixed-size containers
- Never use blocking I/O (file, network, logging) in a real-time loop
- Measure and log actual loop timing — alert if jitter exceeds 5% of target period
- Perception pipelines have a latency budget — measure end-to-end from sensor to decision

## Coordinate Frames
- Always use TF2 for frame transforms — never hardcode transform matrices
- Every sensor has its own frame — publish static transforms in the URDF or launch file
- Use standard frame conventions: x-forward, y-left, z-up (REP 103)
- Timestamps on all messages — never publish data without a valid header.stamp
- Time synchronization between sensors uses message_filters — never assume simultaneous arrival

## Safety
- E-stop is the highest priority — always wire hardware e-stop, implement software e-stop as backup
- Every motion command is bounds-checked before execution — joint limits, velocity limits, workspace limits
- Watchdog on every hardware interface — if heartbeat is missed, go to safe state (not just stop publishing)
- Collision checking runs before motion execution — never skip, even in "known safe" environments
- Failure modes are explicit — every node documents what happens when its inputs go stale or invalid

## Simulation First
- All code must run in simulation before hardware — no exceptions for "simple" changes
- Simulation and hardware use the same launch files with a `use_sim_time` parameter
- Sensor noise and latency are simulated — don't test against perfect data
- Sim-to-real transfer gaps are documented and tracked — known discrepancies are logged as issues

## Testing
- Unit tests for algorithms (kinematics, filters, planners) — independent of ROS
- Integration tests with ROS2 launch_testing — test node communication and behavior
- Simulation tests for full-system behavior — robot completes a task in Gazebo
- Hardware-in-the-loop tests before deployment — run on the real robot in a controlled environment
- Regression tests for safety-critical behavior — e-stop, collision avoidance, workspace limits

## Logging and Recording
- Always record rosbags during testing and deployment — storage is cheap, missing data is not
- Include TF, joint states, commands, and sensor data in default recording profile
- Tag recordings with metadata (test name, conditions, operator, pass/fail)
- Logs must not affect real-time performance — use async logging, never block on log write
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New ROS2 node

```markdown
# Prompt: <NodeName> ROS2 node

## Task
Implement a ROS2 node for <purpose> (e.g., sensor driver, perception module, controller, planner).

## Node Design
- Node name: <lowercase_snake_case>
- Package: <which ROS2 package this belongs to>
- Language: <C++ for real-time, Python for non-critical>
- Lifecycle: <managed lifecycle node or regular node>
- Composition: <composable or standalone>

## Interfaces
- Subscriptions: <topic, message type, QoS, expected frequency>
- Publishers: <topic, message type, QoS, publish frequency>
- Services: <service name, srv type, purpose>
- Actions: <action name, action type, purpose>
- Parameters: <name, type, default, description — declared in constructor>

## Behavior
- Main loop / callback logic: <what the node does on each input>
- State machine: <if applicable — states, transitions, events>
- Error handling: <what happens when input is stale, invalid, or missing>
- Timing requirements: <target frequency, maximum acceptable latency>

## Safety
- Bounds checking: <what limits are enforced on outputs>
- Watchdog: <does this node monitor or publish heartbeats>
- Failure mode: <what happens when this node crashes or hangs>

## Constraints
- Must compile with colcon and pass ament linters
- Must work in simulation (use_sim_time) and on hardware
- Must publish diagnostic status for monitoring
- Parameters must be declared with descriptions (not hardcoded)

## Output format
- Node implementation (C++ or Python)
- Launch file entry
- Parameter YAML configuration
- Unit tests for core logic
- Integration test with launch_testing
```

### Sensor integration pipeline

```markdown
# Prompt: <SensorType> sensor pipeline

## Task
Implement the sensor processing pipeline for <sensor> (e.g., LiDAR, camera, IMU, force/torque) from raw data to usable output.

## Pipeline Stages
- Raw input: <message type, topic, frequency>
- Preprocessing: <filtering, downsampling, outlier rejection>
- Calibration: <intrinsic/extrinsic, where calibration data is stored>
- Fusion: <if combining with other sensors — method, time sync approach>
- Output: <message type, topic, frequency, downstream consumers>

## Coordinate Frames
- Sensor frame: <frame_id, static transform from base_link>
- Output frame: <which frame the processed data is published in>
- TF dependencies: <what transforms must be available>

## Quality and Monitoring
- Health checks: <data rate monitoring, value range validation, stale data detection>
- Diagnostics: <what diagnostic messages are published>
- Degraded mode: <behavior when sensor data is poor but not absent>

## Constraints
- Must handle sensor disconnect and reconnect gracefully
- Must work with simulated sensor data (Gazebo plugin or replay)
- Time synchronization using message_filters for multi-sensor fusion
- Processing latency must not exceed <budget>ms

## Output format
- Sensor driver node (or configuration for existing driver)
- Processing/filter node(s)
- Fusion node (if applicable)
- Launch file for the full pipeline
- Calibration file format and example
- Tests: valid data, degraded data, sensor dropout, time sync verification
```

### Motion planning and execution

```markdown
# Prompt: <MotionType> motion planning

## Task
Implement motion planning and execution for <motion type> (e.g., pick-and-place, navigation to goal, trajectory following, obstacle avoidance).

## Planning
- Planner: <MoveIt, Nav2, custom — specify algorithm>
- Planning space: <joint space, Cartesian space, configuration space>
- Constraints: <joint limits, workspace bounds, orientation constraints, collision objects>
- Planning time budget: <maximum allowed planning time>

## Execution
- Controller: <joint trajectory controller, velocity controller, position controller>
- Control frequency: <Hz>
- Feedback: <what is monitored during execution — joint error, force, distance to goal>
- Preemption: <can the motion be interrupted — how, what happens to the robot>

## Safety
- Collision checking: <self-collision, environment collision — updated during execution?>
- Velocity and acceleration limits: <per-joint and Cartesian>
- Workspace boundaries: <virtual walls, keep-out zones>
- E-stop behavior: <what happens on e-stop during motion>
- Failure recovery: <what happens on planning failure, execution error, timeout>

## Constraints
- Must respect all joint limits and velocity bounds at all times
- Must check for collisions before and during execution
- Must handle planning failure gracefully (report, retry with different parameters, abort)
- Must work in simulation before hardware deployment

## Output format
- Planning configuration (MoveIt/Nav2 config or custom planner)
- Execution node / action server
- Safety monitoring node
- Launch file
- Tests: successful plan and execute, planning failure, collision avoidance, e-stop during motion
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Node architecture**
- [ ] Each node has a single, clear responsibility?
- [ ] Lifecycle nodes used for hardware and resource management?
- [ ] Node names follow ROS2 conventions (lowercase_snake_case)?
- [ ] Parameters are declared (not hardcoded) with descriptions?
- [ ] Diagnostic status published for monitoring?

**Communication patterns**
- [ ] QoS profiles appropriate per topic (RELIABLE for commands, BEST_EFFORT for sensors)?
- [ ] Services used only for fast request-reply (< 100ms)?
- [ ] Actions used for long-running operations with feedback?
- [ ] No unnecessary topic remapping hacks or tight couplings?
- [ ] All topics and services documented with message type and expected frequency?

**Real-time and performance**
- [ ] Control loops maintain target frequency with < 5% jitter under load?
- [ ] No memory allocation in real-time loops?
- [ ] No blocking I/O in real-time callbacks?
- [ ] Perception-to-action latency within specified budget?
- [ ] Memory usage stable over long runs (no leaks in persistent nodes)?

**Coordinate frames and time**
- [ ] TF2 used for all frame transforms (no hardcoded matrices)?
- [ ] Standard frame conventions followed (REP 103: x-forward, y-left, z-up)?
- [ ] All messages have valid timestamps?
- [ ] Multi-sensor fusion uses message_filters for time synchronization?
- [ ] Static transforms defined in URDF or launch file?

**Safety**
- [ ] E-stop integration works — robot halts within specified time?
- [ ] All motion commands respect workspace limits and collision boundaries?
- [ ] Watchdog monitoring on hardware interfaces with timeout to safe state?
- [ ] Collision checking runs before and during motion execution?
- [ ] Graceful degradation when a sensor or actuator fails (no crash, no freeze)?
- [ ] Failure modes documented for every node?

**Simulation and deployment**
- [ ] Code runs in simulation before hardware deployment?
- [ ] Launch files parameterized for both simulation and hardware (use_sim_time)?
- [ ] Simulation behavior matches hardware within acceptable tolerance?
- [ ] Sensor noise simulated (not testing against perfect data)?
- [ ] Rosbag recording captures all relevant topics for debugging?
- [ ] Launch files work with both simulation and hardware configurations?

**Testing**
- [ ] Unit tests for algorithms independent of ROS?
- [ ] Integration tests with launch_testing for node communication?
- [ ] Simulation tests for full-system behavior?
- [ ] Safety-critical behavior has dedicated regression tests?
- [ ] Hardware-in-the-loop test plan documented (even if not yet automated)?

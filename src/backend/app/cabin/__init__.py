"""The Cabin — per-user persistent sandbox container (Phase 0b).

A Cabin is a persistent, per-user, isolated container that holds the user's
credentials (materialized from the Sea Chest) and runs their workloads. The
backend is swappable behind :class:`CabinBackend` (mirroring
``ExecutionBackend``/``DeploymentBackend``/``BrowserCheckBackend``): the
deterministic, container-free :class:`NullCabinBackend` is the CI-safe default,
and :class:`GVisorCabinBackend` is the opt-in real backend.
"""

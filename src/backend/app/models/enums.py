import enum


class VoyageStatus(str, enum.Enum):
    CHARTED = "CHARTED"
    PLANNING = "PLANNING"
    PDD = "PDD"
    TDD = "TDD"
    BUILDING = "BUILDING"
    REVIEWING = "REVIEWING"
    DEPLOYING = "DEPLOYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class CrewRole(str, enum.Enum):
    CAPTAIN = "captain"
    NAVIGATOR = "navigator"
    DOCTOR = "doctor"
    SHIPWRIGHT = "shipwright"
    HELMSMAN = "helmsman"


class CheckpointReason(str, enum.Enum):
    INTERVAL = "interval"
    FAILOVER = "failover"
    PAUSE = "pause"
    MIGRATION = "migration"

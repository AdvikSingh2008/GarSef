"""Traffic light controllers for the 3x3 grid study."""
from .base import BaseController
from .fixed import FixedTimeController
from .actuated import ActuatedController
from .max_pressure import MaxPressureController
from .qlearning import QLearningController
from .pgql import PGQLController

CONTROLLERS = {
    "fixed":        FixedTimeController,
    "actuated":     ActuatedController,
    "max_pressure": MaxPressureController,
    "qlearning":    QLearningController,
    "pgql":         PGQLController,
}

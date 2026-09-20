"""Fixed-time controller: lets SUMO run the static plan baked into .net.xml.
This is the BASELINE."""
from .base import BaseController


class FixedTimeController(BaseController):
    name = "fixed"

    def step(self, t: int):
        return

"""Base controller interface. All controllers expose setup/step/teardown."""
from __future__ import annotations


class BaseController:
    name: str = "base"

    def __init__(self, **kwargs):
        self.cfg = kwargs

    def setup(self, traci_conn):
        self.traci = traci_conn
        self.tls_ids = list(self.traci.trafficlight.getIDList())

    def step(self, t: int):
        pass

    def teardown(self):
        pass

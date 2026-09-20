"""Gap-out actuated controller.

If the green has been on for at least MIN_GREEN and there are no vehicles
queued on the served lanes (the platoon has 'gapped out'), advance to the
next phase early. If MAX_GREEN is reached, force advance regardless. This
is the standard gap-out / max-out actuated logic, more robust than
incremental extension.
"""
from .base import BaseController


class ActuatedController(BaseController):
    name = "actuated"
    MIN_GREEN = 8
    MAX_GREEN = 50
    YELLOW_TIME = 3

    def setup(self, traci_conn):
        super().setup(traci_conn)
        self._green_phases = {}
        self._phase_start_t = {}
        self._pending_yellow = {}
        for tls in self.tls_ids:
            logic = self.traci.trafficlight.getAllProgramLogics(tls)[0]
            greens = [i for i, ph in enumerate(logic.phases)
                      if ("G" in ph.state or "g" in ph.state) and "y" not in ph.state]
            self._green_phases[tls] = greens
            self._phase_start_t[tls] = 0

    def _green_lanes(self, tls):
        state = self.traci.trafficlight.getRedYellowGreenState(tls)
        controlled = self.traci.trafficlight.getControlledLanes(tls)
        return [l for l, s in zip(controlled, state) if s in ("G", "g")]

    def _advance(self, tls, t):
        cur = self.traci.trafficlight.getPhase(tls)
        logic = self.traci.trafficlight.getAllProgramLogics(tls)[0]
        n = len(logic.phases)
        yellow_idx = None
        for k in range(1, n + 1):
            i = (cur + k) % n
            if "y" in logic.phases[i].state:
                yellow_idx = i
                break
        next_green = None
        if yellow_idx is not None:
            for k in range(1, n + 1):
                i = (yellow_idx + k) % n
                if i in self._green_phases[tls]:
                    next_green = i
                    break
        if yellow_idx is None or next_green is None:
            greens = self._green_phases[tls]
            if not greens:
                return
            cur_g = greens.index(cur) if cur in greens else 0
            self.traci.trafficlight.setPhase(tls, greens[(cur_g + 1) % len(greens)])
            self._phase_start_t[tls] = t
        else:
            self.traci.trafficlight.setPhase(tls, yellow_idx)
            self._pending_yellow[tls] = (next_green, t + self.YELLOW_TIME)

    def step(self, t: int):
        for tls, (target_phase, when) in list(self._pending_yellow.items()):
            if t >= when:
                self.traci.trafficlight.setPhase(tls, target_phase)
                self._phase_start_t[tls] = t
                del self._pending_yellow[tls]

        for tls in self.tls_ids:
            if tls in self._pending_yellow:
                continue
            cur = self.traci.trafficlight.getPhase(tls)
            if cur not in self._green_phases[tls]:
                continue
            elapsed = t - self._phase_start_t[tls]
            if elapsed < self.MIN_GREEN:
                continue
            green = self._green_lanes(tls)
            queued = sum(self.traci.lane.getLastStepHaltingNumber(l) for l in green)
            if queued == 0 and len(self._green_phases[tls]) > 1:
                self._advance(tls, t)
            elif elapsed >= self.MAX_GREEN and len(self._green_phases[tls]) > 1:
                self._advance(tls, t)

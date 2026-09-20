"""Max-pressure controller (Varaiya 2013).
Each TLS picks the green phase that maximises pressure
    pressure(phase) = sum over moves served of (q_in - q_out)
Provably stable for any demand within the network's capacity region."""
from .base import BaseController


class MaxPressureController(BaseController):
    name = "max_pressure"

    DECISION_PERIOD = 5
    MIN_GREEN = 8
    YELLOW_TIME = 3

    def setup(self, traci_conn):
        super().setup(traci_conn)
        self._green_phases = {}
        self._last_switch_t = {tls: -1e9 for tls in self.tls_ids}
        self._pending_yellow = {}

        for tls in self.tls_ids:
            logic = self.traci.trafficlight.getAllProgramLogics(tls)[0]
            greens = []
            for i, ph in enumerate(logic.phases):
                if ("G" in ph.state or "g" in ph.state) and "y" not in ph.state:
                    greens.append(i)
            self._green_phases[tls] = greens

        self._phase_moves = {}
        for tls in self.tls_ids:
            links = self.traci.trafficlight.getControlledLinks(tls)
            logic = self.traci.trafficlight.getAllProgramLogics(tls)[0]
            for ph in self._green_phases[tls]:
                state = logic.phases[ph].state
                served = []
                for i, conn_list in enumerate(links):
                    if not conn_list:
                        continue
                    if i < len(state) and state[i] in ("G", "g"):
                        in_lane, out_lane, _ = conn_list[0]
                        served.append((in_lane, out_lane))
                self._phase_moves[(tls, ph)] = served

    def _pressure(self, tls, phase):
        moves = self._phase_moves.get((tls, phase), [])
        p = 0
        for in_lane, out_lane in moves:
            q_in = self.traci.lane.getLastStepHaltingNumber(in_lane)
            q_out = self.traci.lane.getLastStepHaltingNumber(out_lane)
            p += (q_in - q_out)
        return p

    def step(self, t: int):
        for tls, (target_phase, when) in list(self._pending_yellow.items()):
            if t >= when:
                self.traci.trafficlight.setPhase(tls, target_phase)
                self._last_switch_t[tls] = t
                del self._pending_yellow[tls]

        if t % self.DECISION_PERIOD != 0:
            return

        for tls in self.tls_ids:
            if tls in self._pending_yellow:
                continue
            greens = self._green_phases[tls]
            if len(greens) <= 1:
                continue
            cur = self.traci.trafficlight.getPhase(tls)
            if t - self._last_switch_t[tls] < self.MIN_GREEN:
                continue

            best_phase = max(greens, key=lambda p: self._pressure(tls, p))
            if best_phase == cur:
                continue
            logic = self.traci.trafficlight.getAllProgramLogics(tls)[0]
            yellow_idx = None
            for i, ph in enumerate(logic.phases):
                if "y" in ph.state and i > cur:
                    yellow_idx = i
                    break
            if yellow_idx is None:
                self.traci.trafficlight.setPhase(tls, best_phase)
                self._last_switch_t[tls] = t
            else:
                self.traci.trafficlight.setPhase(tls, yellow_idx)
                self._pending_yellow[tls] = (best_phase, t + self.YELLOW_TIME)

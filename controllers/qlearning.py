"""Independent tabular Q-learning per intersection.

State per TLS: bucketed queue lengths on incoming approaches + current green idx.
Actions: 0 = hold current green, 1 = switch to next green (yellow inserted).
Reward: -(incremental waiting time accumulated since last decision).
"""
import os
import pickle
import random
from collections import defaultdict
from .base import BaseController


def _bucket(q):
    if q == 0: return 0
    if q <= 3: return 1
    if q <= 7: return 2
    return 3


class QLearningController(BaseController):
    name = "qlearning"

    DECISION_PERIOD = 5
    MIN_GREEN = 8
    YELLOW_TIME = 3

    ALPHA = 0.1
    GAMMA = 0.9
    EPS_START = 0.30
    EPS_END = 0.02

    def __init__(self, qtable_path=None, train=False, eps=None, **kw):
        super().__init__(**kw)
        self.qtable_path = qtable_path
        self.train = train
        self.eps = eps if eps is not None else (self.EPS_START if train else self.EPS_END)
        self.Q = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
        if qtable_path and os.path.exists(qtable_path):
            with open(qtable_path, "rb") as f:
                raw = pickle.load(f)
            for tls, table in raw.items():
                for s, v in table.items():
                    self.Q[tls][s] = list(v)
        self._last_state = {}
        self._last_action = {}
        self._last_wait_sum = {}
        self._last_switch_t = {}
        self._pending_yellow = {}

    def _green_phases(self, tls):
        return self._green_phases_cache[tls]

    def _state(self, tls):
        in_lanes = sorted(set(self.traci.trafficlight.getControlledLanes(tls)))
        qs = tuple(_bucket(self.traci.lane.getLastStepHaltingNumber(l)) for l in in_lanes)
        cur_phase = self.traci.trafficlight.getPhase(tls)
        greens = self._green_phases(tls)
        cur_idx = greens.index(cur_phase) if cur_phase in greens else 0
        return qs + (cur_idx,)

    def _wait_sum(self, tls):
        in_lanes = set(self.traci.trafficlight.getControlledLanes(tls))
        return sum(self.traci.lane.getWaitingTime(l) for l in in_lanes)

    def setup(self, traci_conn):
        super().setup(traci_conn)
        self._green_phases_cache = {}
        for tls in self.tls_ids:
            logic = self.traci.trafficlight.getAllProgramLogics(tls)[0]
            greens = [i for i, ph in enumerate(logic.phases)
                      if ("G" in ph.state or "g" in ph.state) and "y" not in ph.state]
            self._green_phases_cache[tls] = greens
            self._last_switch_t[tls] = -1e9
            self._last_wait_sum[tls] = 0

    def _choose_action(self, tls, state):
        if random.random() < self.eps:
            return random.randint(0, 1)
        q = self.Q[tls][state]
        return 0 if q[0] >= q[1] else 1

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
            greens = self._green_phases(tls)
            if len(greens) <= 1:
                continue
            if t - self._last_switch_t[tls] < self.MIN_GREEN:
                continue

            state = self._state(tls)
            wait_now = self._wait_sum(tls)

            if self.train and tls in self._last_state:
                prev_s = self._last_state[tls]
                prev_a = self._last_action[tls]
                reward = -(wait_now - self._last_wait_sum[tls])
                old = self.Q[tls][prev_s][prev_a]
                best_next = max(self.Q[tls][state])
                self.Q[tls][prev_s][prev_a] = old + self.ALPHA * (reward + self.GAMMA * best_next - old)

            action = self._choose_action(tls, state)
            self._last_state[tls] = state
            self._last_action[tls] = action
            self._last_wait_sum[tls] = wait_now

            if action == 0:
                continue
            cur = self.traci.trafficlight.getPhase(tls)
            cur_g_idx = greens.index(cur) if cur in greens else 0
            next_phase = greens[(cur_g_idx + 1) % len(greens)]

            logic = self.traci.trafficlight.getAllProgramLogics(tls)[0]
            yellow_idx = None
            for i in range(cur + 1, len(logic.phases)):
                if "y" in logic.phases[i].state:
                    yellow_idx = i
                    break
            if yellow_idx is None:
                self.traci.trafficlight.setPhase(tls, next_phase)
                self._last_switch_t[tls] = t
            else:
                self.traci.trafficlight.setPhase(tls, yellow_idx)
                self._pending_yellow[tls] = (next_phase, t + self.YELLOW_TIME)

    def teardown(self):
        if self.train and self.qtable_path:
            os.makedirs(os.path.dirname(self.qtable_path), exist_ok=True)
            raw = {tls: dict(tbl) for tls, tbl in self.Q.items()}
            with open(self.qtable_path, "wb") as f:
                pickle.dump(raw, f)

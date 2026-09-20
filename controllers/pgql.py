"""Paper-based reconstruction, NOT the missing original PGQL implementation.

Action 2 selects the green other than the max-pressure recommendation.
Timing/phase execution inherits the recovered max-pressure implementation.
"""
import os
import pickle
import random
from collections import defaultdict, Counter
from .max_pressure import MaxPressureController
from .qlearning import _bucket


class PGQLController(MaxPressureController):
    name = "pgql"
    ALPHA = 0.1
    GAMMA = 0.9

    def __init__(self, qtable_path=None, train=False, eps=None, **kwargs):
        super().__init__(**kwargs)
        self.qtable_path = qtable_path
        self.train = train
        self.eps = eps if eps is not None else (0.30 if train else 0.02)
        self.Q = defaultdict(lambda: defaultdict(lambda: [0.0, 1.0, 0.0]))
        if qtable_path and os.path.exists(qtable_path):
            with open(qtable_path, "rb") as f:
                raw = pickle.load(f)  # Only tables trained locally by this experiment.
            for tls, table in raw.items():
                for state, values in table.items():
                    self.Q[tls][state] = list(values)
        self.previous = {}
        self.action_counts = Counter()

    def _select_phase(self, tls, greens, cur):
        expert = super()._select_phase(tls, greens, cur)
        lanes = sorted(set(self.traci.trafficlight.getControlledLanes(tls)))
        state = tuple(_bucket(self.traci.lane.getLastStepHaltingNumber(l)) for l in lanes)
        state += (greens.index(cur) if cur in greens else 0, int(expert != cur))
        wait = sum(self.traci.lane.getWaitingTime(l) for l in lanes)
        if self.train and tls in self.previous:
            prev_state, prev_action, prev_wait = self.previous[tls]
            old = self.Q[tls][prev_state][prev_action]
            reward = -(wait - prev_wait)
            self.Q[tls][prev_state][prev_action] = old + self.ALPHA * (
                reward + self.GAMMA * max(self.Q[tls][state]) - old)
        if random.random() < self.eps:
            action = random.randrange(3)
        else:
            action = max(range(3), key=lambda a: self.Q[tls][state][a])
        self.previous[tls] = (state, action, wait)
        self.action_counts[action] += 1
        if action == 0:
            return cur
        if action == 1:
            return expert
        return next(p for p in greens if p != expert)

    def teardown(self):
        if self.train and self.qtable_path:
            os.makedirs(os.path.dirname(self.qtable_path), exist_ok=True)
            with open(self.qtable_path, "wb") as f:
                pickle.dump({tls: dict(table) for tls, table in self.Q.items()}, f)

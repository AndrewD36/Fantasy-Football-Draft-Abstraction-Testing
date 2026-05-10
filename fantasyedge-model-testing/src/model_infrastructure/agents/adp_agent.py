import numpy as np
from model_infrastructure.agents.base_agent import BaseAgent

class ADPAgent(BaseAgent):
    name = "adp"
    def __init__(self, adp_table: dict[str, float], temperature: float = 2.0, seed: int = 0):
        self.adp = adp_table              # player_id -> adp rank
        self.temp = temperature
        self.rng = np.random.default_rng(seed)

    def pick(self, state, my_slot) -> str:
        legal = [(pid, self.adp.get(pid, 999.0))
                 for pid, p in state.available.items()
                 if state.rosters[my_slot].can_add(p)]
        pids = [pid for pid, _ in legal]
        ranks = np.fromiter((rank for _, rank in legal), dtype=np.float64, count=len(legal))
        u = self.rng.random(len(legal))
        scores = -ranks / self.temp - np.log(-np.log(u))
        return pids[int(np.argmax(scores))]
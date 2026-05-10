import math, random
from model_infrastructure.agents.base_agent import BaseAgent

class ADPAgent(BaseAgent):
    name = "adp"
    def __init__(self, adp_table: dict[str, float], temperature: float = 2.0, seed: int = 0):
        self.adp = adp_table              # player_id -> adp rank
        self.temp = temperature
        self.rng = random.Random(seed)

    def pick(self, state, my_slot) -> str:
        legal = [(pid, self.adp.get(pid, 999.0))
                 for pid, p in state.available.items()
                 if state.rosters[my_slot].can_add(p)]
        # Lower ADP = better. Convert to logits: -adp/temp, sample with Gumbel-max.
        logits = [-rank / self.temp for _, rank in legal]
        gumbels = [-math.log(-math.log(self.rng.random())) for _ in legal]
        scored = [(pid, l + g) for (pid, _), l, g in zip(legal, logits, gumbels, strict=True)]
        return max(scored, key=lambda x: x[1])[0]
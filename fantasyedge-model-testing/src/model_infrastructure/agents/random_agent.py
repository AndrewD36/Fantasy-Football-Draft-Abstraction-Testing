import random
from model_infrastructure.agents.base_agent import BaseAgent
from model_infrastructure.domain.draft import DraftState

class RandomAgent(BaseAgent):
    name = "random"
    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
    def pick(self, state: DraftState, my_slot: int) -> str:
        legal = [pid for pid, p in state.available.items()
                 if state.rosters[my_slot].can_add(p)]
        return self.rng.choice(legal)
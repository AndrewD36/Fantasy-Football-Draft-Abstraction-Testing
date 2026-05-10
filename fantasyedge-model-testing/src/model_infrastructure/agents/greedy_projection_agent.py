from model_infrastructure.agents.base_agent import BaseAgent

class GreedyProjectionAgent(BaseAgent):
    name = "greedy_prior"
    def __init__(self, prior_points: dict[str, float]):
        self.prior = prior_points
    def pick(self, state, my_slot) -> str:
        legal = [(pid, self.prior.get(pid, 0.0))
                 for pid, p in state.available.items()
                 if state.rosters[my_slot].can_add(p)]
        return max(legal, key=lambda x: x[1])[0]
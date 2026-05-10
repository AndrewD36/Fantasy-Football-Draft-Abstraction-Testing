from typing import Protocol, runtime_checkable
from model_infrastructure.domain.draft import DraftState, Pick

@runtime_checkable
class Agent(Protocol):
    name: str
    def pick(self, state: DraftState, my_slot: int) -> str: ...
    def observe(self, state: DraftState, pick: Pick) -> None: ...

class BaseAgent:
    """Convenience base; concrete agents inherit and override pick()."""
    name: str = "base"
    def observe(self, state: DraftState, pick: Pick) -> None:
        pass  # most agents are stateless
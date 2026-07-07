"""Base agent contract."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from processiq_shared.state import AgentState, TraceEvent


class Agent(ABC):
    name: str = "agent"
    model: str | None = None
    version: str = "0.1.0"

    @abstractmethod
    def _run(self, state: AgentState) -> AgentState:  # pragma: no cover - abstract
        ...

    def run(self, state: AgentState) -> AgentState:
        start = time.perf_counter()
        status = "ok"
        try:
            state = self._run(state)
        except Exception:
            status = "error"
            raise
        finally:
            state.add_trace(
                TraceEvent(
                    agent=self.name,
                    model=self.model,
                    version=self.version,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    status=status,
                )
            )
        return state

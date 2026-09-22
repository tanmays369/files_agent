"""Budget guard and cost ledger (T3.4). Stops a runaway loop before it spends your key."""
from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    """Raised when a cap is hit. The run records `aborted: budget`."""


@dataclass
class Budget:
    max_turns: int
    max_calls: int
    max_usd: float
    price_in_per_mtok: float = 3.0
    price_out_per_mtok: float = 15.0
    turns: int = 0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def usd(self) -> float:
        return round(self.input_tokens / 1e6 * self.price_in_per_mtok + self.output_tokens / 1e6 * self.price_out_per_mtok, 6)

    def add_turn(self) -> None:
        self.turns += 1
        if self.turns > self.max_turns:
            raise BudgetExceeded(f"turn cap reached ({self.max_turns})")

    def reserve(self, calls: int) -> None:
        """Refuse to START a multi-call sequence (e.g. read-write-confirm) that the cap would cut off halfway."""
        if self.calls + calls > self.max_calls:
            raise BudgetExceeded(f"MCP call cap would be reached mid-write ({self.calls}+{calls} > {self.max_calls}); stopped before writing")

    def add_call(self) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            raise BudgetExceeded(f"MCP call cap reached ({self.max_calls})")

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        if self.usd > self.max_usd:
            raise BudgetExceeded(f"spend cap reached (${self.max_usd:.2f})")

    def ledger(self) -> dict[str, float | int]:
        return {"turns": self.turns, "mcp_calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "usd": self.usd}

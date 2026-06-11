import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    model_overrides: dict = field(default_factory=dict)
    _token_log: list = field(default_factory=list, repr=False)

    def accumulate_tokens(self, role: str, input_tokens: int, output_tokens: int) -> None:
        self._token_log.append(
            {"role": role, "input_tokens": input_tokens, "output_tokens": output_tokens}
        )

    def total_cost(self, config: dict) -> float:
        total = 0.0
        for entry in self._token_log:
            role_cfg = config["models"].get(entry["role"], {})
            cost_in = role_cfg.get("cost_per_1k_input", 0.0)
            cost_out = role_cfg.get("cost_per_1k_output", 0.0)
            total += (entry["input_tokens"] / 1000) * cost_in
            total += (entry["output_tokens"] / 1000) * cost_out
        return total

    def get_summary(self, config: dict) -> dict:
        calls_by_role: dict = {}
        total_in = 0
        total_out = 0

        for entry in self._token_log:
            role = entry["role"]
            if role not in calls_by_role:
                calls_by_role[role] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            calls_by_role[role]["calls"] += 1
            calls_by_role[role]["input_tokens"] += entry["input_tokens"]
            calls_by_role[role]["output_tokens"] += entry["output_tokens"]
            total_in += entry["input_tokens"]
            total_out += entry["output_tokens"]

        return {
            "session_id": self.session_id,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_cost": self.total_cost(config),
            "calls_by_role": calls_by_role,
        }


def create_session() -> Session:
    return Session(session_id=str(uuid.uuid4()))

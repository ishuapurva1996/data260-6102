from dataclasses import dataclass


@dataclass(frozen=True)
class BikeConfig:
    model: str = "qwen3:8b"
    base_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.0
    seed: int = 6102
    context_window: int = 32768
    output_limit: int = 512
    request_timeout: float = 120.0
    max_seconds: float = 600.0
    max_model_requests: int = 8
    max_tools: int = 16
    max_tokens: int = 48000

    def __post_init__(self):
        for name in (
            "context_window",
            "output_limit",
            "max_model_requests",
            "max_tools",
            "max_tokens",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if (
            not 0 < self.output_limit < self.context_window
            or not 0 < self.request_timeout <= self.max_seconds <= 600
        ):
            raise ValueError("Invalid model/context/time limits.")

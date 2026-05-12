from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DecomposeConfig:
    """Configuration for the decomposition pipeline."""

    # LLM settings
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.3
    base_url: str = "https://api.deepseek.com"

    # Chunking settings
    max_chunk_tokens: int = 8000
    chunk_overlap_tokens: int = 500

    # Arc merge settings
    chapters_per_arc: int = 15

    # Parallelism
    max_parallel_extractions: int = 5

    # Output
    output_dir: Path = field(default_factory=lambda: Path("output"))

    # LLM API key (loaded from env if not set)
    api_key: str = ""


@dataclass
class Config:
    decompose: DecomposeConfig = field(default_factory=DecomposeConfig)


default_config = Config()

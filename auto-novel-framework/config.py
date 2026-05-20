from dataclasses import dataclass, field
from pathlib import Path

# API presets
API_PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.1-8b-instant",
        "description": "Groq 免费 (console.groq.com)",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "description": "DeepSeek (platform.deepseek.com)",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "description": "OpenAI",
    },
}


@dataclass
class DecomposeConfig:
    """Configuration for the decomposition pipeline."""

    # LLM settings
    model: str = "llama-3.1-8b-instant"
    max_tokens: int = 4096
    temperature: float = 0.3
    base_url: str = "https://api.groq.com/openai/v1"

    # Chunking settings
    max_chunk_tokens: int = 8000
    chunk_overlap_tokens: int = 500

    # Arc merge settings
    chapters_per_arc: int = 15

    # Parallelism
    max_parallel_extractions: int = 5
    max_concurrent_extractions: int = 15  # 全并发模式下的最大并发数

    # Output
    output_dir: Path = field(default_factory=lambda: Path("output"))

    # LLM API key (loaded from env if not set)
    api_key: str = ""


@dataclass
class Config:
    decompose: DecomposeConfig = field(default_factory=DecomposeConfig)


default_config = Config()

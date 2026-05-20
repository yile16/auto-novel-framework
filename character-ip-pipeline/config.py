"""Configuration for the Character IP Pipeline."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Master configuration for the entire pipeline."""

    # LLM settings
    model: str = "llama-3.1-8b-instant"
    max_tokens: int = 4096
    temperature: float = 0.3
    base_url: str = "https://api.groq.com/openai/v1"
    api_key: str = ""

    # Agent settings
    max_retries: int = 3  # max retries per agent after quality check failure
    quality_threshold: float = 0.7  # minimum quality score to pass (0-1)

    # Web search settings
    search_api: str = "tavily"  # tavily, serpapi, duckduckgo
    search_api_key: str = ""
    max_search_results: int = 10

    # Media generation settings
    image_api: str = "openai"  # openai (DALL-E), midjourney, stability
    image_size: str = "1024x1024"
    video_api: str = "runway"  # runway, kling
    music_api: str = "suno"  # suno, udio

    # Output
    output_dir: Path = field(default_factory=lambda: Path("projects"))
    auto_approve: bool = False  # skip human review gates if True

    # Parallelism
    max_parallel_agents: int = 3


@dataclass
class ProjectConfig:
    """Per-project configuration."""
    character_name: str
    source: str = ""  # e.g. "西游记原著", "三国演义"
    style: str = "auto"  # visual style: auto, realistic, ink, cyberpunk, dark
    target_platforms: list[str] = field(default_factory=lambda: ["bilibili", "douyin"])
    aspect_ratio: str = "9:16"  # video aspect ratio
    language: str = "zh"  # lyrics language


default_config = PipelineConfig()

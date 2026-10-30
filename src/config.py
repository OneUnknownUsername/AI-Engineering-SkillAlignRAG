"""Local inference defaults; environment cache settings always take precedence."""
import os
from dataclasses import dataclass


@dataclass
class AuditConfig:
    llm_model: str = "Qwen/Qwen2.5-14B-Instruct"
    nli_model: str = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
    backend: str = "hf_local"
    base_url: str = "http://localhost:8000/v1"
    cache_path: str | None = None
    offline: bool = False
    max_input_tokens: int = 12000
    max_new_tokens: int = 128
    pooled_max_new_tokens: int = 140
    input_usd_per_million: float = 0.0
    output_usd_per_million: float = 0.0

    def model_options(self) -> dict:
        # HF_HOME is a root, whereas TRANSFORMERS_CACHE is the weights directory.
        cache = os.environ.get("TRANSFORMERS_CACHE")
        if not cache and os.environ.get("HF_HOME"):
            cache = os.path.join(os.environ["HF_HOME"], "hub")
        cache = cache or self.cache_path
        return {"local_files_only": self.offline, **({"cache_dir": cache} if cache else {})}

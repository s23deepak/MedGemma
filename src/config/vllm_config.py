"""
vLLM Configuration for MedGemma, FunctionGemma, and MedASR

Supports two modes:
- LOCAL: Single GPU (RTX 5060), batch_size=1, optimized for development
- PRODUCTION: Higher throughput, batching, multi-concurrent requests
"""

import os

# Detect environment
_env = os.environ.get("VLLM_ENV", "local").lower()


# ── LOCAL CONFIGURATION (RTX 5060 8GB, batch_size=1) ────────────────────────
VLLM_LOCAL_CONFIG = {
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.85,
    "max_model_len": 2048,              # Simulation context <= 2K tokens
    "max_num_batched_tokens": 512,      # Short patient responses (50-150 tokens)
    "max_num_seqs": 1,                  # Single request only
    "dtype": "bfloat16",
    "quantization": "bitsandbytes",
    "enforce_eager": True,
    "enable_vision": True,
    "limit_mm_per_prompt": {"image": 1},
    "enable_chunked_prefill": True,     
    "enable_prefix_caching": True,                  
}

# Performance expectations (Local):
#   - Q1 (text): ~320ms (includes prefill + generation)
#   - Q1 (with image): ~600-800ms (first image encoding)
#   - Q2+ (text): ~220ms (prefix cache reuse)
#   - Q2+ (with image): ~300-400ms (cached)


# ── PRODUCTION CONFIGURATION (Higher throughput) ─────────────────────────────
VLLM_PRODUCTION_CONFIG = {
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.9,
    "max_model_len": 4096,              # Full clinical context
    "max_num_batched_tokens": 1024,     # Can batch multiple requests
    "max_num_seqs": 4,                  # Allow 4 concurrent requests
    "dtype": "bfloat16",
    "quantization": "bitsandbytes",
    "enforce_eager": True,
    "enable_vision": True,
    "limit_mm_per_prompt": {"image": 1},
    "enable_chunked_prefill": True,     # ← Reduce peak memory during batched prefill
    "enable_prefix_caching": True,      # ← Cache across multi-user sessions
}

# Performance expectations (Production):
#   - Single request: ~280-350ms
#   - Batched (4 concurrent): ~200-250ms per request (amortized)


# ── MODE SELECTION ────────────────────────────────────────────────────────────

def get_vllm_config(mode: str | None = None) -> dict:
    """
    Get vLLM configuration.

    Args:
        mode: "local" or "production". If None, uses VLLM_ENV env var (default: "local").

    Returns:
        Configuration dict for LLM instantiation.
    """
    if mode is None:
        mode = _env

    mode = mode.lower()
    if mode == "production":
        return VLLM_PRODUCTION_CONFIG.copy()
    else:
        return VLLM_LOCAL_CONFIG.copy()


def customize_config(base_config: str = "local", **overrides) -> dict:
    """
    Get base config and apply custom overrides.

    Example:
        config = customize_config("local", max_num_seqs=2, max_model_len=4096)
    """
    config = get_vllm_config(base_config)
    config.update(overrides)
    return config

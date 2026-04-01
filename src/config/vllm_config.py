"""
vLLM Configuration for MedGemma, FunctionGemma, and MedASR

Hardware profiles — select via VLLM_ENV environment variable:
  local       RTX 5060 / any 8 GB GPU  (default)
  l4          NVIDIA L4  24 GB          (cloud single-GPU)
  a100        NVIDIA A100 80 GB         (cloud single-GPU, 27B model)
  multi_gpu   2× L4 / 2× A6000 48 GB   (tensor-parallel, 27B model)

Usage:
  config = get_vllm_config()              # reads VLLM_ENV
  config = get_vllm_config("l4")          # explicit
  config = customize_config("l4", max_num_seqs=4)  # with overrides
"""

import os

# Active profile — set VLLM_ENV on the host or in .env.<hardware>
_env = os.environ.get("VLLM_ENV", "local").lower()


# ── LOCAL  (RTX 5060 8 GB — dev / laptop) ─────────────────────────────────────
_LOCAL = {
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.92,
    "max_model_len": 2048,
    "max_num_batched_tokens": 512,
    "max_num_seqs": 1,
    "dtype": "bfloat16",
    "quantization": "bitsandbytes",     # required to fit 4B in 8 GB
    "enforce_eager": False,
    "enable_vision": True,
    "limit_mm_per_prompt": {"image": 1},
    "enable_chunked_prefill": True,
    "enable_prefix_caching": True,
}
# Q1 text ~320 ms | Q1 image ~600-800 ms | Q2+ text ~220 ms (cache hit)


# ── L4  (NVIDIA L4 Ada 24 GB — cloud single-GPU) ──────────────────────────────
_L4 = {
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.90,
    "max_model_len": 8192,              # full clinical context + history
    "max_num_batched_tokens": 2048,
    "max_num_seqs": 8,                  # 24 GB has plenty of headroom for 4B
    "dtype": "bfloat16",
    "quantization": None,               # not needed — 4B fits natively in 24 GB
    "enforce_eager": False,
    "enable_vision": True,
    "limit_mm_per_prompt": {"image": 1},
    "enable_chunked_prefill": True,
    "enable_prefix_caching": True,
}
# Single request ~180-220 ms | 8 concurrent ~140-180 ms amortised


# ── A100  (NVIDIA A100 80 GB — cloud single-GPU, 27B model) ───────────────────
_A100 = {
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.88,
    "max_model_len": 32768,             # long-context diagnostic reasoning
    "max_num_batched_tokens": 4096,
    "max_num_seqs": 16,
    "dtype": "bfloat16",
    "quantization": None,               # 27B fits in 80 GB natively (~54 GB)
    "enforce_eager": False,
    "enable_vision": True,
    "limit_mm_per_prompt": {"image": 1},
    "enable_chunked_prefill": True,
    "enable_prefix_caching": True,
}
# Single request ~400-600 ms (27B) | batched ~280-380 ms amortised


# ── MULTI-GPU  (2× L4 or 2× A6000 48 GB — tensor parallel, 27B model) ────────
_MULTI_GPU = {
    "tensor_parallel_size": 2,          # split across both GPUs
    "gpu_memory_utilization": 0.88,
    "max_model_len": 32768,
    "max_num_batched_tokens": 4096,
    "max_num_seqs": 16,
    "dtype": "bfloat16",
    "quantization": None,
    "enforce_eager": False,
    "enable_vision": True,
    "limit_mm_per_prompt": {"image": 1},
    "enable_chunked_prefill": True,
    "enable_prefix_caching": True,
}
# 27B across 2× L4 (48 GB total) — single request ~300-450 ms


# ── 4× L4  (4× NVIDIA L4 Ada 24 GB = 96 GB total — high-throughput 27B) ──────
_4XL4 = {
    "tensor_parallel_size": 4,          # split across all 4 GPUs
    "gpu_memory_utilization": 0.88,
    "max_model_len": 65536,             # 64K context — long diagnostic threads
    "max_num_batched_tokens": 8192,
    "max_num_seqs": 32,                 # high concurrent user load
    "dtype": "bfloat16",
    "quantization": None,               # 27B ~54 GB fits with 42 GB left for KV
    "enforce_eager": False,
    "enable_vision": True,
    "limit_mm_per_prompt": {"image": 1},
    "enable_chunked_prefill": True,
    "enable_prefix_caching": True,
}
# 27B across 4× L4 (96 GB total) — single request ~200-300 ms | 32 concurrent


# ── Profile registry ──────────────────────────────────────────────────────────
HARDWARE_PROFILES: dict[str, dict] = {
    "local":      _LOCAL,
    "production": _L4,       # legacy alias — maps to L4
    "l4":         _L4,
    "a100":       _A100,
    "multi_gpu":  _MULTI_GPU,
    "4xl4":       _4XL4,
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_vllm_config(mode: str | None = None) -> dict:
    """
    Return a vLLM config dict for the given hardware profile.

    Args:
        mode: one of "local", "l4", "a100", "multi_gpu" (or legacy "production").
              If None, reads VLLM_ENV env var (default: "local").

    Returns:
        A copy of the config dict — safe to mutate.
    """
    if mode is None:
        mode = _env

    profile = HARDWARE_PROFILES.get(mode.lower())
    if profile is None:
        import warnings
        warnings.warn(
            f"Unknown VLLM_ENV '{mode}', falling back to 'local'. "
            f"Valid options: {list(HARDWARE_PROFILES)}",
            stacklevel=2,
        )
        profile = _LOCAL

    config = profile.copy()
    # vLLM rejects quantization=None — remove the key entirely when not needed
    if config.get("quantization") is None:
        config.pop("quantization", None)
    return config


def customize_config(base_config: str = "local", **overrides) -> dict:
    """
    Get a base hardware profile and apply custom overrides.

    Example:
        config = customize_config("l4", max_num_seqs=4, max_model_len=4096)
    """
    config = get_vllm_config(base_config)
    config.update(overrides)
    return config

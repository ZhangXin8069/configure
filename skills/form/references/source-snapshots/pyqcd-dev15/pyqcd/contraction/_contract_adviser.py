"""收缩成本顾问核心（照抄 refer/sush/lqcddb contraction/contractadviser.py
的成本模型子集：HardwareSpec/ParsedContraction/parse_subscript/
ContractionCost/_estimate_cost_simple/_estimate_cost_via_opt_einsum/
estimate_cost 及缓存抖动常量）。

未移植（登记）：SlicingSuggestion/UpsizingSuggestion/BandwidthAnalysis/
analyze_bandwidth/quick_check/printGPUinfo（Roofline 瓶颈判定与切分建议层）。
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---- 常量（照抄）----
_CACHE_PENALTY_EXPONENT_SIMPLE = 0.25
_CACHE_PENALTY_EXPONENT_MULTI = 0.40

_DTYPE_TABLE = {
    'float16': {'compute_class': 'fp16', 'bytes': 2},
    'float32': {'compute_class': 'fp32', 'bytes': 4},
    'float64': {'compute_class': 'fp64', 'bytes': 8},
    'complex64': {'compute_class': 'fp32', 'bytes': 8},
    'complex128': {'compute_class': 'fp64', 'bytes': 16},
}


@dataclass
class HardwareSpec:
    """硬件规格：存储各精度峰值，根据 dtype 自动选用"""
    name: str
    peak_fp16: float = 0.0
    peak_fp32: float = 0.0
    peak_fp64: float = 0.0
    memory_bandwidth_gbs: float = 0.0
    total_memory_bytes: int = 0
    l2_cache_bytes: int = 0
    compute_efficiency: float = 1.0
    memory_efficiency: float = 1.0
    complex_compute_eff: float = 1.0

    def peak_compute(self, dtype: str) -> float:
        compute_class = _DTYPE_TABLE[dtype]['compute_class']
        return getattr(self, f'peak_{compute_class}')

    def effective_compute(self, dtype: str) -> float:
        base_eff = self.peak_compute(dtype) * self.compute_efficiency
        if 'complex' in dtype:
            base_eff *= self.complex_compute_eff
        return base_eff

    def effective_bandwidth(self) -> float:
        return self.memory_bandwidth_gbs * self.memory_efficiency


@dataclass
class ParsedContraction:
    """解析后的收缩操作信息"""
    subscript: str
    input_subs: List[str]
    output_subs: str
    shapes: List[Tuple[int, ...]]
    index_size: Dict[str, int]
    free_indices: Dict[str, int]
    contracted_indices: Dict[str, int]
    batch_indices: Dict[str, int] = field(default_factory=dict)

    @property
    def n_inputs(self) -> int:
        return len(self.input_subs)

    @property
    def n_free(self) -> int:
        return len(self.free_indices)

    @property
    def n_contracted(self) -> int:
        return len(self.contracted_indices)


def parse_subscript(subscript: str,
                    shapes: List[Tuple[int, ...]]) -> ParsedContraction:
    """解析 opt_einsum 风格下标（显式/隐式/省略号），照抄参照。"""
    if '->' in subscript:
        inputs_part, output_part = subscript.split('->')
    else:
        inputs_part = subscript
        output_part = None

    input_subs = [s_.strip() for s_ in inputs_part.split(',')]
    if len(input_subs) != len(shapes):
        raise ValueError(
            f"输入数量不匹配: 下标有 {len(input_subs)} 个输入, "
            f"但提供了 {len(shapes)} 个形状")

    index_size: Dict[str, int] = {}
    for sub, shape in zip(input_subs, shapes):
        if '...' in sub:
            n_ellipsis = len(shape) - (len(sub) - 3)
            sub_expanded = sub.replace('...', '⋯' * n_ellipsis)
        else:
            sub_expanded = sub
            if len(sub_expanded) != len(shape):
                raise ValueError(
                    f"指标数量与形状维度不匹配: '{sub}' 有 {len(sub)} 个指标, "
                    f"但形状是 {shape} ({len(shape)} 维)")

        for idx_char, size in zip(sub_expanded, shape):
            if idx_char == '⋯':
                continue
            if idx_char in index_size:
                if index_size[idx_char] != size:
                    raise ValueError(
                        f"指标 '{idx_char}' 大小不一致: "
                        f"{index_size[idx_char]} vs {size}")
            else:
                index_size[idx_char] = size

    if output_part is None:
        from collections import Counter
        all_indices = ''.join(input_subs)
        counter = Counter(all_indices.replace(',', '').replace(' ', ''))
        output_part = ''.join(sorted(
            c for c, count in counter.items() if count == 1))
        if not output_part:
            raise ValueError("无法自动推断输出指标: 所有指标都出现了多次。"
                             "请使用 '->' 显式指定输出。")

    all_input_indices = set()
    for sub in input_subs:
        all_input_indices.update(sub)
    output_indices = set(output_part)

    free_indices = {idx: sz for idx, sz in index_size.items()
                    if idx in output_indices}
    contracted_indices = {idx: sz for idx, sz in index_size.items()
                          if idx not in output_indices}

    return ParsedContraction(
        subscript=subscript, input_subs=input_subs,
        output_subs=output_part, shapes=shapes, index_size=index_size,
        free_indices=free_indices, contracted_indices=contracted_indices,
        batch_indices={})


@dataclass
class ContractionCost:
    """收缩操作的成本估算"""
    total_flops: int
    total_read_bytes: int
    total_write_bytes: int
    arithmetic_intensity: float
    ideal_arithmetic_intensity: float
    output_size: int
    cache_penalty: float
    intermediate_write_bytes: int = 0
    peak_working_bytes: int = 0


def _estimate_cost_simple(parsed: ParsedContraction, dtype_bytes: int,
                          flops_per_madd: int):
    contracted_size = 1
    for size in parsed.contracted_indices.values():
        contracted_size *= size
    output_size = 1
    for size in parsed.free_indices.values():
        output_size *= size
    total_input_elements = sum(int(np.prod(s)) if len(s) else 1
                               for s in [tuple(x) for x in parsed.shapes])
    total_flops = flops_per_madd * output_size * contracted_size
    total_read_bytes = total_input_elements * dtype_bytes
    total_write_bytes = output_size * dtype_bytes
    peak_working_bytes = total_read_bytes + total_write_bytes
    return (total_flops, total_read_bytes, total_write_bytes,
            peak_working_bytes, 0)


def _estimate_cost_via_opt_einsum(parsed: ParsedContraction,
                                  dtype_bytes: int, flops_per_madd: int,
                                  optimize: str = 'auto'):
    import opt_einsum as oe

    try:
        _, path_info = oe.contract_path(
            parsed.subscript, *parsed.shapes, shapes=True,
            optimize=optimize)
    except Exception:
        return _estimate_cost_simple(parsed, dtype_bytes, flops_per_madd)

    total_flops = int(path_info.opt_cost * flops_per_madd)

    total_input_elements = sum(int(np.prod(s)) if len(s) else 1
                               for s in [tuple(x) for x in parsed.shapes])
    intermediate_elements = sum(path_info.size_list)
    peak_intermediate = max(path_info.size_list) if path_info.size_list else 0

    total_io_elements = total_input_elements + intermediate_elements
    total_read_bytes = total_io_elements * dtype_bytes

    output_size = 1
    for size in parsed.free_indices.values():
        output_size *= size
    total_write_bytes = output_size * dtype_bytes

    intermediate_write_elements = (
        intermediate_elements - path_info.size_list[-1]
        if path_info.size_list else 0)
    intermediate_write_bytes = int(intermediate_write_elements * dtype_bytes)
    peak_working_bytes = int((total_input_elements + peak_intermediate)
                             * dtype_bytes)

    return (total_flops, total_read_bytes, total_write_bytes,
            peak_working_bytes, intermediate_write_bytes)


def estimate_cost(parsed: ParsedContraction, hw: HardwareSpec = None,
                  dtype_bytes: int = 4, flops_per_madd: int = 2,
                  optimize: str = 'auto') -> ContractionCost:
    """估算张量收缩的计算与搬运成本（照抄参照，含缓存抖动模型）。"""
    output_size = 1
    for size in parsed.free_indices.values():
        output_size *= size

    if parsed.n_inputs <= 2:
        (total_flops, ideal_read_bytes, total_write_bytes,
         peak_working_bytes, intermediate_write_bytes) = \
            _estimate_cost_simple(parsed, dtype_bytes, flops_per_madd)
    else:
        try:
            (total_flops, ideal_read_bytes, total_write_bytes,
             peak_working_bytes, intermediate_write_bytes) = \
                _estimate_cost_via_opt_einsum(parsed, dtype_bytes,
                                              flops_per_madd,
                                              optimize=optimize)
        except Exception:
            (total_flops, ideal_read_bytes, total_write_bytes,
             peak_working_bytes, intermediate_write_bytes) = \
                _estimate_cost_simple(parsed, dtype_bytes, flops_per_madd)

    ideal_data_bytes = (ideal_read_bytes + total_write_bytes
                        + intermediate_write_bytes)
    ideal_ai = total_flops / ideal_data_bytes if ideal_data_bytes > 0 \
        else float('inf')

    cache_penalty = 1.0
    cache_exponent = (_CACHE_PENALTY_EXPONENT_MULTI if parsed.n_inputs > 2
                      else _CACHE_PENALTY_EXPONENT_SIMPLE)
    if hw is not None and hw.l2_cache_bytes > 0:
        if peak_working_bytes > hw.l2_cache_bytes:
            cache_ratio = peak_working_bytes / hw.l2_cache_bytes
            cache_penalty = cache_ratio ** cache_exponent

    effective_read_bytes = ideal_read_bytes * cache_penalty
    effective_write_bytes = (total_write_bytes
                             + intermediate_write_bytes) * cache_penalty
    effective_data_bytes = effective_read_bytes + effective_write_bytes
    effective_ai = total_flops / effective_data_bytes \
        if effective_data_bytes > 0 else float('inf')

    return ContractionCost(
        total_flops=total_flops,
        total_read_bytes=ideal_read_bytes,
        total_write_bytes=total_write_bytes,
        intermediate_write_bytes=int(intermediate_write_bytes),
        arithmetic_intensity=effective_ai,
        ideal_arithmetic_intensity=ideal_ai,
        output_size=output_size,
        cache_penalty=cache_penalty,
        peak_working_bytes=int(peak_working_bytes),
    )


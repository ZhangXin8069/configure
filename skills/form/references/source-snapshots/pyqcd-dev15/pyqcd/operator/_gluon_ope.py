"""
胶子算符：Clover 场强张量 + Wilson 线的非定域胶子 OPE 算符
=============================================================

实现（照抄 docker-v20260805 ``compute_ope.py`` 的 donghx 算法，不改逻辑）：

    O_{μν}(z) = Σ_{x⊥} Tr[ F_{μν}(x + z) · W†(z→0) · F̃_{μν}(x) · W(0→z) ]

其中 F̃_{μν} = ½ ε_{μνρσ} F_{ρσ} 为对偶场强张量，W 为沿 z 方向的 Wilson 线
（roll 链接乘积构造）。

``gluon_ope_operator_z0`` 的 legacy OPE 明确使用 finite-a、未去迹的
``plaquette_clover`` 基元；``OPEChannelSpec.field_projection`` 因而固定记录为
``legacy_untraced``。它不等同于 ``pyqcd.gauge.clover_field_strength`` 的
SU(N) 无迹观测量，也不等同于 TMD bilocal 的场强投影。

TMD 扩展（本库新增，供梯度流重整化 TMD-PDF 使用）：
    ``staple_operator`` 导出同一 Lorentz 对的规范不变 staple 双场强双局域量；
    完整非极化 transverse 组合 M^{ti;ti} + M^{tj;tj} − 2M^{ij;ij} 位于
    ``pyqcd.renorm._tmd``。

张量约定：gauge 为 (Nt, Nz, Ny, Nx, 4, 3, 3)（t,z,y,x 序，与成功实例一致）。
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import os

import numpy as np

from ..tools._backend import get_backend, get_backend_name


def _to_cpu(x):
    """后端无关的 GPU→CPU 转换（cupy 禁止 np.asarray 隐式转换，须用 asnumpy/get）。"""
    b = get_backend()
    asnumpy = getattr(b, 'asnumpy', None)
    if asnumpy is not None:
        return asnumpy(x)
    getter = getattr(x, 'get', None)
    if getter is not None:
        return getter()
    return np.asarray(x)


def _validate_lorentz_direction(direction, name="direction"):
    """Validate a Lorentz/link direction: integer labels 0=x,...,3=t."""
    if (isinstance(direction, (bool, np.bool_))
            or not isinstance(direction, (int, np.integer))):
        raise ValueError(
            f"{name} 必须是非布尔 Lorentz 整数 0=x, 1=y, 2=z, 3=t")
    direction = int(direction)
    if direction not in (0, 1, 2, 3):
        raise ValueError(
            f"{name} 必须属于 0=x, 1=y, 2=z, 3=t")
    return direction


def _validate_lorentz_pair(mu, nu):
    """Return a validated off-diagonal Lorentz pair."""
    mu = _validate_lorentz_direction(mu, "mu")
    nu = _validate_lorentz_direction(nu, "nu")
    if mu == nu:
        raise ValueError("场强 Lorentz 对必须满足 mu != nu")
    return mu, nu


def _validate_spatial_direction(direction, name="z_dir"):
    """Validate a spatial path direction: integer labels 0=x,1=y,2=z."""
    direction = _validate_lorentz_direction(direction, name)
    if direction == 3:
        raise ValueError(f"{name} 必须是空间方向 0=x, 1=y, 2=z")
    return direction


def _validate_ope_direction(direction, name="direction"):
    """Validate the sign of a straight Wilson-line direction."""
    if (isinstance(direction, (bool, np.bool_))
            or not isinstance(direction, (int, np.integer))):
        raise ValueError(f"{name} 必须是非布尔整数 +1 或 -1")
    direction = int(direction)
    if direction not in (-1, 1):
        raise ValueError(f"{name} 必须属于 +1 或 -1")
    return direction


def _validate_ope_enum(value, allowed, name):
    """Validate a closed string enum without silently selecting a fallback."""
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{name} 必须是 {{{choices}}} 中的字符串")
    return value


_OPE_MODES = frozenset(("legacy_dual", "unpolarized", "helicity", "custom"))
_OPE_INSERTS = frozenset(("F", "Ftilde"))
_OPE_SUM_KINDS = frozenset(("full",))
_OPE_NORMALIZATIONS = frozenset(("bare_spatial_sum",))
_OPE_PROJECTIONS = frozenset(("real", "complex"))
_OPE_FIELD_PROJECTIONS = frozenset(("legacy_untraced",))
_OPE_PAIR_MODES = frozenset((
    "unpol", "helicity", "gauge_fix_unpol", "gauge_fix_helicity"))


@dataclass(frozen=True)
class OPEChannelSpec:
    """Fully explicit metadata for one straight-line gluon OPE channel.

    ``field_projection='legacy_untraced'`` records the finite-spacing Clover
    primitive used by the docker legacy path.  This release deliberately does
    not implement a traceless OPE field, so every other field projection is
    rejected instead of being conflated with ``pyqcd.gauge``'s SU(N)-projected
    observable or a TMD bilocal.

    The mode constrains only the insertion family: ``unpolarized`` means
    ``F.F`` and ``helicity``/``legacy_dual`` mean ``F.Ftilde``.  Direction and
    output projection remain explicit independent fields; no unproved
    relation between the +z and -z channels is inferred from the mode.
    """

    mode: str
    mu: int
    nu: int
    mu2: int
    nu2: int
    z_dir: int
    second_insert: str
    direction: int
    sum_kind: str
    normalization: str
    output_projection: str
    field_projection: str

    def __post_init__(self):
        mode = _validate_ope_enum(self.mode, _OPE_MODES, "mode")
        mu, nu = _validate_lorentz_pair(self.mu, self.nu)
        mu2, nu2 = _validate_lorentz_pair(self.mu2, self.nu2)
        z_dir = _validate_spatial_direction(self.z_dir, "z_dir")
        second_insert = _validate_ope_enum(
            self.second_insert, _OPE_INSERTS, "second_insert")
        direction = _validate_ope_direction(self.direction)
        sum_kind = _validate_ope_enum(self.sum_kind, _OPE_SUM_KINDS, "sum_kind")
        normalization = _validate_ope_enum(
            self.normalization, _OPE_NORMALIZATIONS, "normalization")
        output_projection = _validate_ope_enum(
            self.output_projection, _OPE_PROJECTIONS, "output_projection")
        field_projection = _validate_ope_enum(
            self.field_projection, _OPE_FIELD_PROJECTIONS, "field_projection")

        expected_insert = {
            "legacy_dual": "Ftilde",
            "unpolarized": "F",
            "helicity": "Ftilde",
        }.get(mode)
        if expected_insert is not None and second_insert != expected_insert:
            raise ValueError(
                f"mode={mode} 与 second_insert={second_insert} 自相矛盾；"
                f"该 mode 要求 {expected_insert}")

        for name, value in (
                ("mode", mode), ("mu", mu), ("nu", nu),
                ("mu2", mu2), ("nu2", nu2), ("z_dir", z_dir),
                ("second_insert", second_insert), ("direction", direction),
                ("sum_kind", sum_kind), ("normalization", normalization),
                ("output_projection", output_projection),
                ("field_projection", field_projection)):
            object.__setattr__(self, name, value)

    def to_dict(self):
        """Return a JSON-serializable copy of every channel semantic."""
        return {
            "mode": self.mode,
            "mu": self.mu,
            "nu": self.nu,
            "mu2": self.mu2,
            "nu2": self.nu2,
            "z_dir": self.z_dir,
            "second_insert": self.second_insert,
            "direction": self.direction,
            "sum_kind": self.sum_kind,
            "normalization": self.normalization,
            "output_projection": self.output_projection,
            "field_projection": self.field_projection,
        }


def _array_backend_name(array):
    """Return the concrete array family used by the active backend."""
    if isinstance(array, np.ndarray):
        return "numpy"
    module = type(array).__module__
    if module.startswith("cupy"):
        return "cupy"
    if module.startswith("torch"):
        return "torch"
    return None


def _dtype_token(dtype):
    """Make NumPy and Torch dtypes comparable without coercing arrays."""
    try:
        return np.dtype(dtype).str
    except TypeError:
        return str(dtype)


def _numpy_output_dtype(dtype):
    """Map an active-backend dtype to the NumPy dtype used by OPE outputs."""
    try:
        return np.dtype(dtype)
    except (TypeError, ValueError):
        name = getattr(dtype, "name", None)
        if name is None:
            name = str(dtype).rsplit(".", 1)[-1]
        try:
            return np.dtype(name)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"Unsupported OPE output dtype: {dtype!r}") from exc


def _validate_compute_dtype(compute_dtype, gauge_dtype):
    """Resolve an OPE output dtype while preserving complex precision."""
    resolved = _numpy_output_dtype(
        gauge_dtype if compute_dtype is None else compute_dtype)
    if resolved not in (np.dtype("complex64"), np.dtype("complex128")):
        raise TypeError(
            "OPE compute_dtype 必须是 complex64 或 complex128；"
            f"收到 {compute_dtype if compute_dtype is not None else gauge_dtype!r}")
    return resolved


def _validate_lattice_extent(value, name, minimum):
    """Validate a lattice extent before it reaches array allocation/rolling."""
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))):
        raise ValueError(f"{name} 必须是非布尔整数")
    value = int(value)
    if value < minimum:
        relation = ">= 0" if minimum == 0 else ">= 1"
        raise ValueError(f"{name} 必须 {relation}")
    return value


def _array_device_token(array, backend_name):
    """Return the device identity relevant to a concrete gauge array."""
    if backend_name == "torch":
        return str(getattr(array, "device", "unknown"))
    if backend_name == "cupy":
        device = getattr(array, "device", None)
        return getattr(device, "id", str(device))
    return None


def _torch_version(array):
    """Read Torch's O(1) in-place mutation counter when available."""
    version = getattr(array, "_version", None)
    try:
        return None if version is None else int(version)
    except (TypeError, ValueError, RuntimeError):
        return None


def _active_device_token(backend_name):
    """Return the active backend's default device in cache-comparable form."""
    if backend_name == "torch":
        backend = get_backend()
        configured = backend.get_device()
        if configured is None:
            return "cpu"
        try:
            device = backend.torch.device(configured)
            if device.type == "cuda" and device.index is None:
                return f"cuda:{backend.torch.cuda.current_device()}"
            return str(device)
        except (RuntimeError, TypeError, ValueError):
            return str(configured)
    if backend_name == "cupy":
        return int(get_backend().cuda.Device().id)
    return None


class FieldStrengthCache:
    """Lazy, bounded LRU cache for canonical Clover fields.

    The cache strongly owns the exact ``gauge`` object supplied at
    construction and stores only canonical entries ``(mu, nu)`` with
    ``mu < nu``.  A reversed request returns ``-F_{mu nu}`` without another
    Clover evaluation.  ``max_entries`` defaults to all six independent
    fields for compatibility, and may be reduced to bound resident memory.
    This bound covers only references owned by the cache; references retained
    by callers are outside the cache-owned residency limit.
    The cache is also bound to the gauge's concrete backend, device, dtype,
    shape, and optional ``flow_time`` token.  A context mismatch is rejected
    rather than silently reusing tensors from another execution context.

    Cached tensors stay on the active NumPy/CuPy/Torch backend.  The owner is
    responsible for its lifetime: a full lattice tensor costs approximately
    ``Nt*Nz*Ny*Nx*Nc*Nc*sizeof(dtype)`` bytes, and ``max_entries`` such
    tensors can be a material GPU allocation.  Call ``clear()`` after the
    consuming step (or let the object go out of scope) to drop those tensor
    references.  The caller declares the gauge immutable while the cache is
    live; after a controlled same-shape/dtype in-place update, call
    ``refresh()`` before requesting a field.  NumPy and CuPy have no O(1)
    mutation counter, so the cache deliberately does not scan or checksum the
    full gauge on every hit.  Torch's ``_version`` counter is checked in O(1)
    and invalidates fields for Torch-tracked in-place writes; writes through
    an external alias still require ``refresh()``.
    """

    def __init__(self, gauge, *, flow_time=None, gauge_immutable=True,
                 max_entries=6):
        if (not isinstance(gauge_immutable, (bool, np.bool_))
                or not bool(gauge_immutable)):
            raise ValueError(
                "FieldStrengthCache 当前只支持 gauge_immutable=True；"
                "可控变更请先更新 gauge 再调用 refresh()")
        if (isinstance(max_entries, (bool, np.bool_))
                or not isinstance(max_entries, (int, np.integer))
                or not 1 <= int(max_entries) <= 6):
            raise ValueError("max_entries 必须是 1..6 的非布尔整数")
        backend_name = get_backend_name()
        concrete_backend = _array_backend_name(gauge)
        if concrete_backend != backend_name:
            raise ValueError(
                "FieldStrengthCache 的 gauge backend 必须与 active backend 一致: "
                f"expected {backend_name}, got {concrete_backend}")
        self._gauge = gauge
        self._flow_time = flow_time
        self._gauge_immutable = bool(gauge_immutable)
        self._max_entries = int(max_entries)
        self._backend_name = backend_name
        self._device = _array_device_token(gauge, backend_name)
        if _active_device_token(backend_name) != self._device:
            raise ValueError(
                "FieldStrengthCache 的 active device 与 gauge device 不一致")
        self._dtype = gauge.dtype
        self._dtype_token = _dtype_token(gauge.dtype)
        self._shape = tuple(gauge.shape)
        self._torch_gauge_version = (
            _torch_version(gauge) if backend_name == "torch" else None)
        self._fields = OrderedDict()

    @property
    def cached_pairs(self):
        """Canonical field pairs currently resident, in deterministic order."""
        return tuple(sorted(self._fields))

    @property
    def gauge(self):
        """The exact gauge object to which this cache is bound."""
        return self._gauge

    @property
    def flow_time(self):
        """The optional flow-time identity bound at construction."""
        return self._flow_time

    @property
    def backend(self):
        """The concrete backend name bound at construction."""
        return self._backend_name

    @property
    def device(self):
        """The gauge device identity bound at construction."""
        return self._device

    @property
    def dtype(self):
        """The exact gauge dtype bound at construction."""
        return self._dtype

    @property
    def gauge_immutable(self):
        """Whether the caller declared the bound gauge immutable."""
        return self._gauge_immutable

    @property
    def max_entries(self):
        """Maximum number of canonical full-field tensors kept resident."""
        return self._max_entries

    @property
    def mutation_detection(self):
        """Describe the mutation contract used for this cache."""
        if self._torch_gauge_version is not None:
            return "torch_version"
        return "immutable_refresh"

    @staticmethod
    def _same_flow_time(expected, actual):
        if expected is actual:
            return True
        try:
            return bool(expected == actual)
        except (TypeError, ValueError):
            return False

    def _validate_context(self, gauge, flow_time):
        if gauge is not None and gauge is not self._gauge:
            raise ValueError(
                "FieldStrengthCache 只能用于构造它的同一 gauge 对象")
        if not self._same_flow_time(self._flow_time, flow_time):
            raise ValueError(
                "FieldStrengthCache 的 flow_time 与请求不一致；"
                "请为每个流时间显式创建新 cache")
        concrete_backend = _array_backend_name(self._gauge)
        if (get_backend_name() != self._backend_name
                or concrete_backend != self._backend_name):
            raise ValueError(
                "FieldStrengthCache 的 active/concrete backend 与绑定上下文不一致")
        if _array_device_token(self._gauge, self._backend_name) != self._device:
            raise ValueError("FieldStrengthCache 的 gauge device 与绑定上下文不一致")
        if _active_device_token(self._backend_name) != self._device:
            raise ValueError(
                "FieldStrengthCache 的 active device 与绑定上下文不一致")
        if _dtype_token(self._gauge.dtype) != self._dtype_token:
            raise ValueError("FieldStrengthCache 的 gauge dtype 已改变")
        if tuple(self._gauge.shape) != self._shape:
            raise ValueError("FieldStrengthCache 的 gauge shape 已改变")

    def _check_torch_version(self):
        if self._torch_gauge_version is None:
            return
        version = _torch_version(self._gauge)
        if version != self._torch_gauge_version:
            self.clear()
            self._torch_gauge_version = version

    def get(self, mu, nu, *, gauge=None, flow_time=None):
        """Return ``F_{mu nu}``, evaluating one canonical Clover field lazily."""
        mu, nu = _validate_lorentz_pair(mu, nu)
        self._validate_context(gauge, flow_time)
        self._check_torch_version()
        canonical = (mu, nu) if mu < nu else (nu, mu)
        if canonical in self._fields:
            field = self._fields[canonical]
            self._fields.move_to_end(canonical)
        else:
            # Evict before evaluating the full lattice field, so a miss never
            # makes cache-owned residency exceed max_entries even transiently.
            if len(self._fields) >= self._max_entries:
                self._fields.popitem(last=False)
            field = plaquette_clover(
                self._gauge, canonical[0], canonical[1])
            self._fields[canonical] = field
        return field if mu < nu else -field

    def refresh(self, *, gauge=None, flow_time=None):
        """Invalidate fields after a caller-controlled gauge update.

        NumPy/CuPy arrays have no mutation counter that can be read in O(1),
        and Torch writes through external aliases can bypass ``_version``.
        Call this method after such an update; changed dtype/shape/device or
        object identity still requires constructing a new cache.
        """
        self._validate_context(gauge, flow_time)
        self.clear()
        self._torch_gauge_version = _torch_version(self._gauge)
        return self

    def clear(self):
        """Drop all cached field tensors while retaining ownership metadata."""
        self._fields.clear()


# ═══════════════════════════════════════════════════════════════════
# Tensor4 = ½ ε_{μνρσ}（Levi-Civita，系数查表）
# ═══════════════════════════════════════════════════════════════════

def build_tensor4() -> np.ndarray:
    """Build Tensor4[μ,ν,ρ,σ] = ½·ε_{μνρσ}（donghx Operator.py 原版）。"""
    T = np.zeros((4, 4, 4, 4), dtype=np.float64)
    for i in range(4):
        for j in range(4):
            a = 1.0 if i > j else 0.0
            for k in range(4):
                b = (1.0 if i > k else 0.0) + (1.0 if j > k else 0.0)
                for l in range(4):
                    c = ((1.0 if i > l else 0.0)
                         + (1.0 if j > l else 0.0)
                         + (1.0 if k > l else 0.0))
                    if len({i, j, k, l}) == 4:
                        T[i, j, k, l] = 1.0 if int(a + b + c) % 2 == 0 else -1.0
    return 0.5 * T


_TENSOR4 = build_tensor4()


def plaquette_clover(g, mu: int, nu: int):
    """F_{μν} = -i/8 Σ_k (P_k - P_k†)，四叶 Clover 平均（donghx）。

    Args:
        g: gauge，形状 (Nt,Nz,Ny,Nx,4,3,3)，CPU(ndarray) 或 GPU(cupy)。
        mu, nu: 链接/Lorentz 方向标签 (0=x, 1=y, 2=z, 3=t)，mu != nu；
                对应规范场坐标轴为 ``3-mu`` / ``3-nu``。
    Returns:
        F_{μν}，形状 (Nt,Nz,Ny,Nx,3,3)。
    """
    mu, nu = _validate_lorentz_pair(mu, nu)
    reverse = mu > nu
    if reverse:
        mu, nu = nu, mu
    cp = get_backend()
    m = cp.matmul
    a_mu = 3 - mu   # 空间轴
    a_nu = 3 - nu

    g_lu = cp.roll(g, 1, axis=a_mu)
    g_rd = cp.roll(g, 1, axis=a_nu)
    g_ld = cp.roll(g_lu, 1, axis=a_nu)

    tr = (0, 1, 2, 3, 5, 4)  # 共轭转置（色指标 Hermitian 共轭）

    # P1 = P_{μν}（einsum→cuBLAS matmul 等价改写，逐位一致）
    p1 = m(g[..., mu, :, :],
           cp.roll(g, -1, axis=a_mu)[..., nu, :, :])
    p1 = m(p1, cp.roll(g, -1, axis=a_nu)[..., mu, :, :].conj()
           .transpose(*tr))
    p1 = m(p1, g[..., nu, :, :].conj().transpose(*tr))

    # P2 = P_{ν,-μ}
    p2 = m(cp.roll(g_lu, -1, axis=a_mu)[..., nu, :, :],
           cp.roll(g_lu, -1, axis=a_nu)[..., mu, :, :].conj()
           .transpose(*tr))
    p2 = m(p2, g_lu[..., nu, :, :].conj().transpose(*tr))
    p2 = m(p2, g_lu[..., mu, :, :])

    # P3 = P_{-μ,-ν}
    p3 = m(cp.roll(g_ld, -1, axis=a_nu)[..., mu, :, :].conj()
           .transpose(*tr),
           g_ld[..., nu, :, :].conj().transpose(*tr))
    p3 = m(p3, g_ld[..., mu, :, :])
    p3 = m(p3, cp.roll(g_ld, -1, axis=a_mu)[..., nu, :, :])

    # P4 = P_{-ν,μ}
    p4 = m(g_rd[..., nu, :, :].conj().transpose(*tr),
           g_rd[..., mu, :, :])
    p4 = m(p4, cp.roll(g_rd, -1, axis=a_mu)[..., nu, :, :])
    p4 = m(p4, cp.roll(g_rd, -1, axis=a_nu)[..., mu, :, :].conj()
           .transpose(*tr))

    ans = (p1 - p1.conj().transpose(*tr)
           + p2 - p2.conj().transpose(*tr)
           + p3 - p3.conj().transpose(*tr)
           + p4 - p4.conj().transpose(*tr))
    field = (cp.array(-1j, dtype=ans.dtype) * ans
             / cp.array(8.0, dtype=ans.real.dtype))
    return -field if reverse else field


def compute_dual_field_strength(F_dict: dict, mu: int, nu: int):
    """F̃_{μν} = ½ Σ_{ρσ} ε_{μνρσ} F_{ρσ}。"""
    mu, nu = _validate_lorentz_pair(mu, nu)
    cp = get_backend()
    result = None
    for rho in range(4):
        for sigma in range(4):
            coeff = _TENSOR4[mu, nu, rho, sigma]
            if abs(coeff) < 1e-10 or rho == sigma:
                continue
            F_rs = _lookup_field(F_dict, rho, sigma)
            if F_rs is None:
                continue
            term = cp.array(coeff, dtype=F_rs.dtype) * F_rs
            result = term if result is None else result + term
    return result


def _canonical_pair(mu, nu):
    """Return the unique stored key for an antisymmetric Lorentz pair."""
    mu, nu = _validate_lorentz_pair(mu, nu)
    return (mu, nu) if mu < nu else (nu, mu)


def _lookup_field(F_dict, mu, nu):
    """Read an ordered field from canonical storage with its antisymmetric sign.

    Exact ordered keys are still accepted for compatibility with callers that
    construct a legacy dictionary themselves.  The OPE implementation itself
    stores only canonical keys, so a reverse lookup is a sign operation and
    never an additional Clover evaluation.
    """
    mu, nu = _validate_lorentz_pair(mu, nu)
    exact = F_dict.get((mu, nu))
    if exact is not None:
        return exact
    canonical = _canonical_pair(mu, nu)
    field = F_dict.get(canonical)
    if field is not None:
        return field if mu < nu else -field
    reverse = F_dict.get((nu, mu))
    if reverse is not None:
        return -reverse
    return None


def _canonicalize_pairs(pairs):
    """Canonicalize and deduplicate a collection of Lorentz pairs."""
    return {_canonical_pair(mu, nu) for mu, nu in pairs}


def _field_strength(gauge, mu, nu, field_strength_cache=None,
                    flow_time=None):
    """Resolve one ordered field through an explicit cache when supplied."""
    mu, nu = _validate_lorentz_pair(mu, nu)
    if field_strength_cache is None:
        canonical = _canonical_pair(mu, nu)
        field = plaquette_clover(gauge, canonical[0], canonical[1])
        return field if mu < nu else -field
    return field_strength_cache.get(
        mu, nu, gauge=gauge, flow_time=flow_time)


def gluon_ope_operator_z0(gauge, mu: int, nu: int, z_dir: int, delta_z: int,
                          Nt: int, Nx: int, compute_dtype=None, *,
                          mu2: int | None = None, nu2: int | None = None,
                          direction: int = 1,
                          second_insert: str = "Ftilde",
                          field_strength_cache: FieldStrengthCache | None = None,
                          flow_time=None, sum_kind: str = "full",
                          normalization: str = "bare_spatial_sum",
                          output_projection: str | None = None,
                          field_projection: str = "legacy_untraced"):
    """O_{μν;μ₂ν₂}(z)（z = 0..delta_z-1，全部时间片）。

    默认 F_{μν}(z)·W†·F̃_{μν}(0)·W（+z Wilson 线，照抄 compute_ope.py 的
    donghx roll 算法）。扩展参数（照抄 zhangxin workflow / Operator.py）：

    - ``mu2/nu2``：F̃ 插入的独立 Lorentz 对（gauge_fix_helicity 交叉混合，
      如 (3,0;2,1)）；默认与 (mu, nu) 相同。
    - ``direction=-1``：负 z 方向 Wilson 线变体
      （Operator.py ``operators_new_z0_mz_mu2``：F(−z)·W(−z→0)·F̃(0)·W†）。
    - ``field_strength_cache``：可选的、显式绑定本次 gauge/flow time 的
      ``FieldStrengthCache``；不传时保留逐通道的原有 Clover 调用路径。
    - ``flow_time``：传给显式 cache 的身份 token，不参与数值计算。
    - ``sum_kind`` / ``normalization``：当前只支持 ``full`` 空间求和与
      ``bare_spatial_sum``，显式列出以避免把不同观测量混写。
    - ``output_projection``：``"real"`` 保留 legacy 实部投影，``"complex"``
      保留复数；省略时使用旧规则（同对 +z 为实部，其余为复数）。
    - ``field_projection``：当前仅支持 ``"legacy_untraced"``，即有限格距
      ``plaquette_clover`` 原始场强；本函数不冒充 ``pyqcd.gauge`` 的无迹
      SU(N) Clover 观测量。

    返回 (delta_z, Nt) 数组；省略 ``output_projection`` 时，同对 +z 保持原版
    实数行为，交叉对或 −z 为复数；显式投影优先于该 legacy 推断。
    """
    cp = get_backend()
    delta_z = _validate_lattice_extent(delta_z, "delta_z", 0)
    Nt = _validate_lattice_extent(Nt, "Nt", 1)
    Nx = _validate_lattice_extent(Nx, "Nx", 1)
    compute_dtype = _validate_compute_dtype(compute_dtype, gauge.dtype)
    mu, nu = _validate_lorentz_pair(mu, nu)
    if mu2 is None:
        mu2 = mu
    if nu2 is None:
        nu2 = nu
    mu2, nu2 = _validate_lorentz_pair(mu2, nu2)
    z_dir = _validate_spatial_direction(z_dir, "z_dir")
    direction = _validate_ope_direction(direction)
    second_insert = _validate_ope_enum(
        second_insert, _OPE_INSERTS, "second_insert")
    _validate_ope_enum(sum_kind, _OPE_SUM_KINDS, "sum_kind")
    _validate_ope_enum(
        normalization, _OPE_NORMALIZATIONS, "normalization")
    if output_projection is not None:
        output_projection = _validate_ope_enum(
            output_projection, _OPE_PROJECTIONS, "output_projection")
    field_projection = _validate_ope_enum(
        field_projection, _OPE_FIELD_PROJECTIONS, "field_projection")

    z_axis = 3 - z_dir   # Wilson 线方向的空间轴
    cross = (mu2 != mu) or (nu2 != nu)
    complex_out = (
        bool(cross or direction < 0)
        if output_projection is None else output_projection == "complex")

    need_pairs = {_canonical_pair(mu, nu)}
    if second_insert == "F":
        need_pairs.add(_canonical_pair(mu2, nu2))
    else:
        dual_pairs = []
        for rho in range(4):
            for sigma in range(4):
                if abs(_TENSOR4[mu2, nu2, rho, sigma]) > 1e-10 \
                        and rho != sigma:
                    dual_pairs.append((rho, sigma))
        need_pairs.update(_canonicalize_pairs(dual_pairs))

    F_dict = {pair: _field_strength(
                  gauge, pair[0], pair[1], field_strength_cache, flow_time)
              for pair in sorted(need_pairs)}
    F = _lookup_field(F_dict, mu, nu)
    if second_insert == "Ftilde":
        F_second = compute_dual_field_strength(F_dict, mu2, nu2)
    else:
        F_second = _lookup_field(F_dict, mu2, nu2)
    del F_dict

    if F is None or F_second is None:
        raise ValueError("OPE 所需的场强未能从 canonical field dictionary 解析")

    U_z = gauge[..., z_dir, :, :]   # (Nt,Nz,Ny,Nx,3,3)

    spatial_axes = (1, 2, 3)
    out_dtype = np.complex128 if complex_out else np.float64
    ope = np.zeros((delta_z, Nt), dtype=out_dtype)

    def _store(zi, arr_cpu):
        ope[zi] = arr_cpu if complex_out else arr_cpu.real

    for zi in range(delta_z):
        if zi == 0:
            ope_t = cp.einsum("tzyxab,tzyxba->tzyx", F, F_second)
            _store(0, _to_cpu(cp.sum(ope_t, axis=spatial_axes)))
            continue

        if direction > 0:
            # +z：F(+z)·U† 链 → F_second(0) → U 链（compute_ope.py 原算法）
            ope_t = cp.roll(F, -zi, axis=z_axis)
            for step in range(zi):
                U_conj = cp.roll(U_z, -(zi - 1 - step), axis=z_axis).conj()
                ope_t = cp.matmul(ope_t, U_conj.transpose(0, 1, 2, 3, 5, 4))
            ope_t = cp.matmul(ope_t, F_second)
            for step in range(zi):
                U_fwd = cp.roll(U_z, -step, axis=z_axis)
                ope_t = cp.matmul(ope_t, U_fwd)
        else:
            # −z（operators_new_z0_mz_mu2）：F(−z)·U 链 → F_second(0)
            # → U† 链。这里只由显式 direction 控制，不推断共轭关系。
            ope_t = cp.roll(F, zi, axis=z_axis)
            for step in range(zi):
                U_k = cp.roll(U_z, zi - step, axis=z_axis)
                ope_t = cp.matmul(ope_t, U_k)
            ope_t = cp.matmul(ope_t, F_second)
            for step in range(zi):
                Uc_k = cp.roll(U_z, step + 1, axis=z_axis).conj()
                ope_t = cp.matmul(ope_t, Uc_k.transpose(0, 1, 2, 3, 5, 4))

        trace = cp.einsum("...aa->...", ope_t)
        _store(zi, _to_cpu(cp.sum(trace, axis=spatial_axes)))

    return ope.astype(compute_dtype)


def gluon_ope_channel(gauge, channel, delta_z: int, Nt: int, Nx: int,
                      compute_dtype=None, *, field_strength_cache=None,
                      flow_time=None, _operator=None):
    """Evaluate one OPE from a fully explicit :class:`OPEChannelSpec`.

    The wrapper deliberately forwards every channel semantic, including the
    field projection and the two normalization labels, to the legacy kernel.
    ``_operator`` is an internal dependency-injection hook used by the
    pipeline's compatibility contract; ordinary callers should leave it
    unset.
    """
    if not isinstance(channel, OPEChannelSpec):
        raise TypeError("channel 必须是 OPEChannelSpec 实例")
    compute_dtype = _validate_compute_dtype(compute_dtype, gauge.dtype)
    operator = gluon_ope_operator_z0 if _operator is None else _operator
    if not callable(operator):
        raise TypeError("_operator 必须是可调用对象")
    return operator(
        gauge, channel.mu, channel.nu, channel.z_dir, delta_z, Nt, Nx,
        compute_dtype,
        mu2=channel.mu2,
        nu2=channel.nu2,
        direction=channel.direction,
        second_insert=channel.second_insert,
        field_strength_cache=field_strength_cache,
        flow_time=flow_time,
        sum_kind=channel.sum_kind,
        normalization=channel.normalization,
        output_projection=channel.output_projection,
        field_projection=channel.field_projection)


def gluon_ff_operator_z0(gauge, mu: int, nu: int, delta_z: int,
                         Nt: int, Nx: int, *, mu2: int | None = None,
                         nu2: int | None = None, direction: int = 1,
                         field_strength_cache: FieldStrengthCache | None = None,
                         flow_time=None):
    """固定规范（无 Wilson 线）FF 关联（照抄 Operator.py operators_FF_z0/_mz）。

    F_{μν}(±z·ẑ) 与 F̃_{μ₂ν₂}(0) 逐点收缩后全空间求和；无 Wilson 线，
    仅适用于已固定规范（Coulomb/Landau）的系综——规范协变算符的
    系统误差对照通道。z 方向按参考实现硬编码。

    返回 (delta_z, Nt) 复数数组。
    """
    cp = get_backend()
    delta_z = _validate_lattice_extent(delta_z, "delta_z", 0)
    Nt = _validate_lattice_extent(Nt, "Nt", 1)
    Nx = _validate_lattice_extent(Nx, "Nx", 1)
    if mu2 is None:
        mu2 = mu
    if nu2 is None:
        nu2 = nu
    mu, nu = _validate_lorentz_pair(mu, nu)
    mu2, nu2 = _validate_lorentz_pair(mu2, nu2)
    direction = _validate_ope_direction(direction)
    z_axis = 3 - 2   # 参考实现硬编码 z_dir=2

    need_pairs = _canonicalize_pairs(((mu, nu), (mu2, nu2)))
    for a, b in ((mu, nu), (mu2, nu2)):
        for rho in range(4):
            for sigma in range(4):
                if abs(_TENSOR4[a, b, rho, sigma]) > 1e-10 and rho != sigma:
                    need_pairs.add(_canonical_pair(rho, sigma))
    F_dict = {pair: _field_strength(
                  gauge, pair[0], pair[1], field_strength_cache, flow_time)
              for pair in sorted(need_pairs)}
    F = _lookup_field(F_dict, mu, nu)
    F_tilde = compute_dual_field_strength(F_dict, mu2, nu2)
    del F_dict

    if F is None or F_tilde is None:
        raise ValueError("FF 所需的场强未能从 canonical field dictionary 解析")

    out = np.zeros((delta_z, Nt), dtype=np.complex128)
    for zi in range(delta_z):
        ope_t = cp.roll(F, -direction * zi, axis=z_axis)
        ope_t = cp.matmul(ope_t, F_tilde)
        trace = cp.einsum("...aa->...", ope_t)
        out[zi] = _to_cpu(cp.sum(trace, axis=(1, 2, 3)))
    return out


def get_ope_lorentz_pairs(zdir: int, mode: str = "unpol"):
    """OPE 计算的 (mu, nu, mu2, nu2) Lorentz 指派表（照抄 zhangxin workflow
    get_ope_lorentz_pairs，源自 donghx Calc_ope_* 的 rank 分派）。

    Args:
        zdir: Wilson 线方向（0=x, 1=y, 2=z）。
        mode: "unpol" / "helicity"（同表，后者用对偶叠）、
              "gauge_fix_unpol"（3 对）、"gauge_fix_helicity"（4 对交叉混合）。
    """
    zdir = _validate_spatial_direction(zdir, "zdir")
    mode = _validate_ope_enum(mode, _OPE_PAIR_MODES, "mode")
    if mode in ("unpol", "helicity"):
        pairs = [
            (3, (zdir + 1) % 3, 3, (zdir + 1) % 3),
            (3, (zdir + 2) % 3, 3, (zdir + 2) % 3),
            ((zdir + 1) % 3, (zdir + 2) % 3,
             (zdir + 1) % 3, (zdir + 2) % 3),
        ]
    elif mode == "gauge_fix_unpol":
        pairs = [
            (3, 0, 3, 0),   # F_{t,x}
            (3, 1, 3, 1),   # F_{t,y}
            (0, 1, 0, 1),   # F_{x,y}
        ]
    elif mode == "gauge_fix_helicity":
        pairs = [
            (3, 0, 2, 1),
            (3, 1, 0, 2),
            (3, 2, 0, 1),
            (0, 1, 3, 2),
        ]
    else:
        raise ValueError(f"Unknown OPE mode: {mode}")
    return pairs


# ═══════════════════════════════════════════════════════════════════
# Gauge reader（ILDG .lime，照抄 compute_ope.py）
# ═══════════════════════════════════════════════════════════════════

def _first_link_unitarity(raw: np.ndarray, Nc: int = 3) -> float:
    """首 3×3 链接的幺正性偏差 |U·U† − I|。

    对乱字节偏移（数据起点未对齐时）可能产生 inf/nan，这里用 errstate
    抑制溢出告警并以 isfinite 兜底，避免刷屏、保证错偏移被正确拒绝。
    """
    U = raw[:Nc * Nc * 2].reshape(Nc, Nc, 2)
    Uc = U[..., 0] + 1j * U[..., 1]
    with np.errstate(over='ignore', invalid='ignore'):
        try:
            dev = float(np.abs(Uc @ Uc.conj().T - np.eye(Nc)).max())
        except (FloatingPointError, ValueError):
            return float('inf')
    return dev if np.isfinite(dev) else float('inf')


def resolve_ildg_binary_record(filepath):
    """Resolve an ILDG file or an extracted ``.lime.contents`` directory.

    ``lime_contents`` stores the payload as the canonical
    ``msg02.rec04.ildg-binary-data`` record.  Keep the resolution explicit so
    an unrelated file in the directory can never be selected silently.  The
    returned path is the realpath used for both reading and source identity.
    """
    filepath = os.path.realpath(os.path.abspath(os.fsdecode(os.fspath(filepath))))
    if not os.path.isdir(filepath):
        return filepath
    record = os.path.join(filepath, "msg02.rec04.ildg-binary-data")
    if os.path.isfile(record):
        return os.path.realpath(record)
    raise ValueError(
        f"ILDG contents directory has no msg02.rec04.ildg-binary-data: "
        f"{filepath}"
    )


def _resolve_ildg_binary_record(filepath):
    """Backward-compatible private alias for the shared ILDG resolver."""
    return resolve_ildg_binary_record(filepath)


def read_gauge_lime(filepath: str, Nt: int, Nx: int, Nc: int = 3) -> np.ndarray:
    """读 .lime 规范组态 → complex128 (Nt,Nx,Nx,Nx,4,Nc,Nc)。

    ILDG .lime 为大端 float64 + XML 头 + 尾部记录；扫描 ±16KB 窗口
    按幺正性定位数据起点。

    ``filepath`` 也可以是解包后的 ``.lime.contents`` 目录；此时读取其
    标准 ``msg02.rec04.ildg-binary-data`` 记录。

    优化：幺正性判定只需首链接（18 个 double = 144B）。先用微小探针定位
    合法偏移，命中后才全量读取一次，避免每个候选偏移都读整份（≈573MB）
    造成的 TB 级读盘与乱字节数据导致的 matmul 溢出告警。扫描顺序、阈值
    与回退逻辑与原实现完全一致。
    """
    filepath = resolve_ildg_binary_record(filepath)
    expected_elems = Nt * Nx * Nx * Nx * 4 * Nc * Nc * 2
    expected_bytes = expected_elems * 8
    file_size = os.path.getsize(filepath)
    approx_off = file_size - expected_bytes

    def _read_at(off):
        with open(filepath, 'rb') as f:
            f.seek(off)
            return np.fromfile(f, dtype='>f8', count=expected_elems)

    def _probe_unitarity(off: int) -> bool:
        """仅读首链接（144B）判定偏移合法性。"""
        if off < 0 or off + expected_bytes > file_size:
            return False
        with open(filepath, 'rb') as f:
            f.seek(off)
            head = np.fromfile(f, dtype='>f8', count=Nc * Nc * 2)
        if head.size != Nc * Nc * 2:
            return False
        return _first_link_unitarity(head, Nc) < 1e-3

    if 0 <= approx_off < file_size and _probe_unitarity(approx_off):
        raw = _read_at(approx_off)
        if raw.size == expected_elems and _first_link_unitarity(raw, Nc) < 1e-3:
            return _gauge_from_raw(raw, Nt, Nx, Nc)

    for delta in range(-16384, 16385, 8):
        off = approx_off + delta
        if _probe_unitarity(off):
            raw = _read_at(off)
            if raw.size == expected_elems and _first_link_unitarity(raw, Nc) < 1e-3:
                return _gauge_from_raw(raw, Nt, Nx, Nc)

    raise ValueError(f"No valid gauge data found in {filepath} "
                     f"(size={file_size} bytes)")


def _gauge_from_raw(raw: np.ndarray, Nt: int, Nx: int, Nc: int = 3) -> np.ndarray:
    raw = raw.reshape(Nt, Nx, Nx, Nx, 4, Nc, Nc, 2)
    tg = raw[..., 0] + 1j * raw[..., 1]
    return tg.astype(np.complex128, copy=False)


def _read_gauge_or_skip(filepath: str, Nt: int, Nx: int, Nc: int = 3):
    """尝试读组态；文件不存在返回 None（供管线占位）。"""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        return read_gauge_lime(filepath, Nt, Nx, Nc)
    except (ValueError, OSError):
        return None


# ═══════════════════════════════════════════════════════════════════
# TMD staple 型双场强算符（本库新增）
# ═══════════════════════════════════════════════════════════════════

def staple_operator(gauge, mu: int, nu: int, z: int, b_perp: int,
                    z_dir: int = 2, b_dir: int = 0, L: int | None = None,
                    color_normalization: str = 'fundamental_trace'):
    """同 Lorentz 对的规范不变 staple 双场强算符。

    对 ``y=x+z*z_dir+b_perp*b_dir``，返回逐格点

    ``M^{mu nu;mu nu}(x,y) =``
    ``Tr[F_mu_nu^TL(x) W(x,y) F_mu_nu^TL(y) W^dagger(x,y)]``，其中
    ``F^TL = F - Tr(F) I / 3`` 由共享 TMD bilocal 实现逐格点投影。

    ``W`` 使用 TMD 模块的已验证三段路径
    ``-L*z_dir -> b_perp*b_dir -> (L+z)*z_dir``；``L`` 显式固定
    rapidity-regulator 臂长，单点调用省略时沿用 ``L=abs(z)``。扫描多个
    ``z`` 时调用者应传同一个 ``L``。局部导入避免模块初始化循环，并确保
    公开入口与唯一的 TMD 几何实现保持一致。

    ``color_normalization='fundamental_trace'`` 与 refer 算符保持一致；
    ``'adjoint'`` 返回其两倍，对应 ``Tr(T^aT^b)=delta^{ab}/2`` 下的
    ``F^a W_adj^{ab} F^b``。

    Returns:
        形状 ``(Nt,Nz,Ny,Nx)`` 的逐格点复数色迹；不做空间求和。
    """
    from ..renorm._tmd import M_mu_lambda_nu_rho

    return M_mu_lambda_nu_rho(
        gauge, mu, nu, mu, nu, z, b_perp, z_dir, b_dir, L=L,
        color_normalization=color_normalization)

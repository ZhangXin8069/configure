"""Field-strength cache contracts for the straight-line gluon OPE.

This focused contract deliberately remains outside the aggregate test
registry: the task's write boundary does not include that registry.
Run it directly with ``python pyqcd/testing/_field_strength_cache_contract.py``.
"""
from __future__ import annotations

import tempfile
from unittest import SkipTest
from unittest.mock import patch

import numpy as np


_COMPONENTS = ((3, 0), (3, 1), (0, 1))
_LATTICE_SHAPE = (2, 3, 4, 5)


def _random_su3_gauge(seed=9101, dtype=np.complex128):
    """Small rectangular SU(3) fixture with the repository's tzyx layout."""
    rng = np.random.default_rng(seed)
    gauge = np.empty(_LATTICE_SHAPE + (4, 3, 3), dtype=dtype)
    for index in np.ndindex(*_LATTICE_SHAPE, 4):
        matrix = rng.normal(size=(3, 3)) + 1j * rng.normal(size=(3, 3))
        q, r = np.linalg.qr(matrix)
        phases = np.diag(r)
        phases = np.divide(phases, np.abs(phases),
                           out=np.ones_like(phases), where=np.abs(phases) > 0)
        q = q @ np.diag(phases)
        q *= np.linalg.det(q) ** (-1.0 / 3.0)
        gauge[index] = q.astype(dtype, copy=False)
    return gauge


def _run_default_channels(ope, gauge, cache=None, **kwargs):
    """Run the default straight OPE channels and return outputs."""
    outputs = []
    for mu, nu in _COMPONENTS:
        call_kwargs = dict(kwargs)
        if cache is not None:
            call_kwargs["field_strength_cache"] = cache
        outputs.append(ope.gluon_ope_operator_z0(
            gauge, mu, nu, 2, 3, _LATTICE_SHAPE[0], _LATTICE_SHAPE[3],
            **call_kwargs))
    return outputs


def _cache_type(ope):
    """Resolve the cache through the public operator API."""
    from pyqcd.operator import FieldStrengthCache

    assert FieldStrengthCache is getattr(ope, "FieldStrengthCache", None)
    return FieldStrengthCache


def test_default_multichannel_clover_calls_are_canonical_with_or_without_cache():
    """Canonical fields require six Clover evaluations in either path."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge()
    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as uncached_spy:
        uncached = _run_default_channels(ope, gauge)
    assert uncached_spy.call_count == 6

    class PeakTrackingCache(_cache_type(ope)):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.peak_cached_pairs = 0

        def get(self, *args, **kwargs):
            field = super().get(*args, **kwargs)
            self.peak_cached_pairs = max(
                self.peak_cached_pairs, len(self.cached_pairs))
            return field

    cache = PeakTrackingCache(gauge, max_entries=2)
    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as cached_spy:
        cached = _run_default_channels(ope, gauge, cache=cache)

    assert cached_spy.call_count == 6
    assert cache.peak_cached_pairs == 2
    assert len(cache.cached_pairs) <= 2
    for expected, actual in zip(uncached, cached):
        np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=2e-12)


def test_field_strength_cache_is_publicly_exported():
    """Callers can import the cache from ``pyqcd.operator`` directly."""
    from pyqcd.operator import FieldStrengthCache
    import pyqcd.operator._gluon_ope as ope

    assert FieldStrengthCache is ope.FieldStrengthCache


def test_cache_max_entries_contract_and_boundaries():
    """Capacity defaults to six and rejects bool/non-integer/out-of-range values."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91032)
    cache_type = _cache_type(ope)
    assert cache_type(gauge).max_entries == 6
    for capacity in (1, 2, 6):
        assert cache_type(gauge, max_entries=capacity).max_entries == capacity
    for bad in (True, False, 0, -1, 7, 1.0, None):
        try:
            cache_type(gauge, max_entries=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid max_entries accepted: {bad!r}")


def test_cache_lru_hit_promotes_and_miss_evicts_oldest_pair():
    """A hit refreshes recency; the next miss evicts the true LRU pair."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91033)
    cache = _cache_type(ope)(gauge, max_entries=2)
    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as spy:
        f01 = cache.get(0, 1)
        cache.get(0, 2)
        np.testing.assert_array_equal(cache.get(1, 0), -f01)
        assert spy.call_count == 2

        cache.get(0, 3)
        assert cache.cached_pairs == ((0, 1), (0, 3))
        assert spy.call_count == 3

        cache.get(0, 2)
        assert cache.cached_pairs == ((0, 2), (0, 3))
        assert spy.call_count == 4


def test_cache_miss_evicts_before_full_field_computation():
    """A miss enters Clover with at most ``max_entries - 1`` owned fields."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91034)
    cache = _cache_type(ope)(gauge, max_entries=2)
    held_field = cache.get(0, 1)
    cache.get(0, 2)
    observed = []
    real_clover = ope.plaquette_clover

    def observe_before_compute(*args, **kwargs):
        observed.append(cache.cached_pairs)
        return real_clover(*args, **kwargs)

    with patch.object(ope, "plaquette_clover",
                      side_effect=observe_before_compute):
        new_field = cache.get(0, 3)

    assert observed == [((0, 2),)]
    assert len(cache.cached_pairs) == 2
    assert held_field is not new_field


def test_cache_is_lazy_canonical_and_exactly_antisymmetric():
    """All ordered off-diagonal requests occupy only six canonical entries."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=9102)
    cache = _cache_type(ope)(gauge)
    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as spy:
        fields = {
            (mu, nu): cache.get(mu, nu)
            for mu in range(4) for nu in range(4) if mu != nu
        }

    assert spy.call_count == 6
    assert len(cache.cached_pairs) == 6
    assert all(mu < nu for mu, nu in cache.cached_pairs)
    for mu in range(4):
        for nu in range(mu + 1, 4):
            np.testing.assert_array_equal(
                fields[(nu, mu)], -fields[(mu, nu)])


def test_direct_clover_is_canonical_and_exactly_antisymmetric():
    """The public Clover primitive uses one canonical orientation."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91021)
    for mu in range(4):
        for nu in range(mu + 1, 4):
            forward = ope.plaquette_clover(gauge, mu, nu)
            reverse = ope.plaquette_clover(gauge, nu, mu)
            np.testing.assert_array_equal(reverse, -forward)


def test_cache_refresh_invalidates_after_in_place_gauge_mutation():
    """Non-versioned gauges require an explicit refresh after mutation."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91022)
    cache = _cache_type(ope)(gauge)
    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as spy:
        before = cache.get(0, 1)
        gauge[0, 0, 0, 0, 0, 0, 0] += 0.25
        cache.refresh()
        after = cache.get(0, 1)

    assert spy.call_count == 2, "gauge 变更后必须失效并重算 Clover"
    assert not np.array_equal(after, before), \
        "gauge 变更后的场强不应继续复用旧值"
    expected = ope.plaquette_clover(gauge, 0, 1)
    np.testing.assert_array_equal(after, expected)


def test_non_versioned_cache_exposes_immutable_refresh_contract():
    """NumPy cache identity uses immutable/refresh, not a pseudo-checksum."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    cache = _cache_type(ope)(_random_su3_gauge(seed=91027),
                             gauge_immutable=True)
    assert cache.gauge_immutable is True
    assert cache.mutation_detection == "immutable_refresh"


def test_cache_rejects_false_immutable_declaration():
    """The cache must not expose an unimplemented mutable mode."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    try:
        _cache_type(ope)(_random_su3_gauge(seed=91031),
                         gauge_immutable=False)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported mutable cache mode was accepted")


def test_cache_rejects_active_backend_switch():
    """Cached tensors cannot cross the active NumPy/Torch backend boundary."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    try:
        import torch  # noqa: F401
    except ImportError as exc:
        raise SkipTest("torch 未安装，跳过 backend 所有权契约") from exc

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91023)
    cache = _cache_type(ope)(gauge)
    cache.get(0, 1)
    try:
        set_backend("torch", device="cpu")
        try:
            cache.get(0, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("cache silently crossed active backend")
    finally:
        set_backend("numpy")


def test_cache_rejects_same_object_dtype_change():
    """Changing a tensor's dtype in place invalidates its cache identity."""
    from pyqcd.tools import get_backend, set_backend
    import pyqcd.operator._gluon_ope as ope

    try:
        import torch
    except ImportError as exc:
        raise SkipTest("torch 未安装，跳过 dtype 所有权契约") from exc

    set_backend("torch", device="cpu")
    try:
        gauge = get_backend().asarray(_random_su3_gauge(seed=91024))
        cache = _cache_type(ope)(gauge)
        cache.get(0, 1)
        gauge.data = gauge.data.to(torch.complex64)
        try:
            cache.get(0, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("cache silently crossed gauge dtype")
    finally:
        set_backend("numpy")


def test_cache_rejects_active_torch_device_switch():
    """A cache cannot be hit after the active Torch device changes."""
    from pyqcd.tools import get_backend, set_backend
    import pyqcd.operator._gluon_ope as ope

    try:
        import torch
    except ImportError as exc:
        raise SkipTest("torch 未安装，跳过 Torch device 所有权契约") from exc
    if not torch.cuda.is_available():
        raise SkipTest("无可用 CUDA device，跳过 Torch device 所有权契约")

    set_backend("torch", device="cpu")
    try:
        gauge = get_backend().asarray(_random_su3_gauge(seed=91028))
        cache = _cache_type(ope)(gauge)
        cache.get(0, 1)
        set_backend("torch", device="cuda:0")
        try:
            cache.get(0, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("cache silently crossed active Torch device")
    finally:
        set_backend("numpy")


def test_torch_version_counter_invalidates_tracked_mutation():
    """Torch-tracked in-place writes invalidate in O(1) via ``_version``."""
    from pyqcd.tools import get_backend, set_backend
    import pyqcd.operator._gluon_ope as ope

    try:
        import torch  # noqa: F401
    except ImportError as exc:
        raise SkipTest("torch 未安装，跳过 Torch version 契约") from exc

    set_backend("torch", device="cpu")
    try:
        gauge = get_backend().asarray(_random_su3_gauge(seed=91029))
        cache = _cache_type(ope)(gauge)
        assert cache.mutation_detection == "torch_version"
        with patch.object(ope, "plaquette_clover",
                          wraps=ope.plaquette_clover) as spy:
            before = cache.get(0, 1)
            gauge[0, 0, 0, 0, 0, 0, 0] += 0.25
            after = cache.get(0, 1)
        assert spy.call_count == 2
        assert not torch.equal(before, after)
    finally:
        set_backend("numpy")


def test_cupy_cache_refreshes_mutation_without_cpu_coercion():
    """CuPy fields stay on device and explicit refresh invalidates them."""
    try:
        import cupy as cp
    except ImportError as exc:
        raise SkipTest("cupy 未安装，跳过 CuPy 后端契约") from exc
    try:
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise SkipTest("无可用 CUDA device，跳过 CuPy 后端契约")
    except cp.cuda.runtime.CUDARuntimeError as exc:
        raise SkipTest(f"CUDA 不可用，跳过 CuPy 后端契约: {exc}") from exc

    from pyqcd.tools import get_backend, set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("cupy")
    try:
        gauge = get_backend().asarray(_random_su3_gauge(seed=91025))
        cache = _cache_type(ope)(gauge)
        field = cache.get(0, 1)
        assert isinstance(field, cp.ndarray)
        gauge[0, 0, 0, 0, 0, 0, 0] += 0.25
        cache.refresh()
        refreshed = cache.get(0, 1)
        assert not cp.array_equal(refreshed, field).item()
    finally:
        set_backend("numpy")


def test_invalid_field_strength_directions_are_rejected():
    """Direction labels are non-boolean integers in the closed interval 0..3."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=9103)
    cache = _cache_type(ope)(gauge)
    for bad in (-1, 4, True, False, 1.0):
        try:
            cache.get(bad, 0)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid direction accepted: {bad!r}")
        try:
            ope.plaquette_clover(gauge, bad, 0)
        except ValueError:
            pass
        else:
            raise AssertionError(f"plaquette invalid direction accepted: {bad!r}")

    for pair in ((0, 0), (True, 2)):
        try:
            cache.get(*pair)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid Lorentz pair accepted: {pair!r}")

    for bad_zdir in (-1, 3, True, 1.0):
        try:
            ope.gluon_ope_operator_z0(
                gauge, 3, 0, bad_zdir, 1, _LATTICE_SHAPE[0], _LATTICE_SHAPE[3])
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid z_dir accepted: {bad_zdir!r}")


def test_ff_validates_direction_pairs_and_lattice_dimensions():
    """FF accepts only valid signs, Lorentz pairs, and positive extents."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91036)
    valid = dict(delta_z=1, Nt=_LATTICE_SHAPE[0], Nx=_LATTICE_SHAPE[3])

    for bad_direction in (0, 2, -2, True, False, 1.0, -1.0):
        try:
            ope.gluon_ff_operator_z0(
                gauge, 3, 0, direction=bad_direction, **valid)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(
                f"invalid FF direction accepted: {bad_direction!r}")

    for pair_name, pair in (
            ("primary", (0, 0)),
            ("primary_bool", (True, 2)),
            ("primary_range", (4, 0)),
            ("secondary", (1, 1)),
            ("secondary_bool", (2, False)),
            ("secondary_range", (-1, 0))):
        kwargs = dict(valid)
        if pair_name.startswith("primary"):
            args = (gauge, pair[0], pair[1])
            kwargs.update(mu2=3, nu2=0)
        else:
            args = (gauge, 3, 0)
            kwargs.update(mu2=pair[0], nu2=pair[1])
        try:
            ope.gluon_ff_operator_z0(*args, **kwargs)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(f"invalid FF {pair_name} accepted: {pair!r}")

    for name, bad_value in (("delta_z", -1), ("Nt", 0), ("Nx", 0),
                            ("Nx", True)):
        kwargs = dict(valid)
        kwargs[name] = bad_value
        try:
            ope.gluon_ff_operator_z0(gauge, 3, 0, **kwargs)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(
                f"invalid FF lattice extent accepted: {name}={bad_value!r}")


def test_ff_canonical_need_pairs_deduplicate_uncached_clover_calls():
    """Default FF uses each canonical Clover field at most once."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91037)
    kwargs = dict(delta_z=3, Nt=_LATTICE_SHAPE[0], Nx=_LATTICE_SHAPE[3])
    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as uncached_spy:
        uncached = ope.gluon_ff_operator_z0(gauge, 3, 0, **kwargs)
    assert uncached_spy.call_count == 2, uncached_spy.call_count

    cache = _cache_type(ope)(gauge)
    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as cached_spy:
        cached = ope.gluon_ff_operator_z0(
            gauge, 3, 0, field_strength_cache=cache, **kwargs)
    assert cached_spy.call_count == 2, cached_spy.call_count
    assert all(mu < nu for mu, nu in cache.cached_pairs)
    np.testing.assert_allclose(cached, uncached, rtol=2e-12, atol=2e-12)


def test_cache_rejects_other_gauge_and_flow_time():
    """A cache is explicitly owned by one gauge and one optional flow time."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=9104)
    cache = _cache_type(ope)(gauge, flow_time=3.0)
    cache.get(0, 1, gauge=gauge, flow_time=3.0)

    for foreign_gauge, flow_time in ((_random_su3_gauge(seed=9105), 3.0),
                                     (gauge, 4.0)):
        try:
            cache.get(0, 1, gauge=foreign_gauge, flow_time=flow_time)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "cache silently reused across gauge object or flow time")

    with patch.object(ope, "plaquette_clover",
                      wraps=ope.plaquette_clover) as spy:
        cache.clear()
        cache.get(0, 1, gauge=gauge, flow_time=3.0)
    assert spy.call_count == 1


def test_cached_and_uncached_straight_ope_match_on_rectangular_grid():
    """Positive/negative z and cross Lorentz OPE agree element by element."""
    from pyqcd.tools import set_backend
    import pyqcd.operator._gluon_ope as ope

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=9106)
    cases = (
        dict(mu=3, nu=0, mu2=3, nu2=0, direction=1),
        dict(mu=3, nu=0, mu2=3, nu2=0, direction=-1),
        dict(mu=3, nu=0, mu2=2, nu2=1, direction=1),
        dict(mu=3, nu=0, mu2=2, nu2=1, direction=-1),
    )
    for case in cases:
        uncached = ope.gluon_ope_operator_z0(
            gauge, case.pop("mu"), case.pop("nu"), 2, 3,
            _LATTICE_SHAPE[0], _LATTICE_SHAPE[3], **case)
        cache = _cache_type(ope)(gauge)
        cached = ope.gluon_ope_operator_z0(
            gauge, 3, 0, 2, 3, _LATTICE_SHAPE[0], _LATTICE_SHAPE[3],
            field_strength_cache=cache, **case)
        np.testing.assert_allclose(cached, uncached,
                                   rtol=2e-12, atol=2e-12)


def test_torch_ope_default_compute_dtype_maps_to_numpy_output():
    """Torch gauges keep the old omitted-dtype API at the CPU boundary."""
    from pyqcd.tools import get_backend, set_backend
    import pyqcd.operator._gluon_ope as ope

    try:
        import torch  # noqa: F401
    except ImportError as exc:
        raise SkipTest("torch 未安装，跳过 OPE 默认 dtype 契约") from exc

    set_backend("torch", device="cpu")
    try:
        gauge = get_backend().asarray(_random_su3_gauge(seed=91030))
        plain = ope.gluon_ope_operator_z0(
            gauge, 3, 0, 2, 3, _LATTICE_SHAPE[0], _LATTICE_SHAPE[3])
        cache = _cache_type(ope)(gauge)
        cached = ope.gluon_ope_operator_z0(
            gauge, 3, 0, 2, 3, _LATTICE_SHAPE[0], _LATTICE_SHAPE[3],
            field_strength_cache=cache)
        assert isinstance(plain, np.ndarray)
        assert plain.dtype == np.complex128
        np.testing.assert_allclose(cached, plain, rtol=2e-12, atol=2e-12)
    finally:
        set_backend("numpy")


def test_pipeline_creates_and_passes_one_cache_per_config():
    """The OPE pipeline step explicitly shares one cache across components."""
    from pyqcd.pipeline import _steps as steps
    import pyqcd.operator._gluon_ope as ope
    from pyqcd.tools import set_backend

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=9107)
    with tempfile.TemporaryDirectory() as run_dir, \
            patch.object(steps, "HAS_CUPY", True), \
            patch.object(steps, "NT", _LATTICE_SHAPE[0]), \
            patch.object(steps, "NX", _LATTICE_SHAPE[3]), \
            patch.object(steps, "get_gauge_path", return_value="fixture"), \
            patch.object(steps, "read_gauge_lime", return_value=gauge), \
            patch.object(steps, "_validate_gauge"), \
            patch.object(steps, "FieldStrengthCache",
                         wraps=ope.FieldStrengthCache) as cache_ctor, \
            patch.object(steps, "gluon_ope_operator_z0",
                         wraps=ope.gluon_ope_operator_z0) as ope_spy, \
            patch.object(steps, "save_tensor_h5"), \
            patch.object(steps, "save_array"), \
            patch.object(steps, "free_gpu_memory"), \
            patch.object(steps, "log_gpu_memory"):
        steps.compute_ope_for_config(
            9107, run_dir, logger=None, precision="complex128",
            delta_z=3, components=_COMPONENTS)

    assert cache_ctor.call_count == 1
    assert cache_ctor.call_args.kwargs["max_entries"] == 2
    assert ope_spy.call_count == len(_COMPONENTS)
    passed_caches = [call.kwargs["field_strength_cache"]
                     for call in ope_spy.call_args_list]
    assert len({id(cache) for cache in passed_caches}) == 1


def test_pipeline_releases_gpu_memory_after_ope_failure():
    """OPE exceptions still clear the cache and release backend memory."""
    from pyqcd.pipeline import _steps as steps
    import pyqcd.operator._gluon_ope as ope
    from pyqcd.tools import set_backend

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91026)

    class TrackingCache:
        instances = []

        def __init__(self, _gauge, **kwargs):
            self.clear_calls = 0
            self.gauge_immutable = kwargs.get("gauge_immutable")
            self.max_entries = kwargs.get("max_entries")
            self.__class__.instances.append(self)

        def clear(self):
            self.clear_calls += 1

    def fail_ope(*_args, **_kwargs):
        raise RuntimeError("injected OPE failure")

    with tempfile.TemporaryDirectory() as run_dir, \
            patch.object(steps, "HAS_CUPY", True), \
            patch.object(steps, "NT", _LATTICE_SHAPE[0]), \
            patch.object(steps, "NX", _LATTICE_SHAPE[3]), \
            patch.object(steps, "get_gauge_path", return_value="fixture"), \
            patch.object(steps, "read_gauge_lime", return_value=gauge), \
            patch.object(steps, "_validate_gauge"), \
            patch.object(steps, "FieldStrengthCache", TrackingCache), \
            patch.object(steps, "gluon_ope_operator_z0", side_effect=fail_ope), \
            patch.object(steps, "free_gpu_memory") as free_memory, \
            patch.object(steps, "log_gpu_memory"), \
            patch.object(steps, "save_tensor_h5"), \
            patch.object(steps, "save_array"):
        try:
            steps.compute_ope_for_config(
                91026, run_dir, logger=None, precision="complex128",
                delta_z=3, components=_COMPONENTS)
        except RuntimeError as exc:
            assert str(exc) == "injected OPE failure"
        else:
            raise AssertionError("injected OPE failure was swallowed")

    assert len(TrackingCache.instances) == 1
    assert TrackingCache.instances[0].clear_calls == 1
    assert TrackingCache.instances[0].gauge_immutable is True
    assert TrackingCache.instances[0].max_entries == 2
    assert free_memory.call_count == 1


def test_pipeline_cleanup_baseexceptions_preserve_original_ope_exception():
    """Cleanup control-flow exceptions cannot mask the active OPE failure."""
    from pyqcd.pipeline import _steps as steps
    from pyqcd.tools import set_backend

    set_backend("numpy")
    gauge = _random_su3_gauge(seed=91035)
    for cleanup_site, cleanup_exception in (
        ("clear", KeyboardInterrupt()), ("free", SystemExit(17))):
        class TrackingCache:
            def __init__(self, *_args, **_kwargs):
                pass

            def clear(self):
                if cleanup_site == "clear":
                    raise cleanup_exception

        primary = RuntimeError(f"primary OPE failure at {cleanup_site}")

        def fail_ope(*_args, **_kwargs):
            raise primary

        def free_memory():
            if cleanup_site == "free":
                raise cleanup_exception

        with tempfile.TemporaryDirectory() as run_dir, \
                patch.object(steps, "HAS_CUPY", True), \
                patch.object(steps, "NT", _LATTICE_SHAPE[0]), \
                patch.object(steps, "NX", _LATTICE_SHAPE[3]), \
                patch.object(steps, "get_gauge_path", return_value="fixture"), \
                patch.object(steps, "read_gauge_lime", return_value=gauge), \
                patch.object(steps, "_validate_gauge"), \
                patch.object(steps, "FieldStrengthCache", TrackingCache), \
                patch.object(steps, "gluon_ope_operator_z0",
                             side_effect=fail_ope), \
                patch.object(steps, "free_gpu_memory",
                             side_effect=free_memory), \
                patch.object(steps, "log_gpu_memory"), \
                patch.object(steps, "save_tensor_h5"), \
                patch.object(steps, "save_array"):
            try:
                steps.compute_ope_for_config(
                    91035, run_dir, logger=None, precision="complex128",
                    delta_z=3, components=_COMPONENTS)
            except RuntimeError as exc:
                assert exc is primary
            except BaseException as exc:
                raise AssertionError(
                    f"cleanup {cleanup_site} masked the OPE exception") from exc
            else:
                raise AssertionError("primary OPE failure was swallowed")


def test_numpy_and_torch_cache_keep_backend_array_type():
    """The cache does not coerce field tensors away from the active backend."""
    import pyqcd.operator._gluon_ope as ope
    from pyqcd.tools import get_backend, set_backend

    gauge = _random_su3_gauge(seed=9108)
    set_backend("numpy")
    numpy_field = _cache_type(ope)(gauge).get(0, 1)
    assert isinstance(numpy_field, np.ndarray)

    try:
        import torch
    except ImportError as exc:
        raise SkipTest("torch 未安装，跳过 Torch 后端契约") from exc

    try:
        set_backend("torch", device="cpu")
        torch_gauge = get_backend().asarray(gauge)
        torch_field = _cache_type(ope)(torch_gauge).get(0, 1)
        assert isinstance(torch_field, torch.Tensor)
        assert torch_field.device.type == "cpu"
        np.testing.assert_allclose(
            torch_field.detach().cpu().numpy(), numpy_field, rtol=1e-12, atol=1e-12)
    finally:
        set_backend("numpy")


def _run_all():
    tests = [value for name, value in globals().items()
             if name.startswith("test_") and callable(value)]
    passed = skipped = 0
    for test in tests:
        try:
            test()
        except SkipTest as exc:
            skipped += 1
            print(f"SKIP {test.__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {test.__name__}")
    print(f"{passed} passed, {skipped} skipped, 0 failed")


if __name__ == "__main__":
    _run_all()

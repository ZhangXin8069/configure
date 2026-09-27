"""
Dynamic Contraction System
==========================

Registry-based contraction framework that ties Wick contraction output
to actual data arrays. The recommended workflow:

1. Register data → ``PeramRegistry``, ``VRegistry``, ``GammaRegistry``
2. Analyze → ``run_wick_analysis()`` builds contraction plan
3. Contract → ``dynamic_contraction`` or ``calculate_contraction()``

Adapted from lqcddb contraction/dynamic.py.
"""

import numpy as np
from ..tools._base import cached_contract
from ._autowick import wick_contraction, identify_equivalent_diagrams


# ═══════════════════════════════════════════════════════════════════
# Logging (non-MPI version for single-GPU)
# ═══════════════════════════════════════════════════════════════════

def _log(*args, **kwargs):
    """Simple print wrapper (always prints in single-GPU mode)."""
    kwargs.setdefault('flush', True)
    print(*args, **kwargs)


def _check_not_none(data, what):
    """Raise ValueError if data is None."""
    if data is None:
        raise ValueError(f'{what} cannot be None. Check registration or data loading.')


def _check_min_ndim(data, min_ndim, what):
    """Raise ValueError if data.ndim < min_ndim."""
    if data.ndim < min_ndim:
        raise ValueError(
            f'{what} insufficient dimensions: need ≥{min_ndim}, got shape={data.shape}')


# ═══════════════════════════════════════════════════════════════════
# PeramRegistry
# ═══════════════════════════════════════════════════════════════════

class PeramRegistry:
    """Perambulator (propagator) data registry.

    Stores peram array references by (flavor, time_labels) key.
    Time labels: ``'tsink'``, ``'tsrc'``, ``'tcur0'``, ``'tcur1'``, ...
    Flavor ``'light'`` matches both ``'u'`` and ``'d'``.

    Methods
    -------
    register(flavor, time_labels, data)
        Register a peram array. Overwrites on duplicate key.
    resolve(combined_type, time_labels)
        Look up peram by Wick output flavor and time labels.
    """

    def __init__(self):
        self._entries = {}

    def register(self, flavor, time_labels, data):
        """Register a peram array (stores reference, not copy).

        Parameters
        ----------
        flavor : str
            ``'u'``, ``'d'``, ``'s'``, or ``'light'`` (matches both u,d).
        time_labels : tuple of str
            ``(t_quark, t_antiquark)``.
        data : ndarray
            Peram array, shape (..., Ns, Ns, Nev, Nev).
        """
        _check_not_none(data, f'peram({flavor},{time_labels})')
        _check_min_ndim(data, 4, f'peram({flavor},{time_labels})')
        self._entries[(flavor, tuple(time_labels))] = data

    def resolve(self, combined_type, time_labels):
        """Look up peram by Wick entry.

        Parameters
        ----------
        combined_type : str
            Combined flavor string from Wick output, e.g. ``'uu^d'``.
        time_labels : list of str
            ``[t_quark, t_antiquark]``.

        Returns
        -------
        ndarray
            Matching peram array.
        """
        qf = combined_type[0]
        tk = tuple(time_labels)
        key = (qf, tk)
        if key in self._entries:
            return self._entries[key]
        key_light = ('light', tk)
        if key_light in self._entries:
            return self._entries[key_light]
        raise KeyError(
            f'Peram not registered: flavor={qf}, time={tk}. '
            f'Registered: {list(self._entries.keys())}')


# ═══════════════════════════════════════════════════════════════════
# VRegistry
# ═══════════════════════════════════════════════════════════════════

class VRegistry:
    """V vertex tensor registry.

    Stores V arrays by (v_name, time_label) key.
    Per time region, VVV and VDV are independently numbered from 0.

    Methods
    -------
    register(v_name, time_label, data)
        Register a V tensor.
    resolve(v_name, time_label)
        Look up by name and time label.
    """

    def __init__(self):
        self._entries = {}

    def register(self, v_name, time_label, data):
        """Register a V tensor.

        Parameters
        ----------
        v_name : str
            ``'VVV_0'`` (baryon vertex) or ``'VDV_0'`` (meson vertex).
        time_label : str
            ``'tsink'``, ``'tsrc'``, ``'tcur0'``, etc.
        data : ndarray
            V tensor array. First dimension is momentum.
        """
        _check_not_none(data, f'V({v_name}@{time_label})')
        self._entries[(v_name, time_label)] = data

    def resolve(self, v_name, time_label):
        """Look up V tensor.

        Returns
        -------
        ndarray
            Matching V tensor.
        """
        k = (v_name, time_label)
        if k in self._entries:
            return self._entries[k]
        raise KeyError(
            f'V not registered: {v_name}@{time_label}. '
            f'Registered: {list(self._entries.keys())}')


# ═══════════════════════════════════════════════════════════════════
# GammaRegistry
# ═══════════════════════════════════════════════════════════════════

class GammaRegistry:
    """Gamma matrix registry.

    Maps gamma names from operator strings to actual complex arrays.
    Also stores spin projectors under key ``'Projector'``.

    Methods
    -------
    register(name, data)
        Register a gamma matrix.
    resolve(name)
        Look up by name.
    """

    def __init__(self):
        self._entries = {}

    def register(self, name, data):
        """Register a gamma matrix.

        Parameters
        ----------
        name : str
            Gamma name, e.g. ``'gamma_5'``, ``'gamma_7'``.
        data : ndarray
            Complex array (any shape).
        """
        _check_not_none(data, f'gamma({name})')
        self._entries[name] = data

    def resolve(self, name):
        """Look up gamma matrix."""
        if name in self._entries:
            return self._entries[name]
        raise KeyError(
            f'Gamma not registered: {name}. '
            f'Registered: {list(self._entries.keys())}')


# ═══════════════════════════════════════════════════════════════════
# V name renumbering (global → per-region)
# ═══════════════════════════════════════════════════════════════════

def _per_region_v_names(v_info):
    """Convert global V numbering to per-region independent numbering.

    Wick outputs global sequential numbers (VVV_0, VDV_1, VVV_2, ...).
    This converts to per-time-region independent numbering where each
    region's VVV and VDV each start from 0.
    """
    counters = {}
    result = []
    for v in v_info:
        vtype = 'VVV' if 'VVV' in v[1] else 'VDV'
        vtime = v[3]
        key = (vtime, vtype)
        idx = counters.get(key, 0)
        counters[key] = idx + 1
        result.append((f'{vtype}_{idx}', vtime))
    return result


# ═══════════════════════════════════════════════════════════════════
# Plan cache
# ═══════════════════════════════════════════════════════════════════

_plan_cache = {}


def _make_hashable(obj):
    """Recursively convert lists to tuples for hashing."""
    if isinstance(obj, list):
        return tuple(_make_hashable(x) for x in obj)
    if isinstance(obj, tuple):
        return tuple(_make_hashable(x) for x in obj)
    return obj


def _plan_cache_key(operator_groups, Cpt, Pindex, Vindex, Gindex,
                    use_equivalence, ignore_dis,
                    Projection=False, Oindex=None):
    return (_make_hashable(operator_groups), Cpt,
            _make_hashable(Pindex), _make_hashable(Vindex),
            _make_hashable(Gindex),
            use_equivalence, ignore_dis,
            Projection, _make_hashable(Oindex))


def clear_plan_cache():
    """Clear the Wick analysis plan cache."""
    _plan_cache.clear()


# ═══════════════════════════════════════════════════════════════════
# run_wick_analysis — analyze and build contraction plan
# ═══════════════════════════════════════════════════════════════════

def run_wick_analysis(operator_groups, *,
                      Cpt='2pt',
                      Pindex=None, Vindex=None, Gindex=None,
                      use_equivalence=False,
                      ignore_dis=True,
                      verbose=True, max_detail=3,
                      Projection=False,
                      Oindex=None,
                      optimize='auto',
                      peram_registry=None, v_registry=None,
                      gamma_registry=None):
    """Run Wick contraction analysis, returning a structured plan.

    Parameters
    ----------
    operator_groups : list of tuple
        2pt: ``[(sink_op, src_op), ...]``
        3pt: ``[(sink_op, src_op, curr_op), ...]``
    Cpt : str
        ``'2pt'``, ``'3pt'``, ``'4pt'``.
    Pindex, Vindex, Gindex : list of str, optional
        Prefix letters for peram/V/gamma external indices.
    use_equivalence : bool
        If True, merge equivalent diagrams.
    ignore_dis : bool
        If True, skip disconnected diagrams (t_q == t_aq).
    verbose : bool
        Print analysis details.
    max_detail : int
        Max diagrams to show per group (-1 = all).
    Projection : bool
        Enable spin projection.
    Oindex : str, optional
        Explicit output uppercase indices.

    Returns
    -------
    list of list
        Each entry: [equiv_list, group_idx, wick_dict, diag_idx,
                     proj_label, output_labels, oindex_given]
    """
    cache_key = _plan_cache_key(operator_groups, Cpt,
                                Pindex, Vindex, Gindex,
                                use_equivalence, ignore_dis,
                                Projection, Oindex)
    if cache_key in _plan_cache:
        return _plan_cache[cache_key]

    wick_results = []
    all_peram_types = set()
    all_gamma_names = set()
    all_v_names = set()
    errors = []
    disconnected = set()

    # Gamma count from first group
    _first = operator_groups[0]
    if len(_first) == 2:
        _s0, _s1, _s2 = _first[0], _first[1], []
    else:
        _s0, _s1, _s2 = _first
    n_gammas = sum(1 for x in _s0 + _s1 + _s2
                   if isinstance(x, str) and x.startswith('gamma_'))

    _gindex_w = list(Gindex) if Gindex else []
    if len(_gindex_w) < n_gammas:
        _gindex_w += [''] * (n_gammas - len(_gindex_w))
    _proj_label = ''
    if Projection and Gindex and len(Gindex) > n_gammas:
        _proj_label = Gindex[n_gammas]

    _output_labels = None

    def _get_output_labels(einsum_rhs):
        _upper = ''.join(c for c in einsum_rhs if c.isupper())
        if Oindex is not None:
            _allowed = _upper + (_proj_label if Projection else '')
            _unknown = [c for c in Oindex if c not in _allowed]
            if _unknown:
                errors.append(
                    f'Oindex={Oindex!r} contains unknown indices {_unknown}')
            return Oindex
        return _upper

    # Phase 1: Collect all Wick results
    group_info = []
    for idx, item in enumerate(operator_groups):
        if len(item) == 2:
            sink_op, src_op = item
            curr_op = []
        else:
            sink_op, src_op, curr_op = item

        w = wick_contraction(
            sink_operators=sink_op, source_operators=src_op,
            Cpt=Cpt, curr_operators=curr_op,
            Pindex=Pindex, Vindex=Vindex, Gindex=_gindex_w)
        wick_results.append(w)

        if _output_labels is None and w:
            _rhs = w['result_indx'][0][0].split('->')[1]
            _output_labels = _get_output_labels(_rhs)

        nd = len(w['result_indx'])
        sink_seps = sum(1 for x in w['sink_operators'] if x == '|')
        src_seps = sum(1 for x in w['source_operators'] if x == '|')

        ptypes = set()
        for di in range(nd):
            for p in w['peram'][di]:
                pt = (p[2][0], tuple(p[4]))
                ptypes.add(pt)
                all_peram_types.add(pt)

        gnames = [(g[1], g[3]) for g in w['gamma_pos']]
        vnames_per_region = _per_region_v_names(w['V'])
        for gn, _ in gnames:
            all_gamma_names.add(gn)
        for vn, vt in vnames_per_region:
            all_v_names.add((vn, vt))

        # Detect disconnected
        dis_info = []
        for di in range(nd):
            dis_perams = []
            for p in w['peram'][di]:
                if p[4][0] == p[4][1]:
                    dis_perams.append((p[3], p[4][0], p[4][1]))
            if dis_perams:
                dis_info.append((di, dis_perams))
                if ignore_dis:
                    disconnected.add((idx, di))

        n_dis = len(dis_info)
        n_con = nd - n_dis
        group_info.append((idx, w, nd, sink_seps, src_seps, ptypes, gnames,
                          vnames_per_region, dis_info, n_dis, n_con))

    # Phase 2: Equivalent diagram detection
    equiv_lookup = {}
    eqs = None
    if use_equivalence and len(wick_results) > 0:
        eqs = identify_equivalent_diagrams(*wick_results)
        for eq in eqs:
            equiv_list = [(d, di, coeff) for d, di, coeff in eq]
            rd, rdi, _ = eq[0]
            if ignore_dis and (rd, rdi) in disconnected:
                continue
            for gidx, di, _ in equiv_list:
                if ignore_dis and (gidx, di) in disconnected:
                    continue
                if (gidx, di) != (rd, rdi):
                    equiv_lookup[(gidx, di)] = (rd, rdi)

    # Phase 3: Verbose output
    if verbose:
        for (idx, w, nd, sink_seps, src_seps, ptypes, gnames,
             vnames_per_region, dis_info, n_dis, n_con) in group_info:
            dis_str = f' (disconnected: {n_dis}, ignored)' if ignore_dis and n_dis else ''
            shown = nd if not ignore_dis else n_con
            _log(f'\n{"─"*60}')
            _log(f'Group {idx:2d}  sink|={sink_seps} src|={src_seps}  '
                 f'diagrams={nd}  valid={shown}{dis_str}')
            _log(f'  Register peram (flavor,time): {sorted(ptypes)}')
            _log(f'  Register gamma: {gnames}')
            _log(f'  Register V (per-region): {vnames_per_region}')

            if max_detail != 0:
                limit = min(shown, max_detail) if max_detail > 0 else shown
                shown_count = 0
                for di in range(nd):
                    if ignore_dis and any(d == di for d, _ in dis_info):
                        continue
                    if shown_count >= limit:
                        break
                    s = w['result_sign'][di]
                    e = w['result_indx'][di][0]
                    rhs = e.split('->')[1]
                    free = ''.join(c for c in rhs if c.islower())
                    eq_note = ''
                    if use_equivalence and (idx, di) in equiv_lookup:
                        rg, rd = equiv_lookup[(idx, di)]
                        eq_note = f'  ≡ group{rg} diag{rd}'
                    cost_note = ''
                    if None not in (peram_registry, v_registry,
                                    gamma_registry):
                        # FLOPs 诊断（照抄 lqcddb run_wick_analysis 的
                        # cost_note 块：registry 形状 → 路径分析）
                        try:
                            _p_shapes = [peram_registry.resolve(
                                p[2], p[4]).shape for p in w['peram'][di]]
                            _v_names = _per_region_v_names(w['V'])
                            _v_shapes = [v_registry.resolve(vn, vt).shape
                                         for vn, vt in _v_names]
                            _g_shapes = [gamma_registry.resolve(g[1]).shape
                                         for g in w['gamma_pos']]
                            _shapes = _p_shapes + _g_shapes + _v_shapes
                            if Projection:
                                _proj = gamma_registry.resolve('Projector')
                                _shapes = _shapes + [_proj[0].shape,
                                                     _proj[1].shape]
                            nf, of, sp, li, opt_name = \
                                _analyze_contraction_path(e, _shapes,
                                                          optimize)
                            cost_note = (
                                f'  朴素 FLOP={_format_cost(nf)}'
                                f'  优化 FLOP={_format_cost(of)}'
                                f'  加速比={_format_cost(sp)}x'
                                f'  中间最大张量数据={li / 1e9:.2f}GB(cpx)'
                                f'  最优optimize={opt_name}')
                        except Exception as _e:
                            _log(f'    [FLOP分析失败] '
                                 f'{type(_e).__name__}: {_e}')
                    _log(f'  Diag{di}: sign={s.real:+.1f} '
                         f'free={free}{eq_note}{cost_note}')
                    _log(f'    einsum: {e}')
                    shown_count += 1

        if ignore_dis and disconnected:
            _log(f'\n⚠ {len(disconnected)} disconnected diagrams ignored')

        _log(f'\n{"─"*60}')
        _log(f'Global registration needed:')
        _log(f'  peram: {sorted(all_peram_types)}')
        _log(f'  gamma: {sorted(all_gamma_names)}')
        _log(f'  V: {sorted(all_v_names)}')

    # Phase 4: Build plan
    plan = []
    total_raw = 0

    if use_equivalence and eqs:
        for eq in eqs:
            equiv_list = [(d, di, coeff) for d, di, coeff in eq]
            rd, rdi, _ = eq[0]
            if ignore_dis and (rd, rdi) in disconnected:
                continue
            plan.append([
                equiv_list, rd, wick_results[rd], rdi,
                _proj_label, _output_labels, Oindex is not None,
            ])
            total_raw += len(equiv_list)

        if verbose:
            nu = len(plan)
            nr = total_raw
            pct = 100 - nu * 100 // nr if nr else 0
            _log(f'\nEquivalence: {nr}→{nu} unique ({pct}% reduction)')
    else:
        for gidx, w in enumerate(wick_results):
            for di in range(len(w['result_indx'])):
                if ignore_dis and (gidx, di) in disconnected:
                    continue
                plan.append([
                    [(gidx, di, w['result_sign'][di])],
                    gidx, w, di,
                    _proj_label, _output_labels, Oindex is not None,
                ])
                total_raw += 1

    _plan_cache[cache_key] = plan
    return plan


# ═══════════════════════════════════════════════════════════════════
# Projection einsum builder
# ═══════════════════════════════════════════════════════════════════

def _build_projection_einsum(ein, proj_label, output_labels, oindex_given=False):
    """Build bilateral spin-projection einsum string.

    If there are exactly 2 free spin indices (baryon case), attaches
    spin projectors. If there are 0 free spin indices (meson case where
    all spin is contracted through gamma insertions), returns the
    original einsum unchanged.
    """
    lhs, rhs = ein.split('->')
    n_lower = sum(1 for ch in rhs if ch.islower())
    spin_out = rhs[:n_lower]

    if len(spin_out) == 0:
        # No free spin indices — projection is already handled by gamma
        # insertions (meson case). Return original einsum.
        return ein

    if len(spin_out) != 2:
        raise ValueError(
            f'Bilateral projection requires 0 or 2 output spin indices, '
            f'got spin_out={spin_out!r}')

    used = set(ein) | set(proj_label) | set(output_labels)
    a, s = spin_out[0], spin_out[1]

    if oindex_given:
        z = [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if c not in used][0]
        return f'{lhs},{proj_label}{a}{z},{proj_label}{s}{z}->{output_labels}'

    x, y = [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if c not in used][:2]
    return f'{lhs},{proj_label}{a}{x},{proj_label}{s}{y}->{x}{y}{proj_label}{output_labels}'


# ═══════════════════════════════════════════════════════════════════
# calculate_contraction — execute a single diagram contraction
# ═══════════════════════════════════════════════════════════════════

def calculate_contraction(entry, *,
                          peram_registry, v_registry, gamma_registry,
                          optimize='auto',
                          Projection=False):
    """Execute tensor contraction for a single plan entry.

    Parameters
    ----------
    entry : list
        One row from ``run_wick_analysis`` output.
    peram_registry, v_registry, gamma_registry : Registry
        Data registries.
    optimize : str
        Contraction optimization strategy.
    Projection : bool or str
        Enable spin projection.

    Returns
    -------
    ndarray or int
        Contraction result multiplied by total coefficient.
    """
    equiv_list = entry[0]
    total_coeff = sum(coeff for _, _, coeff in equiv_list)
    if abs(total_coeff) < 1e-12:
        return complex(0)

    _, _, wick, diag_idx, *_ = entry
    _output_labels = entry[5] if len(entry) > 5 else ''
    _oindex_given = entry[6] if len(entry) > 6 else False
    ein = wick['result_indx'][diag_idx][0]
    perams = wick['peram'][diag_idx]
    v_info = wick['V']
    g_info = wick['gamma_pos']

    p_vars = [peram_registry.resolve(p[2], p[4]) for p in perams]
    v_names = _per_region_v_names(v_info)
    v_vars = [v_registry.resolve(vn, vt) for vn, vt in v_names]
    g_vars = [gamma_registry.resolve(g[1]) for g in g_info]

    tensors = p_vars + g_vars + v_vars

    # Oindex override
    if len(entry) > 5:
        lhs, rhs = ein.split('->')
        n_lower = sum(1 for ch in rhs if ch.islower())
        spin_out = rhs[:n_lower]
        ein = f'{lhs}->{spin_out}{_output_labels}'

    # Projection
    if Projection is not False:
        if Projection is True:
            _proj_label = entry[4] if len(entry) > 4 else ''
        else:
            _proj_label = str(Projection)

        # Check if we have spin indices to project
        _lhs, _rhs = ein.split('->')
        _n_lower = sum(1 for ch in _rhs if ch.islower())
        if _n_lower > 0:
            proj = gamma_registry.resolve('Projector')
            if len(proj) != 2:
                raise ValueError("Projector must be [proj_sink, proj_src]")
            ein = _build_projection_einsum(ein, _proj_label, _output_labels,
                                           oindex_given=_oindex_given)
            tensors = tensors + [proj[0], proj[1]]

    # Validate tensor count
    n_parts = len(ein.split('->')[0].split(','))
    if len(tensors) != n_parts:
        raise RuntimeError(
            f'Tensor count mismatch: {len(tensors)} vs {n_parts} in einsum')

    return total_coeff * cached_contract(ein, *tensors, optimize=optimize)


# ═══════════════════════════════════════════════════════════════════
# validate_plan — pre-check all registry lookups
# ═══════════════════════════════════════════════════════════════════

def validate_plan(plan, *, peram_registry, v_registry, gamma_registry):
    """Pre-validate all registry lookups in a plan."""
    missing = []
    for i, entry in enumerate(plan):
        try:
            _, _, wick, diag_idx, *_ = entry
            for p in wick['peram'][diag_idx]:
                peram_registry.resolve(p[2], p[4])
            for vn, vt in _per_region_v_names(wick['V']):
                v_registry.resolve(vn, vt)
            for g in wick['gamma_pos']:
                gamma_registry.resolve(g[1])
        except KeyError as e:
            missing.append((i, str(e)))
    return missing


# ═══════════════════════════════════════════════════════════════════
# dynamic_contraction — main workflow class
# ═══════════════════════════════════════════════════════════════════

class dynamic_contraction:
    """Dynamic Wick contraction calculator.

    Initializes with operator groups and registries, automatically runs
    Wick analysis, validates registrations, and provides ``calculate(i)``
    and ``calculate_all()`` for on-demand contraction.

    Parameters
    ----------
    operator_groups : list of tuple
        Same as ``run_wick_analysis``.
    peram_registry, v_registry, gamma_registry : Registry
        Data registries with registered arrays.
    Cpt : str
        ``'2pt'``, ``'3pt'``, ``'4pt'``.
    use_equivalence : bool
        Merge equivalent diagrams.
    Pindex, Vindex, Gindex : list of str, optional
        External index prefixes.
    verbose : bool
        Print analysis details.
    max_detail : int
        Max diagrams to show per group.
    Projection : bool
        Enable spin projection.
    optimize : str
        Einsum optimization strategy.
    Oindex : str, optional
        Explicit output uppercase indices.

    Methods
    -------
    calculate(index)
        Contract one diagram from the plan.
    calculate_all()
        Contract all diagrams and sum.
    __len__()
        Number of unique diagrams in the plan.
    """

    def __init__(self, operator_groups, *,
                 peram_registry, v_registry, gamma_registry,
                 Cpt='2pt',
                 Pindex=None, Vindex=None, Gindex=None,
                 use_equivalence=False,
                 ignore_dis=True,
                 verbose=True,
                 max_detail=3,
                 Projection=False,
                 optimize='auto',
                 Oindex=None):
        self._peram_registry = peram_registry
        self._v_registry = v_registry
        self._gamma_registry = gamma_registry
        self._projection = Projection
        self._optimize = optimize

        _cache_key = _plan_cache_key(operator_groups, Cpt,
                                     Pindex, Vindex, Gindex,
                                     use_equivalence, ignore_dis,
                                     Projection, Oindex)
        _is_cached = _cache_key in _plan_cache

        self.plan = run_wick_analysis(
            operator_groups,
            Cpt=Cpt,
            Pindex=Pindex, Vindex=Vindex, Gindex=Gindex,
            use_equivalence=use_equivalence,
            ignore_dis=ignore_dis,
            verbose=verbose, max_detail=max_detail,
            Projection=Projection,
            Oindex=Oindex,
        )

        self.missing = validate_plan(
            self.plan,
            peram_registry=peram_registry,
            v_registry=v_registry,
            gamma_registry=gamma_registry,
        )
        if self.missing:
            msg = '\n'.join(f'  plan[{i}]: {m}' for i, m in self.missing)
            raise RuntimeError(f'Registration validation failed ({len(self.missing)} missing):\n{msg}')
        elif verbose and not _is_cached:
            _log('✓ All registrations validated')

    def calculate(self, index):
        """Contract the i-th diagram in the plan.

        Returns
        -------
        ndarray or int
            Contraction result × coefficient.
        """
        if index < 0 or index >= len(self.plan):
            raise IndexError(f'index={index} out of range [0, {len(self.plan)})')
        return calculate_contraction(
            self.plan[index],
            peram_registry=self._peram_registry,
            v_registry=self._v_registry,
            gamma_registry=self._gamma_registry,
            optimize=self._optimize,
            Projection=self._projection,
        )

    def calculate_all(self):
        """Contract all diagrams and sum.

        Returns
        -------
        ndarray
            Total correlation function (sum of all diagrams × coefficients).
        """
        total = 0
        for i in range(len(self.plan)):
            result = self.calculate(i)
            if isinstance(result, (int, complex, float)):
                if result != 0:
                    total = total + result
            else:
                total = total + result
        return total

    def __len__(self):
        return len(self.plan)

    def __getitem__(self, index):
        return self.plan[index]


# ═══════════════════════════════════════════════════════════════════
# 收缩路径 FLOPs 诊断（整合 lqcddb dynamic._analyze_contraction_path）
# ═══════════════════════════════════════════════════════════════════

def _format_cost(n):
    """MAC 数 → 人类可读串（照抄 dynamic._format_cost）。"""
    from decimal import Decimal
    n = int(n)
    if n >= 1e15:
        return f"{format(Decimal(n), '.3e')}"
    elif n >= 1e12:
        return f'{n / 1e12:.2f}T'
    elif n >= 1e9:
        return f'{n / 1e9:.2f}G'
    elif n >= 1e6:
        return f'{n / 1e6:.2f}M'
    elif n >= 1e3:
        return f'{n / 1e3:.2f}K'
    else:
        return f'{n:.0f}'


def _analyze_contraction_path(einsum_str, shapes, optimize='auto'):
    """收缩路径朴素/优化 FLOPs 与最大中间张量（照抄 dynamic 同名函数）。

    用 ``opt_einsum.contract_path`` 零内存占位符分析；朴素路径为顺序
    左到右，优化路径按 cached_contract 的选优化器逻辑。仅当
    optimize=True 时尝试 ['auto','greedy','optimal','dp'] 全集。

    Returns:
        (naive_flops, opt_flops, speedup, largest_intermediate_bytes,
         opt_name)；失败返回 (0, 0, 1.0, 0, 'N/A')。
        （对原版的唯一偏离：opt_einsum 缺失时亦返回该兜底而非 ImportError。）
    """
    try:
        from opt_einsum import contract_path
    except ImportError as _e:
        _log(f'    [FLOP分析] opt_einsum 不可用: {_e}')
        return 0, 0, 1.0, 0, 'N/A'
    import numpy as np

    n = len(shapes)
    if n < 2:
        return 0, 0, 1.0, 0, 'N/A'

    placeholders = [
        np.broadcast_to(np.empty((), dtype=np.float64), s)
        for s in shapes
    ]

    try:
        _, naive_info = contract_path(
            einsum_str, *placeholders,
            optimize=[(0, 1)] * (n - 1))
        naive_flops = int(naive_info.opt_cost)
    except Exception as _e:
        _log(f'    [FLOP naive path 失败] {type(_e).__name__}: {_e}')
        naive_flops = 0

    if isinstance(optimize, str):
        candidate_opts = [optimize]
    elif optimize is True:
        candidate_opts = ['auto', 'greedy', 'optimal', 'dp']
    elif isinstance(optimize, list):
        candidate_opts = optimize
    else:
        candidate_opts = ['auto']

    best_path_info = None
    best_cost = (float('inf'), float('inf'))
    best_opt_name = 'N/A'

    for opt in candidate_opts:
        try:
            _, path_info = contract_path(
                einsum_str, *placeholders, optimize=opt)
            cost = (int(path_info.opt_cost),
                    int(path_info.largest_intermediate))
            if cost < best_cost:
                best_cost = cost
                best_path_info = path_info
                best_opt_name = opt
        except Exception as _e:
            _log(f'    [FLOP optimize={opt} 失败] {type(_e).__name__}: {_e}')
            continue

    if best_path_info is None:
        return naive_flops, 0, 1.0, 0, 'N/A'

    opt_flops = int(best_path_info.opt_cost)
    largest_intermediate = int(best_path_info.largest_intermediate)
    speedup = naive_flops / max(opt_flops, 1)
    li_bytes = largest_intermediate * 16   # complex128

    return naive_flops, opt_flops, speedup, li_bytes, best_opt_name

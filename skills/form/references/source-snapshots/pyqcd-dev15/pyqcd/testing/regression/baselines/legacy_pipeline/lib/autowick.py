"""
Automatic Wick Contraction Engine
=================================

Core Wick contraction enumeration for arbitrary multi-hadron operators.
Given sink, source, and (optionally) current operators as string lists,
generates all valid quark-antiquark pairings (contraction diagrams) with
their Fermi signs, perambulator assignments, VVV/VDV vertex assignments,
and gamma matrix insertions.

Supports wildcards 'q'/'q^d' (all 6 flavors) and 'l'/'l^d' (light u,d).

Main entry point: ``wick_contraction()``

Adapted from lqcddb contraction/autowick.py.
"""

import numpy as np
from typing import List, Literal, Union
from collections import Counter
from itertools import product, permutations, combinations
import itertools

# ═══════════════════════════════════════════════════════════════════
# Fermion sign computation
# ═══════════════════════════════════════════════════════════════════

def _count_inversions(lst: list) -> int:
    """Count inversions (out-of-order pairs) in a list."""
    inv = 0
    n = len(lst)
    for i in range(n):
        for j in range(i + 1, n):
            if lst[i] > lst[j]:
                inv += 1
    return inv


def _compute_fermion_sign(contraction_pairs: list) -> int:
    """Compute Fermi sign = (-1)^{#inversions} from contraction pairs.

    Each pair is (quark_position, antiquark_position). The sign comes
    from reordering the fermion fields to pair them.
    """
    indexed_positions = []
    for pair_idx, pair in enumerate(contraction_pairs):
        q_pos, aq_pos = pair[0], pair[1]
        indexed_positions.append((q_pos, pair_idx))
        indexed_positions.append((aq_pos, pair_idx))

    pair_indices = [x[0] for x in indexed_positions]
    return (-1) ** _count_inversions(pair_indices)


# ═══════════════════════════════════════════════════════════════════
# Valid contraction generation (flavor-conserving perfect matchings)
# ═══════════════════════════════════════════════════════════════════

def _generate_valid_contractions(quark_pos: list) -> tuple:
    """Generate all flavor-conserving quark-antiquark pairings.

    Groups quarks by flavor, then for each flavor generates all
    permutations matching quarks to antiquarks. Returns the Cartesian
    product across flavors.

    Returns
    -------
    (all_diagrams, num_diagrams)
        all_diagrams: list of diagrams, each a list of (quark_info, antiquark_info) pairs
        num_diagrams: total number of diagrams
    """
    flavor_quarks = {}
    flavor_antiquarks = {}

    for pos, qtype, label in quark_pos:
        if '^d' in qtype:
            base_flavor = qtype.replace('^d', '')
            flavor_antiquarks.setdefault(base_flavor, []).append((pos, qtype, label))
        else:
            flavor_quarks.setdefault(qtype, []).append((pos, qtype, label))

    flavor_matchings = []
    for flavor in sorted(set(list(flavor_quarks.keys()) + list(flavor_antiquarks.keys()))):
        qs = flavor_quarks.get(flavor, [])
        aqs = flavor_antiquarks.get(flavor, [])

        if len(qs) != len(aqs):
            raise ValueError(
                f"Flavor '{flavor}' quark count({len(qs)}) "
                f"≠ anti-quark count({len(aqs)})")

        if not qs:
            continue

        matchings = []
        for perm in permutations(range(len(aqs))):
            matching = []
            for q_idx in range(len(qs)):
                aq_idx = perm[q_idx]
                matching.append((qs[q_idx], aqs[aq_idx]))
            matchings.append(matching)

        flavor_matchings.append(matchings)

    if not flavor_matchings:
        return [[]], 1

    all_diagrams = []
    for combo in itertools.product(*flavor_matchings):
        diagram = []
        for flavor_matching in combo:
            diagram.extend(flavor_matching)
        all_diagrams.append(diagram)

    return all_diagrams, len(all_diagrams)


# ═══════════════════════════════════════════════════════════════════
# Helper: V structure naming
# ═══════════════════════════════════════════════════════════════════

def _creat_sink_source(param: dict, Vindex: list, time_labels: list) -> list:
    """Generate VVV and VDV object list from quark positions.

    Each pair of '|' separators defines a time interval. Intervals with
    3 quarks get VVV; intervals with 2 quarks get VDV.

    Returns list of [(low, high), V_name, index_string, time_label].
    """
    quark_pos = param['quark_pos']
    sep_pos = param['sep_pos']
    sorted_sep = sorted(sep_pos)
    pairs = [(sorted_sep[i], sorted_sep[i + 1]) for i in range(0, len(sorted_sep), 2)]
    intervals = [(min(p), max(p)) for p in pairs]

    result = []
    for i_indx, (low, high) in enumerate(intervals):
        candidates = []
        for idx, (pos, typ, label) in enumerate(quark_pos):
            if low <= pos <= high:
                second_letter = label[1]
                has_carat = '^d' in typ
                candidates.append((idx, second_letter, has_carat))
        candidates.sort(key=lambda x: (x[2], x[0]))
        sorted_letters = [letter for _, letter, _ in candidates]

        if len(sorted_letters) == 3:
            result.append([(low, high), f'VVV_{i_indx}',
                          Vindex[i_indx] + ''.join(sorted_letters),
                          time_labels[i_indx]])
        elif len(sorted_letters) == 2:
            result.append([(low, high), f'VDV_{i_indx}',
                          Vindex[i_indx] + ''.join(sorted_letters[::-1]),
                          time_labels[i_indx]])
    return result


def _keep_unique_letters(s: str) -> str:
    """Extract free (uncontracted) indices from a contraction string.

    Lowercase letters appearing once = free spin indices.
    Uppercase letters = free momentum/link indices (first occurrence).
    """
    counts_lower = Counter(ch for ch in s if ch.islower())
    counts_upper = Counter(ch for ch in s if ch.isupper())

    result_lower = []
    result_upper = []

    s_no_comma = s.replace(',', '')
    for ch in s_no_comma:
        if ch.islower():
            if counts_lower[ch] == 1:
                result_lower.append(ch)
        else:
            if counts_upper[ch] >= 1 and ch not in result_upper:
                result_upper.append(ch)

    if len(result_lower) == 2:
        _result = [None] * len(result_lower)
        segments = s.split(',')
        for i_indx, i in enumerate(result_lower):
            _result[
                [y_indx for x in segments for y_indx, y in enumerate(x) if y == i][0]
            ] = i
        _result = _result + result_upper
    else:
        _result = result_lower + result_upper

    return ''.join(_result)


def _add_sep_sign(operator: List[str]) -> List[str]:
    """Ensure operator list starts and ends with '|'."""
    operator = [x for x in operator if isinstance(x, str)]
    if operator:
        if operator[0] != '|':
            operator = ['|'] + operator
        if operator[-1] != '|':
            operator = operator + ['|']
    return operator


# ═══════════════════════════════════════════════════════════════════
# Main Wick contraction function
# ═══════════════════════════════════════════════════════════════════

def wick_contraction(
    sink_operators: List[str],
    source_operators: List[str],
    curr_operators: List[str] = None,
    Cpt: Literal['bubble', '2pt', '3pt', '4pt'] = '2pt',
    Pindex: list = None, Vindex: list = None, Gindex: list = None,
) -> Union[dict, List[dict]]:
    """Auto Wick contraction for N-particle operators separated by '|'.

    Enumerates all valid Wick contractions for given sink, source, and
    (optionally) current operators. Supports wildcards 'q'/'q^d' (all
    6 flavors) and 'l'/'l^d' (light u,d only).

    Parameters
    ----------
    sink_operators : list of str
        Sink operator, may contain flavor labels, gamma names,
        separators '|', and wildcards.
    source_operators : list of str
        Source operator, same format.
    curr_operators : list of str, optional
        Current insertion operator (for 3pt/4pt). Ignored for '2pt'.
    Cpt : {'bubble','2pt','3pt','4pt'}
        Correlation function type.
    Pindex : list of str, optional
        Prefix letters for peram objects. Auto-generated if None.
    Vindex : list of str, optional
        Prefix letters for VVV/VDV objects. Auto-generated if None.
    Gindex : list of str, optional
        Prefix letters for gamma insertions. Auto-generated if None.

    Returns
    -------
    dict or list of dict
        If no wildcards: single dict with keys 'result_indx', 'result_name',
        'result_sign', 'operators', 'sink_operators', 'source_operators',
        'curr_operators', 'quark_pos', 'sep_pos', 'gamma_pos', 'V', 'peram'.
        If wildcards present: list of such dicts (one per flavor substitution).
    """
    if curr_operators is None:
        curr_operators = []

    # ── Flavor lists and contraction index pool ──
    quark_list = (['u', 'd', 's', 'c', 'b', 't']
                  + [x + '^d' for x in ['u', 'd', 's', 'c', 'b', 't']])
    contraction_index = [
        'ab', 'cd', 'ef', 'mn', 'op', 'gh', 'ij', 'kl', 'qr', 'st', 'uv', 'wx', 'yz',
        'AB', 'CD', 'EF', 'MN', 'OP', 'GH', 'IJ', 'KL', 'QR', 'ST', 'UV', 'WX', 'YZ'
    ]

    # 2pt ignores current operators
    if Cpt == '2pt':
        curr_operators = []

    # ── Extract overall coefficient ──
    operators = sink_operators + curr_operators + source_operators
    overall_sign = complex(np.prod([
        x for x in operators if isinstance(x, (int, complex, float))]))

    # Add separators
    sink_operators = _add_sep_sign(sink_operators)
    source_operators = _add_sep_sign(source_operators)
    curr_operators = _add_sep_sign(curr_operators)
    operators = sink_operators + curr_operators + source_operators

    operators_str = [x for x in operators if isinstance(x, str)]

    # ── Wildcard handling ──
    FLAVORS_ALL = ['u', 'd', 's', 'c', 'b', 't']
    FLAVORS_LIGHT = ['u', 'd']

    wildcard_positions = []
    for idx, op in enumerate(operators_str):
        if op in ('q', 'q^d', 'l', 'l^d'):
            wildcard_positions.append((idx, op))

    if not wildcard_positions:
        substitutions = [operators_str]
    else:
        choices = []
        for idx, wc in wildcard_positions:
            if wc == 'q':
                choices.append(FLAVORS_ALL)
            elif wc == 'q^d':
                choices.append([f + '^d' for f in FLAVORS_ALL])
            elif wc == 'l':
                choices.append(FLAVORS_LIGHT)
            elif wc == 'l^d':
                choices.append([f + '^d' for f in FLAVORS_LIGHT])

        substitution_list = []
        for combo in itertools.product(*choices):
            new_ops = list(operators_str)
            for (idx, _), val in zip(wildcard_positions, combo):
                new_ops[idx] = val
            substitution_list.append(new_ops)
        substitutions = substitution_list

    # ── Slice lengths ──
    len_sink = len([x for x in sink_operators if isinstance(x, str)])
    len_curr = len([x for x in curr_operators if isinstance(x, str)])
    len_src = len([x for x in source_operators if isinstance(x, str)])

    all_params = []

    for ops_sub in substitutions:
        # Check quark-antiquark balance
        num = Counter([x for x in ops_sub if x in quark_list])
        balanced = True
        for q in set([x.replace('^d', '') for x in ops_sub if x in quark_list]):
            if num[q] != num[q + '^d']:
                balanced = False
                break
        if not balanced:
            continue

        param = {}
        param['operators'] = ops_sub
        param['sink_operators'] = ops_sub[:len_sink]
        param['curr_operators'] = ops_sub[len_sink:len_sink + len_curr]
        param['source_operators'] = ops_sub[len_sink + len_curr:]

        param['quark_pos'] = []
        param['sep_pos'] = []
        param['gamma_pos'] = []

        # Parse operators
        for _pi, _p in enumerate(ops_sub):
            if _p in quark_list:
                param['quark_pos'].append((_pi, _p))
            elif 'gamma' in _p:
                param['gamma_pos'].append((_pi, _p))
            elif '|' == _p:
                param['sep_pos'].append(_pi)

        # Assign contraction labels
        for i, qp in enumerate(param['quark_pos']):
            param['quark_pos'][i] = (*qp, contraction_index[i])

        # Generate all valid contractions
        all_diagrams, num_diag = _generate_valid_contractions(param['quark_pos'])

        param['peram'] = []
        param['result_sign'] = []

        # ── Time intervals and labels ──
        sorted_sep = sorted(param['sep_pos'])
        intervals = []
        for i in range(0, len(sorted_sep), 2):
            if i + 1 < len(sorted_sep):
                intervals.append((sorted_sep[i] + 1, sorted_sep[i + 1] - 1))
        n_intervals = len(intervals)

        time_labels = []
        curr_count = 0
        for j in range(0, len(sorted_sep), 2):
            if j + 1 >= len(sorted_sep):
                break
            sep_close = sorted_sep[j + 1]
            sep_open = sorted_sep[j]
            if sep_close < len_sink:
                time_labels.append('tsink')
            elif sep_open >= len_sink + len_curr:
                time_labels.append('tsrc')
            else:
                time_labels.append(f'tcur{curr_count}')
                curr_count += 1

        pos_to_time = {}
        for idx, (start, end) in enumerate(intervals):
            label = time_labels[idx]
            for pos in range(start, end + 1):
                pos_to_time[pos] = label

        def _pad_or_gen(lst, n):
            if lst is None or len(lst) == 0:
                return [''] * n
            else:
                return lst + [''] * (n - len(lst))

        _Pindex = _pad_or_gen(Pindex, n_intervals)
        _Vindex = _pad_or_gen(Vindex, n_intervals)
        _Gindex = _pad_or_gen(Gindex, len(param['gamma_pos']))

        # Gamma matrix handling
        gamma_result = []
        for cut_indx, cut in enumerate(param['gamma_pos']):
            pos = [cut[0] - 1, cut[0] + 1]
            letters = []
            for _param in param['quark_pos']:
                if _param[0] in pos:
                    letters.append(_param[2][0])
            combined = _Gindex[cut_indx] + ''.join(letters)
            gamma_result.append((*cut, combined, pos_to_time.get(cut[0], '?')))
        param['gamma_pos'] = gamma_result

        # Build peram entries and compute signs
        for diagram in all_diagrams:
            combo_entry = []
            for quark_info, antiquark_info in diagram:
                q_pos, q_type, q_label = quark_info
                aq_pos, aq_type, aq_label = antiquark_info
                combined_type = q_type + aq_type
                combined_label = q_label[0] + aq_label[0] + q_label[1] + aq_label[1]
                t_q = pos_to_time.get(q_pos, '?')
                t_aq = pos_to_time.get(aq_pos, '?')
                combo_entry.append([q_pos, aq_pos, combined_type,
                                   combined_label, [t_q, t_aq]])
            param['peram'].append(combo_entry)
            sign = _compute_fermion_sign(
                [(entry[0], entry[1]) for entry in combo_entry])
            param['result_sign'].append(sign * overall_sign)

        # VVV / VDV entries
        param['V'] = _creat_sink_source(param=param, Vindex=_Vindex,
                                         time_labels=time_labels)

        # Generate index and name strings
        param['result_indx'] = []
        param['result_name'] = []
        for diag_indx in range(num_diag):
            _result_indx = ','.join(
                [x[3] for x in param['peram'][diag_indx]]
                + [x[2] for x in param['gamma_pos']]
                + [x[2] for x in param['V']]
            )
            param['result_indx'].append(
                [_result_indx + '->' + _keep_unique_letters(_result_indx)])

            _result_name = ', '.join(
                [f'peram_{x[2][0]}' for x in param['peram'][diag_indx]]
                + [x[1] for x in param['gamma_pos']]
                + [x[1] for x in param['V']]
            )
            param['result_name'].append([_result_name])

        all_params.append(param)

    if not wildcard_positions:
        return all_params[0] if all_params else {}
    else:
        return all_params


# ═══════════════════════════════════════════════════════════════════
# Equivalent diagram identification
# ═══════════════════════════════════════════════════════════════════

from collections import defaultdict
import itertools as _it


def _find_connected_groups(four_dim_list):
    """Union-Find connected components from a list of variant groups."""
    n = len(four_dim_list)
    if n == 0:
        return []

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    key_to_groups = defaultdict(list)
    for group_idx, group in enumerate(four_dim_list):
        for item in group:
            key = tuple(tuple(sublist) for sublist in item)
            key_to_groups[key].append(group_idx)

    for groups in key_to_groups.values():
        if len(groups) > 1:
            first = groups[0]
            for g in groups[1:]:
                union(first, g)

    components = defaultdict(list)
    for i in range(n):
        components[find(i)].append(i)

    result = [sorted(indices) for indices in components.values()]
    result.sort(key=lambda x: x[0])
    return result


def _generate_all_swaps(original, swap_pairs):
    """Generate all swap variants by toggling swap pairs."""
    n = len(swap_pairs)
    results = []
    for enabled in _it.product([False, True], repeat=n):
        mapping = {}
        for (a, b), do_swap in zip(swap_pairs, enabled):
            if do_swap:
                mapping[a] = b
                mapping[b] = a
        transformed = [[mapping.get(x, x) for x in sub] for sub in original]
        results.append(transformed)
    return results


def identify_equivalent_diagrams(*dicts):
    """Identify equivalent Wick contraction diagrams across groups.

    Finds diagrams that are equivalent under quark-flavor permutations
    induced by gamma matrix insertions, combining their coefficients.

    Parameters
    ----------
    *dicts : dict
        One or more wick_contraction result dictionaries.

    Returns
    -------
    list of list of tuple
        Each sublist is an equivalence class: [(dict_idx, diag_idx, coeff), ...]
        where coeff = result_sign * variant_swap_sign.
    """
    from .baroperator import GAMMA_PROPERTIES

    data = []
    diag_meta = []

    for dict_idx, _dicts in enumerate(dicts):
        gamma_names = [x[1] for x in _dicts['gamma_pos']]
        change_quark_pos = [[int(x[0]) - 1, int(x[0]) + 1]
                           for x in _dicts['gamma_pos']]

        swap_signs = []
        for gname in gamma_names:
            t_sign = GAMMA_PROPERTIES[gname]["T"][0]
            swap_signs.append(-t_sign)

        peram = [[y[:2] + [y[2].replace('d', 'u')] for y in x]
                 for x in _dicts['peram']]

        for diag_idx, peram_entry in enumerate(peram):
            variants = _generate_all_swaps(peram_entry, change_quark_pos)
            sorted_variants = [sorted(v, key=lambda x: x[0]) for v in variants]
            data.append(sorted_variants)

            n = len(change_quark_pos)
            variant_signs = []
            for enabled in _it.product([False, True], repeat=n):
                vs = complex(1.0)
                for i, do_swap in enumerate(enabled):
                    if do_swap:
                        vs *= swap_signs[i]
                variant_signs.append(vs)

            diag_meta.append((dict_idx, diag_idx,
                            _dicts['result_sign'][diag_idx], variant_signs))

    raw_groups = _find_connected_groups(data)

    # Build variant → diag index for BFS
    variant_to_diags = {}
    for diag_idx, variants in enumerate(data):
        for v_idx, variant in enumerate(variants):
            key = tuple(tuple(sublist) for sublist in variant)
            variant_to_diags.setdefault(key, []).append((diag_idx, v_idx))

    equivalent_diagrams = []
    for group in raw_groups:
        canonical_idx = group[0]
        group_set = set(group)

        _, _, canonical_rs, _ = diag_meta[canonical_idx]
        coeffs = {canonical_idx: canonical_rs}

        from collections import deque
        queue = deque([canonical_idx])

        while queue:
            cur = queue.popleft()
            cur_coeff = coeffs[cur]
            cur_d_idx, cur_diag, cur_rs, cur_vs_list = diag_meta[cur]

            for v_cur, variant in enumerate(data[cur]):
                key = tuple(tuple(sublist) for sublist in variant)
                for neighbor, v_neighbor in variant_to_diags.get(key, []):
                    if neighbor == cur or neighbor not in group_set or neighbor in coeffs:
                        continue
                    n_d_idx, n_diag, n_rs, n_vs_list = diag_meta[neighbor]
                    n_coeff = cur_coeff * (n_rs / cur_rs) * (
                        n_vs_list[v_neighbor] / cur_vs_list[v_cur])
                    coeffs[neighbor] = n_coeff
                    queue.append(neighbor)

        group_entries = []
        for diag_idx in sorted(group):
            d_idx, d_diag, result_sign, _ = diag_meta[diag_idx]
            total_sign = coeffs.get(diag_idx, result_sign)
            group_entries.append((d_idx, d_diag, total_sign))

        equivalent_diagrams.append(group_entries)

    return equivalent_diagrams

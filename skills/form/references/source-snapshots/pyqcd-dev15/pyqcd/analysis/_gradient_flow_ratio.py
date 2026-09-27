"""
参考 schema-v2 梯度流胶子 disconnected C3/C2 统计。

输入 OPE 的轴为
``(configuration, channel, z_orientation, component, z, t)``；
输入两点函数的轴为
``(channel, direction, configuration, tsep, t_source, momentum)``。

统计层保留完整复数。特别是 helicity 通道使用完整 `pol35` 两点函数
构造 covariance；只有在显示或物理相位投影阶段才取
``Re[-i R_H] = Im(R_H)``。
"""
from __future__ import annotations

import numpy as np

from ..operator._gradient_flow_gluon_ope import (
    CHANNELS, COMPONENTS, ORIENTATIONS,
)


POLARIZATION_FOR_CHANNEL = {
    "unpolarized": "nopol",
    "helicity": "pol35",
}
RATIO_SCHEMA = "gradient_flow_gluon_ratio_v2"


def _as_complex128(value, name):
    array = np.asarray(value, dtype=np.complex128)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} 含非有限值")
    return array


def _validate_tseps(tseps, nt):
    values = list(tseps)
    if not values:
        raise ValueError("tseps 不能为空")
    if any(isinstance(value, (bool, np.bool_))
           or not isinstance(value, (int, np.integer))
           for value in values):
        raise ValueError("tseps 必须是整数")
    values = [int(value) for value in values]
    if len(set(values)) != len(values):
        raise ValueError("tseps 不得重复")
    if min(values) < 0 or max(values) >= nt:
        raise ValueError("tseps 必须满足 0 <= tsep < Nt")
    return values


def covariance_ratio_estimator(operator, correlator, do_jackknife=True,
                               denominator_correlator=None):
    """计算一个插入量的 disconnected ratio 和 delete-one jackknife。

    Args:
        operator: ``(Nconf, Nobservable, Nsource)``，完整复数 OPE。
        correlator: ``(Nconf, Nsource, Nmomentum)``，C3 covariance 所用
            投影；unpolarized 使用 nopol，helicity 使用 pol35。
        do_jackknife: 是否生成 Nconf 个 delete-one 样本。
        denominator_correlator: ratio 分母的 C2；省略时使用 correlator。

    Returns:
        ``(c3_central, c2_central, ratio_jk_mean,
        ratio_jk_bias_corrected, error_real, error_imag)``。
        central ratio 不做实部/虚部截断。
    """
    op = _as_complex128(operator, "operator")
    c2 = _as_complex128(correlator, "correlator")
    denominator = (
        c2 if denominator_correlator is None
        else _as_complex128(denominator_correlator, "denominator_correlator")
    )
    if op.ndim != 3 or c2.ndim != 3:
        raise ValueError(
            f"需要 operator=(conf,observable,source)、C2=(conf,source,momentum)，"
            f"收到 {op.shape} 与 {c2.shape}")
    if op.shape[0] != c2.shape[0] or op.shape[2] != c2.shape[1]:
        raise ValueError(f"operator/C2 轴不匹配: {op.shape}, {c2.shape}")
    if denominator.shape != c2.shape:
        raise ValueError(
            f"denominator C2 形状必须与 correlator 一致: "
            f"{denominator.shape} != {c2.shape}")
    nconf = int(op.shape[0])
    if nconf < 2:
        raise ValueError("delete-one ratio 至少需要两个组态")
    nsource = int(op.shape[2])

    sum_o = np.sum(op, axis=0)
    sum_c = np.sum(c2, axis=0)
    sum_denominator = np.sum(denominator, axis=0)
    oc_mean_source = np.einsum("nos,nsp->op", op, c2, optimize=True) / nsource
    o_times_c_mean_source = (
        np.einsum("os,sp->op", sum_o, sum_c, optimize=True) / nsource
    )
    c3_central = (
        oc_mean_source / nconf
        - o_times_c_mean_source / (nconf * nconf)
    )
    c2_central = np.mean(sum_denominator, axis=0) / nconf
    if np.any(~np.isfinite(c2_central)) or np.any(c2_central == 0.0):
        raise FloatingPointError("ratio denominator C2 contains zero/non-finite value")

    shape = c3_central.shape
    nan_complex = np.full(shape, np.nan + 1j * np.nan, dtype=np.complex128)
    nan_real = np.full(shape, np.nan, dtype=np.float64)
    if not do_jackknife:
        return (
            c3_central, c2_central, nan_complex,
            nan_complex.copy(), nan_real, nan_real.copy(),
        )

    nminus = nconf - 1
    own_oc_mean_source = np.einsum(
        "nos,nsp->nop", op, c2, optimize=True
    ) / nsource
    own_o_times_total_c = np.einsum(
        "nos,sp->nop", op, sum_c, optimize=True
    ) / nsource
    total_o_times_own_c = np.einsum(
        "os,nsp->nop", sum_o, c2, optimize=True
    ) / nsource
    c3_jackknife = (
        (oc_mean_source[None, ...] - own_oc_mean_source) / nminus
        - (
            o_times_c_mean_source[None, ...]
            - own_o_times_total_c
            - total_o_times_own_c
            + own_oc_mean_source
        ) / (nminus * nminus)
    )
    c2_jackknife = (
        np.mean(sum_denominator, axis=0)[None, :]
        - np.mean(denominator, axis=1)
    ) / nminus
    if np.any(~np.isfinite(c2_jackknife)) or np.any(c2_jackknife == 0.0):
        raise FloatingPointError(
            "delete-one ratio denominator contains zero/non-finite value")
    ratio_jackknife = c3_jackknife / c2_jackknife[:, None, :]
    jk_mean = np.mean(ratio_jackknife, axis=0)
    jk_bias_corrected = nconf * (c3_central / c2_central[None, :]) \
        - nminus * jk_mean
    prefactor = nminus / nconf
    error_real = np.sqrt(
        prefactor * np.sum(
            (ratio_jackknife.real - jk_mean.real) ** 2, axis=0
        )
    )
    error_imag = np.sqrt(
        prefactor * np.sum(
            (ratio_jackknife.imag - jk_mean.imag) ** 2, axis=0
        )
    )
    return (
        c3_central, c2_central, jk_mean, jk_bias_corrected,
        error_real, error_imag,
    )


def _component_labels_for_count(ncomp, component_labels):
    if component_labels is None:
        if ncomp == len(COMPONENTS):
            labels = COMPONENTS
        elif ncomp == 3:
            labels = COMPONENTS[:3]
        else:
            labels = tuple(f"component_{index}" for index in range(ncomp))
    else:
        labels = tuple(component_labels)
    if len(labels) != ncomp or len(set(labels)) != len(labels):
        raise ValueError("component_labels 必须与 component 轴一一对应且不重复")
    return labels


def calculate_gradient_flow_ratios(ope, twopt, tseps, do_jackknife=True,
                                   component_labels=None):
    """按参考 ratio-v2 轴构造所有 channel/orientation/component ratio。

    Args:
        ope: ``(conf,2,4,ncomp,nz,Nt)`` complex OPE。
        twopt: ``(2,ndirection,conf,ntsep,Nt,nmomentum)`` complex C2；
            channel 0 必须为 nopol，channel 1 为 pol35。
        tseps: 与 twopt 的 ``ntsep`` 轴对应的 separation 列表。

    Returns:
        字典，包含 `c3_mean`、`c2_mean`、`ratio`、jackknife 统计和
        `valid_insertion_mask`。ratio 轴为
        ``(channel,orientation,component,direction,z,tsep,insertion,momentum)``。
    """
    ope = _as_complex128(ope, "ope")
    twopt = _as_complex128(twopt, "twopt")
    if ope.ndim != 6:
        raise ValueError("ope 必须具有 (conf,channel,orientation,component,z,t) 六轴")
    if twopt.ndim != 6:
        raise ValueError(
            "twopt 必须具有 (channel,direction,conf,tsep,source,momentum) 六轴")
    nconf, nch, norient, ncomp, nz, nt = ope.shape
    nch2, ndir, nconf2, ndt, nt2, nmom = twopt.shape
    if (nch, norient) != (len(CHANNELS), len(ORIENTATIONS)):
        raise ValueError(
            f"ope channel/orientation 轴必须为 (2,4)，收到 {ope.shape}")
    if (nch2, nconf2, nt2) != (nch, nconf, nt):
        raise ValueError(f"输入 OPE/C2 轴不匹配: {ope.shape}, {twopt.shape}")
    if ncomp <= 0 or nz <= 0 or nt <= 0:
        raise ValueError("ope 的 component/z/time 轴必须非空")
    component_labels = _component_labels_for_count(
        ncomp, component_labels
    )
    tseps = _validate_tseps(tseps, nt)
    if len(tseps) != ndt:
        raise ValueError(
            f"tseps 长度 {len(tseps)} 与 twopt tsep 轴 {ndt} 不一致")
    if nconf < 2 and do_jackknife:
        raise ValueError("jackknife 至少需要两个组态")

    max_tsep = max(tseps)
    out_shape = (
        nch, norient, ncomp, ndir, nz, ndt, max_tsep + 1, nmom
    )
    nan_complex = np.full(out_shape, np.nan + 1j * np.nan, dtype=np.complex128)
    c3 = nan_complex.copy()
    ratio = nan_complex.copy()
    jk_mean = nan_complex.copy()
    jk_bias = nan_complex.copy()
    nan_real = np.full(out_shape, np.nan, dtype=np.float64)
    jk_err_real = nan_real.copy()
    jk_err_imag = nan_real.copy()
    c2_mean = np.empty((nch, ndir, ndt, nmom), dtype=np.complex128)

    source = np.arange(nt)
    for channel in range(nch):
        for direction in range(ndir):
            c2_by_dt = twopt[channel, direction]
            denominator_by_dt = twopt[0, direction]
            c2_mean[channel, direction] = np.mean(
                denominator_by_dt, axis=(0, 2)
            )
            for insertion in range(max_tsep + 1):
                shifted = np.take(
                    ope[:, channel],
                    (source + insertion) % nt,
                    axis=-1,
                )
                flat = shifted.reshape(nconf, norient * ncomp * nz, nt)
                for dt_index, dt in enumerate(tseps):
                    if insertion > dt:
                        continue
                    result = covariance_ratio_estimator(
                        flat,
                        c2_by_dt[:, dt_index],
                        do_jackknife=do_jackknife,
                        denominator_correlator=denominator_by_dt[:, dt_index],
                    )
                    c3_one, c2_one, mean_one, bias_one, err_r, err_i = result
                    shape = (norient, ncomp, nz, nmom)
                    target = (
                        channel, slice(None), slice(None), direction,
                        slice(None), dt_index, insertion, slice(None),
                    )
                    c3[target] = c3_one.reshape(shape)
                    central_ratio = c3_one / c2_one[None, :]
                    ratio[target] = central_ratio.reshape(shape)
                    jk_mean[target] = mean_one.reshape(shape)
                    jk_bias[target] = bias_one.reshape(shape)
                    jk_err_real[target] = err_r.reshape(shape)
                    jk_err_imag[target] = err_i.reshape(shape)

    valid_insertion = np.zeros((ndt, max_tsep + 1), dtype=bool)
    for index, dt in enumerate(tseps):
        valid_insertion[index, :dt + 1] = True
    return {
        "c3_mean": c3,
        "c2_mean": c2_mean,
        "ratio": ratio,
        "ratio_jackknife_mean": jk_mean,
        "ratio_jackknife_bias_corrected": jk_bias,
        "ratio_jackknife_error_real": jk_err_real,
        "ratio_jackknife_error_imag": jk_err_imag,
        "valid_insertion_mask": valid_insertion,
        "schema": RATIO_SCHEMA,
        "channel_labels": tuple(CHANNELS),
        "z_orientation_labels": tuple(ORIENTATIONS),
        "component_labels": component_labels,
        "direction_labels": tuple(range(ndir)),
        "axes": (
            "channel", "z_orientation", "component", "direction",
            "z", "tsep", "insertion", "momentum_abs",
        ),
        "polarization_for_channel": dict(POLARIZATION_FOR_CHANNEL),
        "denominator_polarization": "nopol",
    }


calculate_ratios = calculate_gradient_flow_ratios


def physical_helicity_ratio(ratio, *, orientation="odd_difference",
                            component=None):
    """取参考 helicity 的最终 Euclidean 相位投影 ``Re[-i R_H]``。

    对 schema-v2 的 ``combined``，参考 OPE 文件保存的是
    ``Mtiti+Mijij``；理论目标 ``Mtiti-Mijij`` 应在 OPE 层显式选择后
    再进入 ratio。默认返回指定 orientation 下的全部 component；传入
    ``component`` 时只返回该 component。
    """
    array = np.asarray(ratio, dtype=np.complex128)
    if array.ndim < 2:
        raise ValueError("ratio 至少需要 channel/orientation 两个轴")
    try:
        io = ORIENTATIONS.index(orientation)
    except ValueError as exc:
        raise ValueError(f"未知 orientation: {orientation}") from exc
    if array.shape[0] < 2 or array.shape[1] <= io:
        raise ValueError("ratio 缺少 helicity/orientation 轴")
    selected = array[1, io]
    if component is not None:
        if component not in COMPONENTS:
            raise ValueError(f"未知 component: {component}")
        if selected.ndim < 1 or selected.shape[0] not in (3, len(COMPONENTS)):
            raise ValueError(
                "按 component 选择时，ratio 必须保留前三组件或完整六组件轴")
        component_index = COMPONENTS.index(component)
        if component_index >= selected.shape[0]:
            raise ValueError(f"ratio 未保存 component: {component}")
        selected = selected[component_index]
    return np.real(-1j * selected)


def validate_gradient_flow_ratio_results(results, *, nconf=None):
    """验证 ratio-v2 结果的轴、复数 dtype、orientation 与 component 恒等式。"""
    ratio = np.asarray(results["ratio"])
    c3 = np.asarray(results["c3_mean"])
    c2 = np.asarray(results["c2_mean"])
    jk_mean = np.asarray(results["ratio_jackknife_mean"])
    jk_bias = np.asarray(results["ratio_jackknife_bias_corrected"])
    errors = (
        np.asarray(results["ratio_jackknife_error_real"]),
        np.asarray(results["ratio_jackknife_error_imag"]),
    )
    if ratio.ndim != 8 or ratio.shape[0:2] != (2, 4):
        raise ValueError(
            "ratio 必须为 (channel=2,orientation=4,...) 八轴数组，"
            f"收到 {ratio.shape}"
        )
    complex_arrays = (ratio, c3, jk_mean, jk_bias)
    if any(array.dtype.kind != "c" for array in complex_arrays):
        raise ValueError("ratio/c3/jackknife 结果必须保持复数 dtype")
    if any(array.shape != ratio.shape for array in (c3, jk_mean, jk_bias)):
        raise ValueError("ratio/c3/jackknife 形状不一致")
    for error in errors:
        if error.shape != ratio.shape or error.dtype.kind != "f":
            raise ValueError("ratio jackknife 误差形状/dtype 错误")
    ndir, nz, ndt, nins, nmom = (
        ratio.shape[3], ratio.shape[4], ratio.shape[5],
        ratio.shape[6], ratio.shape[7],
    )
    if c2.shape != (2, ndir, ndt, nmom):
        raise ValueError(
            "c2_mean 必须为 (channel=2,direction,tsep,momentum)，"
            f"收到 {c2.shape}"
        )
    if c2.dtype.kind != "c" or not np.isfinite(c2).all():
        raise ValueError("c2_mean 必须是有限复数")
    if np.any(c2 == 0.0):
        raise ValueError("c2_mean 不能含零分母")
    if not np.array_equal(c2[0], c2[1]):
        raise ValueError("两个 channel 必须共享 nopol c2_mean 分母")
    valid = np.asarray(results["valid_insertion_mask"])
    if valid.shape != (ndt, nins) or valid.dtype != np.dtype(bool):
        raise ValueError(
            "valid_insertion_mask 形状/dtype 错误: "
            f"{valid.shape}, {valid.dtype}"
        )
    if nconf is not None and int(nconf) < 2:
        raise ValueError("ratio-v2 需要至少两个组态")
    if results.get("schema") != RATIO_SCHEMA:
        raise ValueError("ratio schema 不一致")
    if results.get("denominator_polarization") != "nopol":
        raise ValueError("ratio-v2 denominator 必须是 nopol")
    if results.get("polarization_for_channel") != POLARIZATION_FOR_CHANNEL:
        raise ValueError("channel polarization metadata 不一致")
    if tuple(results.get("channel_labels", ())) != tuple(CHANNELS):
        raise ValueError("channel_labels 不一致")
    if tuple(results.get("z_orientation_labels", ())) != tuple(ORIENTATIONS):
        raise ValueError("z_orientation_labels 不一致")
    labels = tuple(results.get("component_labels", ()))
    if len(labels) != ratio.shape[2] or len(set(labels)) != len(labels):
        raise ValueError("component_labels 与 ratio component 轴不一致")
    expected_axes = (
        "channel", "z_orientation", "component", "direction",
        "z", "tsep", "insertion", "momentum_abs",
    )
    if tuple(results.get("axes", ())) != expected_axes:
        raise ValueError("ratio axes 不一致")

    expanded_valid = np.broadcast_to(
        valid[None, None, None, None, None, :, :, None],
        ratio.shape,
    )
    for name, array in (
            ("c3_mean", c3), ("ratio", ratio),
            ("ratio_jackknife_mean", jk_mean),
            ("ratio_jackknife_bias_corrected", jk_bias),
            ("ratio_jackknife_error_real", errors[0]),
            ("ratio_jackknife_error_imag", errors[1]),
    ):
        if not np.isfinite(array[expanded_valid]).all():
            raise ValueError(f"{name} 的有效插入含非有限值")
        if not np.isnan(array[~expanded_valid]).all():
            raise ValueError(f"{name} 的无效插入必须全部为 NaN")
    if np.any(errors[0][expanded_valid] < 0.0) or np.any(
            errors[1][expanded_valid] < 0.0):
        raise ValueError("jackknife 误差不能为负")

    denominator = c2[0][None, None, None, :, None, :, None, :]
    expected_ratio = c3 / denominator
    if not np.allclose(
            ratio[expanded_valid], expected_ratio[expanded_valid],
            rtol=5e-12, atol=1e-10):
        raise ValueError("central ratio 与 c3_mean/c2_mean 不一致")

    if ratio.shape[2] == len(COMPONENTS) and labels == COMPONENTS:
        kw = {"rtol": 5e-12, "atol": 1e-10, "equal_nan": True}
        oi = {name: ORIENTATIONS.index(name) for name in ORIENTATIONS}
        checks = (
            np.allclose(
                ratio[:, oi["even_sum"]],
                ratio[:, oi["plus_z_raw"]] + ratio[:, oi["minus_z_raw"]],
                **kw,
            ),
            np.allclose(
                ratio[:, oi["odd_difference"]],
                ratio[:, oi["plus_z_raw"]] - ratio[:, oi["minus_z_raw"]],
                **kw,
            ),
        )
        if not all(checks):
            raise ValueError("ratio orientation linear identities failed")
        for name, array in (("c3_mean", c3), ("ratio", ratio)):
            odd_z0 = array[1, oi["odd_difference"], :, :, 0, :, :, :]
            odd_valid = np.broadcast_to(
                valid[None, None, :, :, None], odd_z0.shape
            )
            if not np.allclose(odd_z0[odd_valid], 0.0, **kw):
                raise ValueError(f"{name} helicity odd z=0 恒等式失败")
    return True


__all__ = [
    "RATIO_SCHEMA", "POLARIZATION_FOR_CHANNEL",
    "covariance_ratio_estimator", "calculate_gradient_flow_ratios",
    "calculate_ratios",
    "physical_helicity_ratio", "validate_gradient_flow_ratio_results",
]

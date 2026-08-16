#!/bin/bash
# =============================================================================
# Conda activate.d hook for zhangxin-snsc -- 引用式 (REFERENCE-ONLY)
# Placed at: $CONDA_PREFIX/etc/conda/activate.d/env_vars.sh
# Runs automatically on: conda activate zhangxin-snsc
# Purpose: 配合 {source ~/env.sh} 提供功能完整的 conda 环境
# v20260817: 全部环境配置已并入 ~/env.sh (configure/lib/snsc-v20260817/env.sh),
#            本钩子直接引用其环境变量, 不再重复明文路径(避免明文/便于移植套用):
#   - 经 {source ~/env.sh} 激活: ZHANGXIN_SNSC_READY=1 已设置 -> 立即返回,
#     激活零额外开销(优化启用耗时);
#   - 直接 conda activate(未经 env.sh): 载入 env.sh 兜底; 其中 CONDA_DEFAULT_ENV
#     幂等判断(钩子执行时该变量已设置)防止递归激活
# =============================================================================

if [ "${ZHANGXIN_SNSC_READY:-}" = "1" ]; then
    return 0
fi

. /public/home/zhangxin/env.sh

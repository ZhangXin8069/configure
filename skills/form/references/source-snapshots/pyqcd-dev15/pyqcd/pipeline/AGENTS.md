# AGENTS.md — pyqcd/pipeline

集中配置（`_config.py`）+ 9 步管线调度（`_runner.py`，+tmd 步）。产物写 logs/。
数据守卫（`_validate.py`，整合 data/from-logs/logs/test7/test8：check_raw_data 三类原始数据
齐全度 / check_input_arrays 形状+有限性校验 / ProgressLog+tlog ETA 进度日志）。
step_2pt 支持组态级断点续跑（corr_{ch}_{P0,P2} 全存在即跳过；recompute_2pt=True
强制重算）。
模板占位符组合式文件守卫 `check_files_existence(templates, **占位符取值列表)`
（笛卡尔积存在性 + 以首个全存在组合为基准的大小一致性，异常大小归 corrupted）。

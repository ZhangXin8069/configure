# 物理量不确定度与证据边界

## 1. 单位在边界处处理

- 输入进入计算前显式绑定单位；
- 只在输出边界转换为报告单位；
- 不直接读取带单位对象的裸 magnitude，除非同时写明目标单位；
- 摄氏/华氏温度是偏移单位，温度不确定度使用 `delta_` 类差值单位；
- dB 等对数单位先换到线性量再运算。

## 2. 测量模型

先写 measurement model，再计算。模型应包含所有修正项，即使某项估计为零；遗漏零值修正也会遗漏其不确定度。

每个输入尽量记录四项：

1. estimate；
2. standard uncertainty；
3. uncertainty distribution；
4. degrees of freedom 或来源说明。

## 3. 不确定度预算

- Type B 的 expanded uncertainty 除以证书给出的 coverage factor；
- rectangular limits 除以 `sqrt(3)`，triangular 除以 `sqrt(6)`；
- 已识别的共享校准、拟合参数或系统修正要按协方差处理，不能全部假设独立；
- 报告 sensitivity coefficient 与 `c_i u(x_i)`，而不是只列原始输入误差；
- 线性传播在强非线性、输出有界或相对不确定度较大时必须与 Monte Carlo 或极限分析交叉检查。

## 4. 报告规则

- 先修约不确定度，再用相同末位修约中心值；
- 明确 `±` 是 standard uncertainty 还是 expanded uncertainty；
- expanded uncertainty 写明 coverage factor `k`、概率与方法；
- 常数、拟合协方差和单位转换都记录来源/版本，不从记忆手填。

## 5. 物理合理性

量纲一致不等于物理上可能。额外检查：

- 数量级与已知尺度；
- Reynolds、Peclet、Knudsen 等无量纲组所处 regime；
- 扩散长度、Debye 长度、热噪声等特征尺度；
- 参数是否仍落在模型假设的适用范围。

## 6. 证据状态

报告中的关键判断使用三态：

- `确证`：有公式、代码、测试或数据输出直接支持；
- `推断`：物理上合理但仍有未验证假设；
- `未验证`：缺少基准、实验数据、收敛证据或输入不确定度。

未验证不等于错误，但不得写成已确认结果。

## 来源

适配自 `scientific-agent-skills` 的 `uncertainty-and-units` 与
`scientific-critical-thinking`，固定提交 `593377bb048752abb0152deab9fbb1083a6087df`，
MIT License；本文件只保留适用于本库物理建模的技能约束。

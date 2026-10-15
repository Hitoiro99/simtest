# 二维层流速度扩散

首期可行性案例。一个常量为运动黏度，一个工况变量为初始速度幅值；这不是平台的数据数量限制。

固定区域尺寸 0.1 × 0.1 × 0.01 m；4 × 32 × 1 六面体单元。x 周期，上下 y 壁面无滑移，z 为 empty。使用 OpenFOAM Foundation 12 的 icoFoam，时间步 0.001 s、终止时间 1 s，每 100 步保存一次完整速度场。

唯一网格资产位于案例根目录 polyMesh/。`mesh-preparation/create_example_mesh.py` 和同目录 `blockMeshDict` 用于显式制备网格，制备日志及哈希保存在 mesh-provenance/。脚本会拒绝覆盖已有 polyMesh/，不能在每次运行中重新生成案例网格。0/U 中的可信 codeStream 根据真实单元中心和工况幅值生成正弦初始速度；它是本案例的原生输入代码，运行前通过受控工具完成展开，并进入 input 快照。

参考解见 references/analytical-solution.md。首期只限制示例的输入数量，监控曲线完整保存，全部输出时刻的速度分量与模长都参与比较。

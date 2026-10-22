# 稳态二维 Couette 流

本案例验证两块平行平板间的稳态 Couette 流动：下壁静止，上壁以恒定速度沿流向运动，流向采用入口/出口边界，厚度方向采用 `empty`，不施加压力梯度。

- 计算区域：0.1 m × 0.01 m × 0.001 m；
- 网格：`polyMesh/`，两块 120×8×1 六面体单元，共 1920 个单元；
- 运动黏度：\(10^{-3}\ \mathrm{m^2/s}\)，\(Re=10\)；
- 求解器：`simpleFoam` 稳态；案例模板 `system/controlDict` 中声明 `application simpleFoam`，平台据此选择主程序；
- 迭代：0–200 步，每 20 步输出一次，共 11 个输出时刻；
- 监控：体积加权平均流向速度、每步首个 Ux 与压力线性求解初始残差；
- 场：速度与运动压力，覆盖全部输出时刻。

解析解为 \(u(y)=U\,y/H\)、\(v=w=0\)、\(p=0\)，详见 `references/startup-couette-solution.md`。`mesh-preparation/create_example_mesh.py` 与同目录的 `blockMeshDict` 只用于显式制备源网格；制备日志和哈希保存在 `mesh-provenance/`。

# 原生读取器固定结果样本

来自本机 OpenFOAM Foundation 12 构建 12-86e126a7bc4d 的真实串行运行 abd58ab99921cfa5be151e4a，保留唯一 polyMesh、初始及终止时刻 U、原生 time 字典与 controlDict。

这是读取器软件回归样本，不是用于自动判定数值模拟是否通过的基准。测试逐单元核对 native ASCII U 与读取器结果，核对 128 单元、330 节点、物理时间、最小归档数组、正体积及时间切换。这样可以发现 vtkOpenFOAMReader 输出缓存没有随时间更新的错误。

本机 VTK 9.0 使用 Float32 场数组与节点坐标，测试中对解码舍入设置 Float32 相对精度界限；该界限不进入数值报告或解析误差判定。

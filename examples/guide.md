# 可运行场景

[单栏反馈框图](feedback-loop.json) 是 3.5 in 的二维场景。参考输入 r 与返回量 m 作差，经 C(s)、G(s) 输出 y，由 H(s) 生成 m。运行以下命令（从技能根目录执行，输出目录选在任务工作区），再按端口逐一核对导出的 PNG。可对照已验证的[原生样图](feedback-loop.vsdx)和[预览](feedback-loop.png)。

```powershell
$figures = Join-Path $env:TEMP ("visio-figures-" + [guid]::NewGuid())
python scripts/check_scene.py examples/feedback-loop.json --target-width 3.5
& ./scripts/render_visio.ps1 -ScenePath examples/feedback-loop.json -OutputDirectory $figures
python scripts/audit_vsdx.py --scene examples/feedback-loop.json --directory $figures
```

下表三个工程样例的源画布宽度均为 6.5 in（165 mm）。改用于窄栏时按实际宽度重排标签和视图。

| 源文件 | 样例 | 物理约定 |
|---|---|---|
| [marine-3d.json](marine-3d.json) | `marine-frames` | 地固和体固两套右手轴采用同一相机。体固系 x 向艏、y 向右舷、z 向下，固定系独立于船体。船体与相对姿态均为示意 |
| [marine-3d.json](marine-3d.json) | `marine-six-dof` | 艏、右舷、下为体固正向。O 为示意运动原点。弧圆心沿各自的轴放置，箭头表示正转向，弧大小无量值含义 |
| [marine-fluid-domain.json](marine-fluid-domain.json) | `marine-fluid-domain` | 二维 x–z 侧剖，z 向上，航速向右，入射波向左。S₁ 为湿表面，S₂ 为自由面，S∞ 为示意远场。n 是船体外法向，指向流体。波形只示意界面形状 |

在技能根目录运行：

```powershell
python scripts/project_scene3d.py --input examples/marine-3d.json --output '<task>/marine-projected.json'
python scripts/check_scene.py '<task>/marine-projected.json' --target-width 6.5
python scripts/check_scene.py examples/marine-fluid-domain.json --target-width 6.5
& scripts/render_visio.ps1 -ScenePath '<task>/marine-projected.json' -OutputDirectory '<task>/figures'
& scripts/render_visio.ps1 -ScenePath 'examples/marine-fluid-domain.json' -OutputDirectory '<task>/figures'
python scripts/audit_vsdx.py --scene '<task>/marine-projected.json' --directory '<task>/figures'
python scripts/audit_vsdx.py --scene examples/marine-fluid-domain.json --directory '<task>/figures'
```

既有示例仍可用于核对投影和编辑能力。[coordinate-assembly.json](coordinate-assembly.json) 对比正交和透视，[hidden-lines.json](hidden-lines.json) 展示遮挡，[coordinate-twinhull.json](coordinate-twinhull.json) 验证旧场景兼容，[native-flow.json](native-flow.json) 验证粘连和原生上下标。几何回归命令为 `python -m unittest discover -s scripts -p test_geometry.py`。

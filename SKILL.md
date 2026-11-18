---
name: visio-diagrams-v5
description: "按控制与工程论文的符号和版面绘制、审校或修改原生可编辑 Visio 插图。适用于反馈框图、估计与优化控制架构、算法与信号时序、坐标姿态和物理示意，以及结构图与数据子图组合。"
---

# Visio 文档插图五代

先从图题、相邻公式或已有图中找出读者要验证的一条关系。修改已有图时先辨认现有节点、连接、符号和用户指定的改动范围；保留可复用的原生形状。仅审图时给出具体位置、与正文的矛盾和修法。

## 按图意选择表达

| 读者的问题 | 表达与依据 |
|---|---|
| 谁测量、计算什么、作用于哪里？ | 从方程列出信号的来源、接收端、名称及求和符号，再布置主通道与回路。观测器、串级、多变量和 MPC 见[控制图设计](references/control-figures.md)。 |
| 哪一步先执行，哪一拍生效？ | 判断、迭代、退出用流程图；采样、延迟、异步更新用共享时间轴。把算法内部迭代与物理系统的反馈区分开。 |
| 方向、几何或约束如何定义？ | 平面内的角度和边界用正交视图。空间关系读[空间表达](references/spatial-graphics.md)及[场景格式](references/scene3d-format.md)。按实际原点、基向量与观察方向投影，方向只旋转，作用点同时平移。船舶、流域专例见[物理约定](references/marine-schematics.md)及[文献图例](references/literature.md)。 |
| 数据能支持哪项比较？ | 用数据与科学绘图脚本生成响应、频响或相轨迹，保留源数据和配置。与原生 Visio 结构子图组合时标明可编辑范围。无数据时只表达已知结构或明确标作示意的趋势。 |

没有完全匹配的图型时，先辨认箭头表达信号传输、时间先后、物质流动还是几何方向。只有正文赋予的关系才入图。正文未给的测量、增益、时延、扰动通道或性能值应留待确认。可以先绘制有依据的部分。

## 设计和生成

以稿件实际插入宽度定画布；期刊模板、用户参考图和稿件语言优先。白底、深色线条、就近标注；灰度下仍可通过线型、符号或位置区分含义。缩印时优先重排长回路或拆分子图。字号和线宽的换算见[视觉设计](references/visual-design.md)，控制论文参照来源见[控制图设计](references/control-figures.md)。

按对象与概念建立 Visio 图层。控制模块、求和点、取样点、连接线和文字各用原生图元，连接端粘连到实际对象。坐标轴绑定原点，矩按右手约定用绕轴弧。核查隐线与载荷方向。原生形状、字体、另存和导出接口见[绘制规范](references/visio-authoring.md)。

从技能目录运行。二维输入直接使用 scene2d.json；三维输入先用 `python scripts/project_scene3d.py --input scene3d.json --output scene2d.json` 投影。下面以随附的单栏框图为例。运行前将 $figures 指向任务的输出目录，换图时同时更新 $scene 与实际栏宽。

```powershell
$scene = "examples/feedback-loop.json"
$figures = Join-Path $env:TEMP ("visio-figures-" + [guid]::NewGuid())
python scripts/check_scene.py $scene --target-width 3.5
& ./scripts/render_visio.ps1 -ScenePath $scene -OutputDirectory $figures
python scripts/audit_vsdx.py --scene $scene --directory $figures
```

## 验收与交付

沿着成图的每个回路回读一次方程，或按图意复核时序、几何、曲线与数据。再看实际栏宽和灰度下的 PNG，检查正负号与端口的对应、相交线、裁切、字体和子图对齐。结构审计只能验证文件中的对象与粘连，不能证明控制律正确。源场景、落盘 VSDX 和同版 PNG 一起更新；三维图附投影前场景。原生渲染需要 Windows 桌面版 Visio，如环境仅能检查源文件，要说明实际完成到哪一步。

运行样例见[示例索引](examples/guide.md)。涉及 Word 原位替图时读[文档集成](references/document-integration.md)。

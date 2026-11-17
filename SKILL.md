---
name: visio-diagrams-v4
description: "为论文和技术文档绘制、审校或修改原生可编辑、语义分层的 Visio 插图及同版 PNG。用于 Visio 文档插图四代、三维坐标系和姿态、六自由度、受力与力矩、流域边界和工程示意。数值曲线保留科学绘图源与数据。"
---

# Visio 文档插图四代

先确定读者要从图中确认的物理或结构关系，再选择视图、设计标注并生成原生 Visio 图形。三维源场景、投影场景、VSDX 和 PNG 同步保存。

## 选择表达

- 读实际参考图、图题、相邻正文和公式。记录主关系、约定、几何依据、图面语言和实际栏宽。参考图提供构图和标注线索，技术定义以当前任务为准。几何简化时在图注注明“示意”。
- 多坐标系用主体斜视或能直接说明变换的平面视图。六自由度用直轴与绕轴弧。边界、法向或尺寸主要在一个平面内时，用侧剖或相互对齐的正交视图。选择范式和核对物理约定时读 [船舶与流域示意](references/marine-schematics.md)，追溯原图和图号时读 [文献图例](references/literature.md)。
- 一般布局、缩放、字号和线型见 [视觉设计](references/visual-design.md)。先检查复杂图的一幅样稿。主关系受遮挡或标注拥挤时，调整视角、按物理关系拆分子图或加局部图。已有绘图、另存和插入授权可继续执行。

## 几何与原生编辑

- 三维图读 [空间表达与坐标](references/spatial-graphics.md) 和 [三维场景格式](references/scene3d-format.md)。在右手三维系定义原点、基向量、法向、作用点与矩心，用 `poses` 组合变换。点含平移，方向只旋转。每个视图统一投影，默认正交。
- 先调相机以分辨轴和主体。轴起点绑定实际原点，移位显示须注明。遮挡按不透明面计算，隐段按需省略或弱虚线。覆盖投影须有明确的透视参照或概念说明。相交面和复杂透明介质需要人工检查。
- 力用直箭头，矩用三维绕轴弧。核对法向的所属对象与正方向，以及载荷、力矩、角度和角速度的含义。分布载荷与等效合力同图时标明等效关系。
- 二维场景和渲染步骤见 [Visio 原生绘制](references/visio-authoring.md)。使用独立 `Visio.InvisibleApp`，按对象与概念分真实图层。每个面、线、弧和文字为原生二维图元，变量可斜排，中文和上下标可编辑。流程连接线按实际连接粘连。修改三维关系或相机时改源场景后重生成。

## 生成与验收

```powershell
python '<skill>/scripts/project_scene3d.py' --input '<task>/scene3d.json' --output '<task>/scene2d.json'
python '<skill>/scripts/check_scene.py' '<task>/scene2d.json' --target-width 6.5
& '<skill>/scripts/render_visio.ps1' -ScenePath '<task>/scene2d.json' -OutputDirectory '<task>/figures'
python '<skill>/scripts/audit_vsdx.py' --scene '<task>/scene2d.json' --directory '<task>/figures' --output '<task>/native-audit.json'
```

纯二维图从第二步开始。将 `--target-width` 改成实际插入宽度，单位为英寸。渲染器保存后重开文件，结构核验读取落盘 VSDX。逐图检查几何诊断、原生结构、标注对应关系、缩印和灰度效果。修订后同步导出。

可运行样例见 [场景示例](examples/guide.md)。Word 插图替换见 [文档集成](references/document-integration.md)。交付 VSDX、同版 PNG 和源场景，数值曲线附科学绘图源和数据。

# Visio 原生绘制

## 文档接口

先用 `[Type]::GetTypeFromProgID('Visio.InvisibleApp')` 检查注册状态。`New-Object -ComObject Visio.InvisibleApp` 建立独立实例；不要通过 `GetActiveObject` 接管并关闭用户已有文档。失败时先检查错误，不反复启动孤立后台进程。

脚本通过文档 API 创建形状和导出文件，不依赖屏幕坐标。需要实际 UI 操作时再加载电脑操作技能。脚本写入任务输出目录，不把生成物写入已安装技能的目录。

```powershell
& '<skill-dir>/scripts/render_visio.ps1' -ScenePath '<task-dir>/scenes.json' -OutputDirectory '<task-dir>/figures'
```

存在同名成品时默认拒绝覆盖。确需更新时使用 `-Replace`；原 `.vsdx`、PNG、SVG 会被备份到输出目录内的 `_previous`。生成和重新打开校验成功后才提交替换。任一文件失败就停止，先诊断，不用缺失/旧 PNG 继续插图。

## 场景格式

根对象为 `{"scenes": [...]}`。坐标单位为英寸、二维页面原点在左下；三维图先按空间表达规范在三维中构造，再通过统一相机投影到二维，不手工拼三轴。页面和每个几何数值必须为有限数。下列是一个完整、可运行的受力图示例；物理关系应由实际任务决定。

```json
{
  "scenes": [{
    "name": "force-diagram",
    "width": 8,
    "height": 5,
    "font": "Cambria",
    "layers": [
      {"name": "body-entity", "owner": "body", "concept": "entity"},
      {"name": "body-forces", "owner": "body", "concept": "force"},
      {"name": "body-moments", "owner": "body", "concept": "moment"}
    ],
    "shapes": [
      {"id": "body", "kind": "rect", "layer": "body-entity", "x": 2.5, "y": 1.7, "w": 3, "h": 1.2, "fill": "#DFEAF0", "line": "#314D60"},
      {"id": "force", "kind": "poly", "layer": "body-forces", "points": [[4,2.3],[4,4.0]], "line": "#216BA6", "weight": 2, "endArrow": true},
      {"id": "force-label", "kind": "text", "layer": "body-forces", "x": 4.15, "y": 3.7, "w": 0.9, "h": 0.4, "text": "F_{H}", "notation": true, "size": 22, "color": "#216BA6"},
      {"id": "moment", "kind": "poly", "layer": "body-moments", "points": [[6.2,1.8],[6.5,2.0],[6.6,2.3],[6.5,2.6],[6.2,2.8],[5.9,2.7]], "line": "#216BA6", "weight": 1.8, "endArrow": true},
      {"id": "moment-label", "kind": "text", "layer": "body-moments", "x": 5.9, "y": 1.15, "w": 1.0, "h": 0.4, "text": "M_{H}", "notation": true, "size": 22, "color": "#216BA6"}
    ]
  }]
}
```

- `name` 是安全的 Windows 基本文件名，不包含路径或扩展名。输出同名 `.vsdx`、`.png`、`.svg`，SVG 主要便于再利用；仍以原生 VSDX 为可编辑成品。
- `layers` 必须为每一层提供 `name`、`owner`、`concept`。同一个 `owner + concept` 不能声明两层，避免把同一物体的实体或同一类力拆层。
- `shapes` 的顺序就是初始前后顺序。每个形状有唯一 `id`、已声明的 `layer`，可选 `name`。不要把图层当成 Photoshop 的堆叠顺序。
- `kind` 支持 `rect`、`ellipse`、`poly`、`text`、`connector`。前两者和文字使用 `x,y,w,h`；`poly` 使用至少两个二维 `points`。
- 图形样式：`line`、`fill` 使用 `#RRGGBB`；`weight` 单位 pt；`dash`、`endArrow`、`startArrow` 为布尔值；`alpha` 是填充透明度百分数；`closed` 封闭多边形；`round` 是矩形圆角英寸数。
- 文字：`text`、`size`（pt）、`color`、可选 `font`、`align`（0 左、1 中、2 右）。布尔值 `italic` 控制原生斜体。混排时可把斜体变量与正体说明置于相邻文字框。矩形和椭圆也可直接带 `text`。
- `notation: true` 把 `F_{H}`、`Q_{01}^{(2)}` 转为原生字符上下标，不是 LaTeX 渲染器。普通流程文字默认不要开启。也可显式给 `runs: [{"start":1,"end":2,"position":"subscript"}]`；索引是无花括号纯文本的零起点 UTF-16 范围，end 不含。
- 连线：`kind: "connector"`，`from` 和 `to` 指向形状 id。脚本创建原生 Dynamic Connector，再将两端粘连到节点。可选 fromSide、toSide 各取 left、right、top、bottom 之一，将对应端固定到节点边中点；省略时由 Visio 动态选择接点；可带必要分支 `text`。必须检查导出的路径没有穿过其他节点。
- 复杂弧线、受力箭头或三维投影，用采样点构造原生 `poly`。符号与对应几何同一层；不要为每个下标建立新层。

## 验证与修订

脚本检查未知图层、重复 id、同 owner/concept 拆层、非有限数，保存后重新打开，递归检查形状图层、外来对象和连接端点，并写 `visio-audit.json`。只凭脚本退出成功不足以证明技术正确或排版合格。

查看每张 PNG，检查文字压线、曲线与符号对应、可辨认实物、力与矩心、视角和隐线。以文档实际尺寸查看最小符号。修订场景后重新生成两个交付格式；如果直接调整原生文件，也要同步更新场景及 PNG。

关于组合：可将同一分图中的同层实体部件组合，便于整体移动，组和子形状均归同一层。不要把实体、力和力矩包成一个跨层组合来替代各自的图层。脚本保持独立形状以方便编辑；需要组时可在原生文档 API 中使用 Selection.Group，再复核子形状与组的层归属。

## 三维管线

### 三维投影

```powershell
& '<bundled-python>' '<skill-dir>/scripts/project_scene3d.py' --input '<task>/scene3d.json' --output '<task>/scene2d.json'
& '<bundled-python>' '<skill-dir>/scripts/check_scene.py' '<task>/scene2d.json' --target-width 6.2
& '<skill-dir>/scripts/render_visio.ps1' -ScenePath '<task>/scene2d.json' -OutputDirectory '<task>/figures' -RasterDpi 300
```

具体字段与已实现范围见 [三维场景格式](scene3d-format.md)。`examples/coordinate-assembly.json` 为正交/透视装配体示例，`hidden-lines.json` 演示自动隐线；`coordinate-twinhull.json` 保留用于二代输入兼容，不是经试验验证的船体几何。

### 字体与导出

场景 `font` 控制拉丁字符，`fontEastAsia` 控制东亚字符，均可在形状中覆盖。默认 Arial 与 Microsoft YaHei。渲染器解析中文 Windows 的本地字体名，例如 Microsoft YaHei 对应“微软雅黑”；将 `Char.AsianFont` 显式设置为该字体。找不到请求字体就报错，不静默改成 Arial 并让中文字形自行退化。

300 dpi 为默认栅格导出分辨率，可通过 `-RasterDpi` 调整。脚本读取并在退出时恢复 Visio 原栅格分辨率设置。PNG 的高分辨率不能弥补字号过小；仍需按目标插入宽度检查。

### 排版提示检查

`check_scene.py` 提示实际字号、边界越界及文字框重叠。已知的字框重叠可能不是字形重叠；提示用于定位检查，不是自动美观评分。脚本不会把设计质量判定为通过。

连接线、背景、组和字符仍遵守结构验收。VSDX 的图层定义位于 `visio/pages/pages.xml` 的 PageSheet，不能只读 `page1.xml` 就判定没有图层。


## 结构核验与隔离

`noLine:true` 可关闭原生形状描边，用于将面填充与去重的边分开。渲染器显式关闭默认阴影、重置线型与箭头，避免继承当前模板样式。独立 InvisibleApp 不显示窗口，不枚举/关闭用户实例；COM 登录会话错误先诊断执行环境，不循环创建后台进程。

重新打开后核对原生 source ID 集合。完成导出后再运行 `audit_vsdx.py --scene <scene2d.json> --directory <figures>`，直接读已落盘包中的真实图层、成员关系、文本、逐字符上下标和粘连目标。它限定为本脚本生成的单页文件，结构通过仍须看 PNG。

可编辑范围是投影后的二维图元，不含三维约束求解。线被遮挡切分后为多个原生形状；力矩弧用采样原生折线。重调视角、姿态和力向量时改 scene3d JSON 再生成，保留 JSON 与输出同步。

VSDX、PNG、SVG 在临时文件生成、重开核验后逐文件提交；不是文件系统级多文件原子事务。失败可能留下带 token 的恢复文件，或部分已提交文件；停止并依据日志/备份恢复，不能把混版 PNG/VSDX 当成新成品。输出审计含 projectionDiagnostics，需逐项解释或处理。

原生接口依据：[Page.DrawPolyline](https://learn.microsoft.com/en-us/office/vba/api/visio.page.drawpolyline)、[Cell.GlueTo](https://learn.microsoft.com/en-us/office/vba/api/visio.cell.glueto)、[Layer.Add](https://learn.microsoft.com/en-us/office/vba/api/visio.layer.add)。

## PNG 导出与模板图层

导出显式采用源图尺寸、24位颜色、不旋转/不翻转、指定DPI。原分辨率、尺寸及修改过的颜色/透明设置在退出时恢复。OLE_COLOR 有时由 COM 返回 UInt32，恢复时按32位位模式转回 Int32，避免退出报错。

`-PngMode AlphaSafe` 为默认：采用图中未用的透明键色，加上原生白色页框，保留白底并启用带 alpha 的 PNG 导出路径。当前 Windows/Visio 实测改善了 Opaque 路径的黄色边缘杂点；这不是三维算法的结果，也不是跨版本通用保证。PNG 可能多出1像素的导出边界，插入文档仍按指定宽度。保留 `-PngMode Opaque` 供确需不带 alpha 的流程使用，并重新看图。不要把透明键色选成白色以误删白底或物体颜色。

动态连接线母版可能自行添加本地化默认图层；仅在本脚本新建文档中删除未声明的母版图层（Delete(0)，保留形状），以声明的语义图层为准。不得对用户原文档套用此清理逻辑。

设置接口：[栅格导出设置说明](https://devblogs.microsoft.com/microsoft365dev/new-visio-2010-api-for-configuring-raster-export/)、[透明键色](https://learn.microsoft.com/en-us/office/vba/api/visio.applicationsettings.rasterexporttransparencycolor)、[源图导出尺寸](https://learn.microsoft.com/en-us/office/vba/api/visio.applicationsettings.setrasterexportsize)。

# 三维场景格式与兼容性

根对象 `{"scenes":[...]}`；场景必需 `name,width,height,layers,camera,primitives`。页面英寸、二维原点左下，三维单位自行约定且全图一致。`scale` 为每三维单位的页面英寸数；文字/线宽为源图 pt；`alpha` **是填充透明度 0..100**（0 不透明）。不把它当不透明度。

## 最小示例

```json
{"scenes":[{"name":"axes","width":8,"height":5,
"layers":[{"name":"axes","owner":"body","concept":"coordinate"}],
"camera":{"eye":[6,-8,6],"target":[0,0,0],"up":[0,0,1],"scale":1.5,"origin":[4,2.5]},
"poses":{"body":{"origin":[0,0,0],"euler_deg":[5,-3,20]}},
"primitives":[{"id":"body-frame","kind":"frame","pose":"body","layer":"axes","lengths":[1,1,1],"labels":["x_{b}","y_{b}","z_{b}"]}]}]}
```

## 相机与变换

`camera`: `eye,target,up,scale,origin`；默认 target=[0,0,0]、up=[0,0,1]、scale=1、origin=[0,0]。F=unit(target-eye)，right=unit(F×up)，screenUp=right×F。eye/target 必须不同，up 不平行视线。

- `projection`: `orthographic`（默认），或 `perspective`。
- 透视：camera 坐标 X,Y,Z，以 eye 为原点，Z 沿 F；页面为 origin + scale*focal_length*(X/Z,Y/Z)。`focal_length` 默认 eye 到 target 距离；不是以度为单位的视场角。`near` 默认 .01，三维单位且大于 0。线/面跨近面时裁剪，背后文字省略并提示。近面不自动生成实体封口；切开实体须另建切面或换机位。
- 正交保留二代基于 target 的公式。正交不施加 near 裁剪；不使用远裁面或视口裁剪，越出页面由检查器提示。
- `views` 为命名相机字典；primitive 的 `view` 默认 main。各 view 的遮挡计算隔离；页面区域由 origin/scale 自行安排，不自动防止多个视图区重叠。
- `poses`: 具名局部坐标系。`parent` 默认 world，`origin` 是本系原点在父系中的位置。旋转三选一：`euler_deg:[roll,pitch,yaw]` 为主动、列向量 `Rz(yaw) Ry(pitch) Rx(roll)`；`matrix` 为 3×3；`quaternion_xyzw` 为单位 [x,y,z,w]。不隐式转换其它库的角序/四元数顺序。
- 递归组合 `R_world=R_parent R_local`，`o_world=o_parent+R_parent o_local`。检查正交性、det=+1、单位四元数和父系循环；拒绝反射/缩放。world/main 为保留名。

## 通用字段

primitive 必须有唯一 `id`、已声明 `layer`、`kind`；可选 `pose`（默认 world）和 `view`。样式 `line,fill,weight,alpha,dash,size,color,font,fontEastAsia`；颜色 #RRGGBB。`order` 为绘制阶段而非语义图层；面默认100、边110、向量200、轴210、力矩220、文字300，同阶段面从远到近。

`visibility:occlude` 默认对线进行遮挡；`overlay` 刻意覆盖实体。`hidden:omit|dash` 控制隐段（实体边默认 dash，其它线默认 omit），`hidden_line` 默认 #9AA6AE，`hidden_weight` 默认 .65 pt。省略的部分无形状；dash 部分可独立编辑。拆分不产生中途箭头，隐藏/被近裁剪的原始端点不显示箭头。不要靠 order 修复穿体向量。

## 图元

- `mesh`: `vertices` 三维点、`faces` 索引数组。每面须平面且凸，无重复索引，绕序给出向外右手法向；非平面/凹面先显式三角化。模型整体可由多个凸面组成，形体闭合/流形与外绕序仍须作者保证。默认 `cull:true`，开放薄面可 false。Newell 法向容许前三点共线，但整体退化会拒绝。
- `box`: `center` 默认0，`size3d:[长,宽,高]` 正值，局部 x/y/z 对齐。不要用 `size`（文字 pt）。
- `cylinder`: `center,axis`（默认局部 z）、正 `radius,length`、`segments` 整数6..256（默认24）。中心位于轴段中点。原生分面可编辑，不是精确圆柱 CAD。`light` 为世界系指向光源方向，默认[-.3,-.5,1]。
- 实体 `edge_mode:feature|all|none`；默认 feature，仅保留开边、轮廓和折角大于等于 `crease_deg`（默认25°）的边，去掉共面三角对角线和圆柱侧面冗余线。面填充无描边，边统一去重。`edge_order` 可覆盖边阶段。
- 只有带 fill 且 alpha=0 的面作为遮挡面；`occluder:false` 禁用其遮挡。透明面不参与二值遮挡，应采用明确的剖切/透明表达并人工核对。
- `polyline/arrow`: `points`，可 `closed,endArrow,startArrow`。arrow 默认尾端有箭头。
- `vector`: `anchor` 是 pose 中作用点；`components` 是 `vector_pose`（默认同 pose）中的向量分量，`length_scale` 正值默认1。世界方向为 R_vector*components（无平移），终点=世界作用点+length_scale*世界方向。不自动单位化，因此可保留统一力尺度；零向量拒绝。相对分量图必须注明比例关系。
- `frame`: `origin`（在 pose 中，默认0）、正 `lengths`、3个 `labels/colors`。默认 x/y/z 红/绿/蓝。轴严格沿 pose 的基向量。`label_width` 默认 .85 英寸、`size` 默认20pt，自动把标签向轴端外偏；可用3个二维 `label_offsets` 精调。自动偏移不保证无碰撞。原点被遮挡会省略圆点并提示。
- `label`: `anchor,text,offset,w,h,size,notation`，文字为独立原生文字。可设布尔值 `italic`，`frame` 的轴端标签也支持该字段。可 `leader:true` 自动连到最近文字框边点，另设 `leader_layer/leader_color`。引线表示对应关系，默认无箭头。
- `arc`: `center,normal,start_direction,radius,sweep_deg`；normal 和 start_direction 均在 pose 中。起向量先去掉法向分量，正扫角按 normal 右手定则；允许负扫角，范围非零且绝对值≤360°。`step_deg` 默认4°，原生折线采样（不是图像、不是精确圆锥曲线）；保持连续可见部分为一形状。默认 endArrow=true。
- `overlays` 是二维原生形状数组，用于短注释、视图标识和图例，不独立伪造三维向量。ID 必须不与投影生成的 ID 冲突。

## 诊断与限制

输出二维场景含 `projectionDiagnostics`。`foreshortened-or-overlapping-axes`：最短/最长投影轴<.3或轴线最小无向夹角<25°；这些阈值为提醒。`occluded-frame-origin`、`frame-crosses-near-plane`、`label-behind-near-plane` 应处理。`overlay-frame` 要核对其说明。

`--suggest-camera` 输出5个候选相机及三轴评分，不写图形；只评分 main 视图所有 frame 的可辨性，不评分实物结构、标签和布局，不自动采用。

隐线计算为线段与三角遮挡面的投影区间及深度比较，透视使用逆深度线性插值；不是只按线中点判断。复杂度约为线段数×遮挡三角形数，适合论文示意图。大量网格应简化实体或只保留关键结构。

**面填充仍为 painter 排序**。`face-order-review` 是投影包围框与深度区间重叠的保守提示，可能误报；不保证找出全部面相交/循环遮挡。相交/循环面须沿交线拆分，或使用可信几何处理后再投影。透明、阴影、材质、精确曲面及 CAD 实体运算未实现。

二代 JSON 字段可继续使用，几何投影兼容；边去重/隐线/标签默认值已改，**不承诺逐像素或逐形状数量兼容**。需要原样复现二代时继续调用保留的二代技能。

# 前端实时日志增强 + 历史记录 + 配色设计

- 日期：2026-06-01
- 背景：当前前端进度区只有每步两条摘要、日志过后即逝、刷新后历史丢失、视觉偏素。本设计补三件事：阶段内细粒度滚动日志、历史 run 加载、加克制配色。
- 最高原则延续：普适、不过拟合；保持 Apple 风极简底子。

---

## 1. 现状（已探明）

- `pipeline.run_pipeline` 有 `log_callback`，但每步只发 `start`（空 message）+ `done`（一句摘要）两条。
- 日志只实时推 SSE，**不落盘**；`runs/<id>/` 只存 9 步 `*.json` 中间产物 + `input/`。
- `tree` 只在内存 `TREE_STORE`，**刷新即丢**；`finalize.json` 已落盘但 API 没从它读。
- API 端点：upload / run / progress(SSE) / tree(内存) / export / steps。**无"列 runs""取日志"端点**。
- 前端单栏，进度时间线每阶段只显示 done 摘要；配色全中性灰。

---

## 2. 需求与确认的取舍

| # | 需求 | 确认 |
|---|---|---|
| A | 阶段内细粒度滚动日志 | **阶段内子进度**（每次 LLM/CU 调用 + 循环/轮询都埋点）|
| B | 日志落盘以便历史还原 | 完整存 `runs/<id>/logs.jsonl` |
| C | 历史记录加载 | **左侧边栏历史列表**（点击切换加载该 run）|
| D | 配色 | **一个品牌色 + 功能色**，保持 Apple 极简底子 |
| E | 当前阶段自动展开日志窗、完成自动收起、可手动再展开 | 是 |

---

## 3. 后端设计

### 3.1 pipeline 细粒度日志（`outline_extraction/pipeline.py`）
事件结构升级为 `{"phase", "status", "message", "level"}`：
- `status`: `start` | `progress` | `done`
- `level`: `"main"`（阶段开始/结束摘要）| `"detail"`（子进度/单次调用），前端据此分样式
- 在每个 LLM/CU 调用点与循环/轮询内埋 `progress` 日志，示例（措辞体现"服务/模型/任务"）：
  - parse：每个文件一条——`"解析《{file}》"`；非 docx 走 CU 时 `"调用 Content Understanding 解析《{file}》"`
  - classify：`"调用 {model_mini} 分类《{file}》（{i}/{n}）"`
  - segment：`"切分《{file}》→ {k} 个章节块"`
  - locate：`"调用 {model_main} 定位关键章节（{n} 个章节块）"`
  - extract_skeleton：`"调用 {model_main} 抽取骨架（bid_format 章节 {i}/{n}）"`
  - extract_requirements：`"调用 {model_main} 抽取要求（章节 {i}/{n}）"`
  - merge：`"调用 {model_main} 归并 {n} 条要求到骨架"`
  - supplement：`"调用 {model_main} 生成式补充（{n} 条游离要求）"`
  - finalize：`"整理大纲 id / 统计覆盖率"`
- 实现方式：优先在 pipeline 层（调用前后）发日志，避免大改各 step 模块；CU 轮询的"第 N 次"日志因在 cu_client 内部，作为可选增强（轮询回调），若改动过大则降级为"调用 CU 解析…"单条。**埋点不依赖具体文件内容，普适。**

### 3.2 日志 + 元信息落盘（`outline_extraction/api/main.py` 的 run worker）
- worker 的 `_log_cb` 除入队 SSE 外，把每条事件 append 到 `runs/<id>/logs.jsonl`（一行一 JSON）。
- 管线结束后写 `runs/<id>/meta.json`：`{run_id, project_name, filenames, created_at, coverage}`（created_at 由 worker 生成；coverage 取自 tree）。
- `run_pipeline` 内不写这些（保持纯净/可测）；由 API worker 负责落盘 logs.jsonl 与 meta.json。`run_pipeline` 已 dump 的 `*.json` 保留。

### 3.3 新增/改造 API 端点
- **新增 `GET /api/runs`**：扫描 `RUNS_DIR/*/meta.json`，返回历史列表（按 created_at 倒序）：`[{run_id, project_name, filenames, created_at, coverage}]`。无 meta.json 的旧 run 跳过。
- **新增 `GET /api/runs/{id}/logs`**：读 `runs/<id>/logs.jsonl`，返回事件数组。
- **改造 `GET /api/tree/{id}`**：先查内存 `TREE_STORE`，没有则从 `runs/<id>/finalize.json` 读并返回——使刷新后历史大纲可加载。

---

## 4. 前端设计（`web/index.html` + `web/app.js`）

### 4.1 布局：左侧历史边栏 + 右侧主区
- 两栏 flex。左侧窄边栏（约 260px）：顶部"+ 新建提取"按钮，下方历史 run 列表（项目名 + 时间 + 覆盖率小标）。刷新时 `GET /api/runs` 填充。
- 右侧主区：保留现有上传/流程时间线/覆盖率/大纲。
- 点左侧某条 → 进入"回看模式"：`GET /api/runs/{id}/logs` 还原各阶段日志（全 done 态、可展开）、`GET /api/tree/{id}` 显示大纲与覆盖率，隐藏上传按钮。
- 点"+ 新建" → 回到上传态。
- 窄屏：边栏可折叠为顶部抽屉/汉堡（响应式）。

### 4.2 阶段可展开滚动日志窗
- 时间线每阶段下方挂一个日志窗（`max-height` + `overflow-y:auto`，等宽字、浅色块）。
- 状态联动：阶段 `running` → 自动展开，新日志 append 并自动滚到底；阶段 `done` → 自动收起为一行摘要 + 展开箭头；点箭头可重新展开看该阶段全部 detail 日志。
- 数据：前端按 phase 把 detail 日志归到对应阶段的 `logs[]`（实时来自 SSE，回看来自 `/logs` 接口）。
- 日志行格式化：`detail` 行用次要灰、`main` 摘要行常规色；带轻微序号/前缀便于阅读。

### 4.3 配色（一个品牌色 + 功能色，保留 Apple 极简）
- 品牌主色 **靛蓝（indigo）**：主按钮、当前运行阶段高亮、选中的历史项、进行中转圈。
- 功能色：覆盖率达标 **绿**、有缺口 **琥珀**；来源徽章低饱和分类色——骨架=蓝、评分=绿、技术=紫、商务=橙、AI建议=灰。
- 底子仍 Apple 风：白/近白底、大圆角、细边框、充足留白、系统字体。彩色只点缀关键元素，不大面积铺色。

---

## 5. 非目标
- 不做 run 删除/重命名/搜索（YAGNI）。
- 不做日志分页。
- 不引入重型前端框架，仍 Alpine + Tailwind CDN。
- 不改管线理解逻辑（本设计纯展示/可观测层 + 落盘）。

---

## 6. 验证
- 单测：API 新端点（/api/runs 列表、/logs 读取、tree 从 finalize.json 兜底）用 TestClient + tmp runs 验证；pipeline 细日志用 fake log_callback 断言关键 progress 事件被发出。
- 真实渲染：Chrome DevTools 截图——运行中（某阶段展开滚动日志）、完成（阶段收起）、历史边栏列表、点击切换回看、配色（桌面+窄屏）。遵循全局 UI 规范。
- 现有测试不回归。

---

## 7. 受影响文件
- `outline_extraction/pipeline.py`（细粒度 log_callback 埋点 + 事件加 level 字段）
- `outline_extraction/parsing/cu_client.py`（可选：轮询进度回调）
- `outline_extraction/api/main.py`（logs.jsonl+meta.json 落盘；/api/runs、/api/runs/{id}/logs 新端点；tree 从 finalize.json 兜底）
- `web/index.html`（两栏布局 + 历史边栏 + 阶段日志窗 + 配色）
- `web/app.js`（历史加载、回看模式、按阶段归集日志、展开/收起逻辑）
- `tests/test_api.py`（新端点测试）

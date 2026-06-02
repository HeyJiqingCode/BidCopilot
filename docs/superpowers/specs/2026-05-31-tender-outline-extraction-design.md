# 招标文件 → 投标文件大纲提取（Demo）设计文档

- 日期：2026-05-31
- 客户：Sungrow（阳光电源）
- 目标：给客户演示「AI 读懂招标文件，自动生成结构完整、不漏项、可溯源的投标文件大纲」
- 范围：仅做到**大纲生成（到每一层级标题）**，不做内容生成

---

## 1. 背景与核心认知

### 1.1 需求
根据一份或一包招标文件，自动产出一份**投标文件大纲**——精确到每一层级的标题。招标文件可能是：
- 单个文件（如一个 docx）
- 一个文件包（含技术规范、商务文件、投标格式、招标正文、补遗答疑等多个文件）

### 1.2 关键认知（决定方案不"粗暴"的根本）
投标大纲不是让 LLM 凭空创作，而是把招标文件里**已经写明的要求**重组成完整、不漏项、可应答的结构。大纲有三个来源，需要**合并**：

1. **显式骨架（权威但不足）**——来自招标文件的「投标文件组成/投标文件格式」章节，给出一/二级骨架，但通常较粗。
2. **抽取式补充（优先、可靠）**——来自「评分办法/评标标准」「技术规范书」「商务条款」，把逐条要求*抽取*出来，翻译成投标文件里对应的章节。例：评分表"提供 ISO9001 得 2 分" → 大纲应有"质量管理体系认证证书"节。
3. **生成式兜底（少量、诚实标注）**——招标文件没明说、但评审逻辑/行业惯例上应有的章节（如"项目实施组织方案"），由 LLM 生成，且明确标注为 AI 建议。

> 核心原则：**能抽取就不生成，生成只兜底，且永远诚实标注来源。** 漏项 = 废标，因此覆盖率必须可度量、缺口必须暴露。

### 1.3 OCR / Content Understanding 的定位
本批文件多为 `.docx/.doc/.xml`（原生文本层），**不需要 OCR**。Content Understanding（CU）的价值在**版面理解与表格还原**（评分表、技术偏离表的结构必须保住），仅扫描件 PDF 才用其 OCR 能力。

---

## 2. 范围与约束

### 2.1 形态
- 给客户 **Demo**（非生产）：**Python 后端（FastAPI）+ 轻量 Web 界面**。
- 目标：追求**普适性**——换一份没见过的招标文件也能跑，不靠"背答案"。

### 2.2 普适性保证（防"看着答案跑结论"）
- 理解层/对齐层的所有 prompt **不含任何特定标的的硬编码**（不写死章节号、文件名、关键词清单），只描述"如何识别某类信息的通用方法"。这是普适性的根本工程保证。
- **盲测机制（已落实）**：
  - **开发可见标的（3 个）**：华能（单 docx）、北京院青海察尔汗（文件包）、白银景泰（单 doc）。仅用这 3 个调试管线与 prompt。
  - **盲测标的（2 个，开发期不可见）**：赞比亚夏翁加项目、淮能电力凤台丁集矿储能项目。其文件夹已从 `TenderingDocs/` 删除，开发全程不打开其内容；Demo 时由用户提供，**首次运行**即为真实压力测试。
  - 任何 prompt / 代码若出现只为通过某可见标的而写的特判，即视为违反普适性原则。

### 2.3 输出形态
- **A. 可视化大纲树**：界面可展开，每节点带来源徽章 + 覆盖率面板。
- **B. Word 导出**：同一棵树 JSON 的另一个渲染器，几十行遍历即可。
- A 先做，B 顺带。

### 2.4 已知输入形态（TenderingDocs/ 实测）
- 单 docx 标的（华能）
- 文件包标的（山东高速：投标格式 + 招标正文 PDF + 补遗 + 多份 doc/docx）
- `.ebid` 专有格式（实测为 ZIP，内含 `TenderData.xml`）
- 扫描件可能性的 PDF（须探测，不预设）

### 2.5 技术约束
- LLM：Azure OpenAI **Responses API**（非 chat completions）。
  - `client.responses.create(model=..., input=..., instructions=..., reasoning={"effort":...}, text={"verbosity":...})`
  - base_url 形如 `https://<resource>.services.ai.azure.com/openai/v1/`，key 从 `.env` 的 `FOUNDRY_API_KEY_AOAI` 读。
  - 模型：`gpt-5.4`（全局推理：定位/抽取/对齐/兜底）、`gpt-5.4-mini`（量大简单：分类/切分兜底）。
- Content Understanding：已部署，第二阶段增量接入（先把 4 个电子文档标的用纯文本链路跑通）。
- 平台：macOS（`textutil` 可用，`pandoc` 不可用）。

---

## 3. 架构总览

分层架构，每层职责单一、接口清晰、可独立测试：

```
招标文件包
   │
┌──▼──────────────┐  parsing/        纯工程 + Content Understanding
│ 1. 解析层        │  解压 → 探测优先抽文本 → 表格/版面还原 → 统一 Markdown
└──┬──────────────┘
┌──▼──────────────┐  understanding/  LLM(mini/5.4)
│ 2. 理解层        │  ②分类 ③切分 ④定位关键章节 ⑤抽显式骨架 ⑥抽要求条目
└──┬──────────────┘
┌──▼──────────────┐  alignment/      LLM(5.4)
│ 3. 对齐层        │  ⑦归并去重挂树(+覆盖率) ⑧生成式兜底 → 大纲树 JSON
└──┬──────────────┘
┌──▼──────────────┐  output/         纯工程
│ 4. 输出层        │  树 JSON → API 响应 / Word 导出
└──┬──────────────┘
┌──▼──────────────┐  api/ + web/     FastAPI + 前端
│ 5. 接口/界面层   │  上传、SSE 进度、树视图、覆盖率面板、导出
└─────────────────┘
```

### 3.1 工程 vs LLM 分工
| 阶段 | 干什么 | 谁来做 |
|---|---|---|
| 解析/取文本 | 解压、抽文本、探测扫描件、表格还原 | 纯工程 + CU |
| 文件分类 | 判定每个文件类型 | LLM(mini) |
| 章节切分 | 切成带层级章节块 | 工程为主，LLM 兜底 |
| 定位关键章节 | 找投标组成/评分/技术/商务 | LLM(5.4) |
| 抽显式骨架 | 投标组成章节 → 大纲树 | LLM(5.4) |
| 抽要求条目 | 评分/技术逐条 → 要求项 | LLM(5.4) + CU 表格 |
| 对齐归并 | 挂树、去重、覆盖率 | LLM(5.4) + 工程统计 |
| 生成式兜底 | 补缺失节，标 AI 建议 | LLM(5.4) |
| 输出 | 树→API/Word | 纯工程 |

> 原则：**凡是会因文件不同而变化的判断，全部交给 LLM；工程只做不依赖内容的机械活。**

### 3.2 目录结构
```
outline_extraction/
├── parsing/        # unpack.py, extract.py, cu_client.py
├── understanding/  # classify.py, segment.py, locate.py, extract_skeleton.py, extract_requirements.py
├── alignment/      # merge.py, supplement.py
├── output/         # tree.py(数据模型), word_export.py
├── llm/            # client.py(Responses API), prompts/*.txt
├── api/            # main.py, routes.py
├── web/            # index.html, app.js
├── pipeline.py     # 编排 9 步主管线
└── tests/
```

---

## 4. 数据模型（系统核心契约）

所有环节围绕这一个结构流转。用 Pydantic v2 定义（便于校验 + LLM 结构化输出）。

```python
class SourceType(str, Enum):
    SKELETON     = "skeleton"      # 📋 投标文件组成/格式（显式骨架）
    SCORING      = "scoring"       # 📊 评分办法
    TECH_SPEC    = "tech_spec"     # 📐 技术规范书
    BIZ_TERMS    = "biz_terms"     # 📄 商务条款
    AI_SUGGESTED = "ai_suggested"  # 🤖 AI 生成式兜底

class SourceRef(BaseModel):
    type: SourceType
    document: str          # 来源文件名
    location: str          # 章节定位，如"七、技术建议书"/"评分办法第3条"
    quote: str | None      # 原文摘录（可选，悬停可看）

class OutlineNode(BaseModel):
    id: str                        # 路径式稳定 id，如 "3.2.1"
    title: str
    level: int                     # 1/2/3...，映射 Word Heading
    sources: list[SourceRef]       # 多来源：同一标题可同时是骨架要求+评分点
    children: list["OutlineNode"]
    note: str | None               # 应答提示，可选

class CoverageReport(BaseModel):
    total_scoring_items: int
    mapped_scoring_items: int
    total_tech_items: int
    mapped_tech_items: int
    unmapped: list[str]            # 未能挂载的要求（红色告警，提示人工复核）

class OutlineTree(BaseModel):
    project_name: str
    source_documents: list[str]
    nodes: list[OutlineNode]
    coverage: CoverageReport
```

**两个关键设计：**
1. **`sources` 为复数**——多来源是"此标题重要、勿漏"的信号，界面可叠加多个徽章。
2. **`CoverageReport`**——Demo 可信度锚点。对齐后纯工程统计（不靠 LLM 自我美化），诚实暴露缺口。

---

## 5. 解析层（parsing/）

原则：**探测优先（probe-first）**，绝不靠文件名/后缀预设。

### 5.1 解压（unpack.py）
- 目录 → 递归遍历；`.zip`/`.ebid` → 解压（`.ebid` 实测为 ZIP，内含 `TenderData.xml`，能抽到结构是额外收获，抽不到则忽略，不依赖）。
- 产出：扁平文件清单 `[(路径, 后缀)]`。

### 5.2 文本抽取（extract.py）— 决策链（失败才降级）
```
.docx → python-docx 直读（保留标题样式/层级）
.doc  → textutil 转换
.pdf  → ① pdfplumber/PyMuPDF 抽文本层
        ② 每页平均字符数 < 阈值 → 判为扫描件 → 走 CU OCR
.xml  → 直接解析
其它   → 跳过 + 日志（不静默吞）
```
扫描件判定用"每页平均字符数"这类**与具体文件无关**的通用指标。

### 5.3 表格/版面还原（cu_client.py）— CU 主战场
- 扫描件 PDF：CU 做 OCR + 版面分析 → 带结构 Markdown。
- 含复杂表格文档：CU 还原表格为 Markdown 表格，保住"评分项—分值—要求"对应关系。
- CU 输出统一转 Markdown（`#` 标题、`|` 表格），结构化且对 LLM 友好。

### 5.4 统一输出
```python
class ParsedDocument(BaseModel):
    filename: str
    raw_markdown: str        # 统一 Markdown 全文
    extract_method: str      # docx/textutil/pdf_text/cu_ocr —— 可追溯
    page_count: int | None
```

### 5.5 实施顺序（CU 接入节奏）
分两阶段，理由是先用最快路径拿到端到端可见效果，再把 CU 作为质量增强单独验证、降低耦合风险：
1. **阶段一（先做）**：纯文本抽取全链路（docx/textutil/pdf-text + 简单表格转 Markdown），把电子文档标的端到端跑通，界面和导出先成型。
2. **阶段二（增量）**：接入 Content Understanding，用于 (a) 扫描件 PDF 的 OCR + 版面，(b) 评分表/技术偏离表等复杂表格的高保真还原。CU 作为可插拔的增强模块，`extract.py` 通过决策链按需调用，不影响阶段一已跑通的链路。

---

## 6. 理解层（understanding/）

所有 prompt 只描述"通用识别方法"，零特定标的硬编码。

### 6.1 文件分类（classify.py · mini）
- 输入：每个文档的 文件名 + 正文前 ~1500 字。
- 输出：`tender_main / tech_spec / business / bid_format / addendum / unknown`，带 `confidence`。
- 靠读内容判断，不靠文件名；低置信度界面标注待核对。

### 6.2 章节切分（segment.py · 工程为主，mini 兜底）
- 工程优先：正则识别"第X章/一、/（一）/1.1/数字编号"等多种中文编号风格 → 带 `level` 章节块。
- 兜底：编号混乱/无编号时 mini 判断边界。
- 输出：`list[Section{title, level, content, doc_source}]`。

### 6.3 定位关键章节（locate.py · 5.4）
- 输入：所有 Section 标题 + 简短摘要。
- 输出：指认四类关键章节位置（投标组成/评分办法/技术规范/商务条款）。
- 靠语义定位，处理各家叫法不同（"投标文件格式" vs "投标文件编制要求" vs "投标须知前附表"）。

### 6.4 抽显式骨架（extract_skeleton.py · 5.4，结构化输出）
- 输入：定位到的"投标文件组成"章节全文。
- 输出：`OutlineNode` 树，节点 `source.type = SKELETON`。
- 用 Responses API 结构化输出直接产出符合 schema 的 JSON。

### 6.5 抽要求条目（extract_requirements.py · 5.4 + CU 表格）
- 输入：评分办法章节 + 技术规范章节（表格已还原为 Markdown 表格）。
- 输出：`list[RequirementItem{要求描述, 来源类型, 原文定位, 建议对应的投标章节标题}]`。
  - 评分表每条 → SCORING；技术规范每条 → TECH_SPEC。
- **职责分离**：只抽取要求 + 给出"建议标题"，**挂到哪、是否合并留给对齐层**。

> 每步吃明确输入结构、吐明确输出结构，可拿任一标的中间产物单独喂入验证。

---

## 7. 对齐层（alignment/）

把"显式骨架树 + 零散要求条目"合并成最终大纲树。gpt-5.4 全局推理最吃重的一步。

### 7.1 归并挂载（merge.py · 5.4，结构化输出）
以**显式骨架树为主干**，每个 `RequirementItem` 三选一归宿：
1. 已存在等价节点 → **合并**：把该要求的 `SourceRef` 追加到现有节点 `sources[]`（多来源由此产生）。
2. 应作为子节点 → 新建 child 挂上（如技术参数逐条 → 挂"技术响应"下）。
3. 骨架无对应位置 → 暂存为"游离要求"，进入 7.3。

合并靠**语义判同**（"质量管理体系认证" ≈ "ISO9001 认证证书"），每个判定记录可追溯。

### 7.2 覆盖率自检（merge.py 内，纯工程统计）
合并后**纯工程**统计（不靠 LLM，避免自我美化）：
- `total_* vs mapped_*`
- `unmapped[]` = 判为游离且 7.3 未安置的要求。
- 进 `CoverageReport`，界面红色高亮 unmapped。**Demo 可信度锚点。**

### 7.3 生成式兜底（supplement.py · 5.4）
- 游离要求 → 生成合理新章节标题并挂载（来源仍标原始 SCORING/TECH_SPEC，仅位置由 AI 推断）。
- 行业惯例缺失项 → 生成节点，`source.type = AI_SUGGESTED`。
- **严格约束**：纯 AI_SUGGESTED 节点必须可视觉区分（界面 🤖、Word 可选保留/去除），绝不伪装成招标要求。

### 7.4 排序与 id 重整（tree.py · 工程）
按骨架原始顺序 + 层级规则排序，重生成路径式稳定 id（`3.2.1`），符合标书阅读习惯。

> 对齐哲学：**骨架为主干，要求做填充，生成只兜底，覆盖率纯工程统计。**

---

## 8. LLM 封装、编排、接口/界面层

### 8.1 LLM 封装（llm/client.py）
```python
class LLMClient:
    def __init__(self):  # .env: FOUNDRY_API_KEY_AOAI + base_url
        self.client = OpenAI(api_key=..., base_url=".../openai/v1/")

    def complete(self, *, model, instructions, input_content,
                 effort="medium", verbosity="low",
                 schema: type[BaseModel] | None = None):
        # schema 不为空 → 结构化输出，返回校验过的 Pydantic 对象
        # 记录 usage（token）→ 展示成本 & 调试
```
- 模型路由：调用方传 `gpt-5.4` 或 `gpt-5.4-mini`。
- `prompts/` 目录：每步 instructions 存独立 `.txt`，与代码分离便于迭代。
- 重试：简单指数退避。

### 8.2 编排管线（pipeline.py）
```python
def run_pipeline(input_path, progress_callback) -> OutlineTree:
    docs = parse(input_path)
    classified = classify(docs)
    sections = segment(classified)
    located = locate(sections)
    skeleton = extract_skeleton(located)
    requirements = extract_requirements(located)
    tree = merge(skeleton, requirements)   # 含覆盖率
    tree = supplement(tree)
    return finalize(tree)                   # 排序+id
```
每步中间产物 dump 成 JSON 存 `runs/<时间戳>/` —— 调试 + 给客户讲原理的素材。

### 8.3 接口层（api/ · FastAPI）
```
POST /api/upload                  上传 → run_id
POST /api/run/{run_id}            启动管线
GET  /api/progress/{run_id}       SSE 推送每步进度
GET  /api/tree/{run_id}           最终 OutlineTree JSON
GET  /api/export/{run_id}.docx    Word 导出（B）
GET  /api/runs/{run_id}/steps/{step}  某步中间产物（讲原理）
```

### 8.4 界面层（web/ · 单页应用，注重视觉效果）
**技术选型**：Alpine.js + Tailwind CSS（均走 CDN，**无构建步骤**）。这是"好看"与"轻量"的平衡点——能做出现代、克制、有质感的界面，又不引入 npm/打包链路，Demo 启动即用。配色走干净的中性灰 + 单一品牌强调色，避免花哨。

界面区块：
- **上传区**：拖拽文件包，带文件类型/数量预览。
- **进度区**：9 步流水线竖向时间线，SSE 实时点亮（pending→running→done 状态动效），每步可点开抽屉看中间产物 JSON。
- **大纲树视图（A）**：可展开/折叠树；节点带**来源徽章**（📋骨架 📊评分 📐技术 📄商务 🤖AI建议），多来源叠加显示；悬停 tooltip 看原文摘录；AI 建议节点用淡色背景区分。
- **覆盖率面板**：醒目卡片，绿"28/28 已覆盖" / 红 未覆盖告警并列出缺口条目。
- **导出区**：一键下 Word（B），带"是否保留 AI 建议标注"开关。

> UI 完成后用 Playwright/Chrome DevTools 截图验证实际渲染（含多视口），不靠代码推断——遵循全局 UI 规范。

### 8.5 技术栈
- 后端：Python 3.11+ / FastAPI / Pydantic v2 / openai SDK
- 解析：python-docx, pdfplumber/PyMuPDF, textutil(子进程), Azure Content Understanding
- 导出：python-docx
- 前端：Alpine.js + Tailwind CSS（CDN，无构建）
- 配置：.env（API key、base_url、CU endpoint）

---

## 9. 诉求落地对照

| 诉求 | 落地点 |
|---|---|
| 不靠 OCR 粗暴丢 LLM | 探测优先解析 + 显式骨架抽取为主 |
| 两类来源合并 | 骨架(显式)+要求(抽取)+兜底(生成)，对齐层归并 |
| 换新文件不翻车 | prompt 零硬编码 + 盲测第 5 个标的 |
| 漏项=废标 | 覆盖率报告（纯工程统计，诚实暴露缺口） |
| A 树视图 + B Word | 同一棵树 JSON 的两个渲染器 |
| 给客户讲原理 | 每步中间产物可 dump/查看 |

---

## 10. 非目标（YAGNI）

- 不做内容生成（仅到标题层级）。
- 不做 Map-Reduce / Agent 自主编排（方案二/三，留待生产化演进）。
- 不做用户账户、持久化数据库（Demo 用文件系统 `runs/` 即可）。
- 不做多语言界面、权限控制。

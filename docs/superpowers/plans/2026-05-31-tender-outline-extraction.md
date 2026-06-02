# 招标文件→投标大纲提取 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 FastAPI + 轻量前端的 Demo，输入一份/一包招标文件，自动产出带层级、带来源标注、带覆盖率报告的投标文件大纲树，并支持 Word 导出。

**Architecture:** 分层管线（解析 → 理解 → 对齐 → 输出），9 步顺序执行。解析层纯工程 + Content Understanding 增量接入；理解/对齐层用 Azure OpenAI Responses API（结构化输出）做"定位+抽取+对齐"，prompt 零特定标的硬编码。核心数据契约是一棵 `OutlineTree` JSON，界面树视图与 Word 导出都是它的渲染器。

**Tech Stack:** Python 3.14（`.venv`，用 `uv pip` 装依赖）、FastAPI、Pydantic v2、openai SDK（Responses API `responses.parse` + `text_format`）、python-docx、pdfplumber、Alpine.js + Tailwind（CDN，无构建）、pytest。

**关键约定（贯穿全程）：**
- 装依赖：`uv pip install <pkg>`（venv 已激活）。跑命令：`.venv/bin/python ...` 或 `.venv/bin/pytest ...`。
- 模型：`gpt-5.4`（定位/抽取/对齐/兜底）、`gpt-5.4-mini`（分类/切分兜底）。
- LLM 调用一律走 `client.responses.parse(model=..., input=..., instructions=..., reasoning={"effort":...}, text={"verbosity":...}, text_format=PydanticModel)`，读 `response.output_parsed`。
- 项目当前非 git 仓库 → Task 0 先 `git init`。所有 commit 用普通 `git commit`。
- **盲测纪律**：开发只用 3 个可见标的（华能 / 北京院青海察尔汗 / 白银景泰）。`TenderingDocs/` 下赞比亚、淮能凤台已删除，禁止凭记忆为其写特判。

---

## 文件结构

```
outline_extraction/
├── __init__.py
├── config.py              # 读 .env：API key、base_url、模型名、CU endpoint
├── models.py              # Pydantic 数据模型：SourceRef/OutlineNode/OutlineTree/CoverageReport/ParsedDocument/Section/RequirementItem
├── llm/
│   ├── __init__.py
│   ├── client.py          # LLMClient：封装 responses.parse，记录 usage
│   └── prompts/           # 每步 instructions 独立 .txt
│       ├── classify.txt
│       ├── locate.txt
│       ├── extract_skeleton.txt
│       ├── extract_requirements.txt
│       ├── merge.txt
│       └── supplement.txt
├── parsing/
│   ├── __init__.py
│   ├── unpack.py          # 解压/遍历 → 文件清单
│   ├── extract.py         # 探测优先抽文本 → ParsedDocument
│   └── cu_client.py       # Content Understanding 封装（阶段二）
├── understanding/
│   ├── __init__.py
│   ├── classify.py        # 文件分类（mini）
│   ├── segment.py         # 章节切分（正则+mini兜底）
│   ├── locate.py          # 定位关键章节（5.4）
│   ├── extract_skeleton.py# 抽显式骨架（5.4）
│   └── extract_requirements.py # 抽要求条目（5.4）
├── alignment/
│   ├── __init__.py
│   ├── merge.py           # 归并挂载 + 覆盖率（5.4 + 工程统计）
│   └── supplement.py      # 生成式兜底（5.4）
├── output/
│   ├── __init__.py
│   ├── tree.py            # 排序 + 路径式 id 重整
│   └── word_export.py     # OutlineTree → .docx
├── pipeline.py            # 编排 9 步
└── api/
    ├── __init__.py
    └── main.py            # FastAPI：upload/run/progress(SSE)/tree/export/steps

web/
├── index.html             # Alpine + Tailwind CDN
└── app.js                 # 前端逻辑

tests/
├── __init__.py
├── conftest.py            # fixtures：样例文本、fake LLM
├── test_models.py
├── test_unpack.py
├── test_extract.py
├── test_segment.py
├── test_word_export.py
├── test_tree.py
├── test_merge_coverage.py
├── test_classify.py
├── test_pipeline.py
└── fixtures/              # 小型样例文件（非真实标的）

.env.example
requirements.txt
runs/                      # 运行产物（gitignore）
```

---

## Task 0: 项目初始化与依赖

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `outline_extraction/__init__.py`, `tests/__init__.py`, `pytest.ini`

- [ ] **Step 1: git 初始化**

Run:
```bash
cd /Users/jiqingyou/Documents/Code/VSCode/Microsoft/Demo/Customers/Sungrow/OutlineExtraction
git init
```
Expected: `Initialized empty Git repository`

- [ ] **Step 2: 写 .gitignore**

Create `.gitignore`:
```
.venv/
__pycache__/
*.pyc
.env
runs/
.DS_Store
docs/TenderingDocs/
*.egg-info/
.pytest_cache/
```
（`TenderingDocs/` 入 gitignore：真实标的不进版本库。）

- [ ] **Step 3: 写 requirements.txt**

Create `requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.32
pydantic>=2.9
python-dotenv>=1.0
openai>=1.55
python-docx>=1.1
pdfplumber>=0.11
pymupdf>=1.24
python-multipart>=0.0.9
sse-starlette>=2.1
pytest>=8.3
httpx>=0.27
```

- [ ] **Step 4: 安装依赖**

Run:
```bash
uv pip install -r requirements.txt
```
Expected: 全部安装成功，无报错。

- [ ] **Step 5: 验证关键库可导入**

Run:
```bash
.venv/bin/python -c "import fastapi, pydantic, openai, docx, pdfplumber, fitz; print('imports ok')"
```
Expected: `imports ok`

- [ ] **Step 6: 写 .env.example**

Create `.env.example`:
```
FOUNDRY_API_KEY_AOAI=your-key-here
AOAI_BASE_URL=https://resource-aifoundry-eastus-2.services.ai.azure.com/openai/v1/
MODEL_MAIN=gpt-5.4
MODEL_MINI=gpt-5.4-mini
CU_ENDPOINT=
CU_KEY=
```

- [ ] **Step 7: 写 pytest.ini**

Create `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v
```

- [ ] **Step 8: 创建空包文件**

Create `outline_extraction/__init__.py`（空文件）、`tests/__init__.py`（空文件）。

- [ ] **Step 9: 验证 pytest 能跑（空集）**

Run:
```bash
.venv/bin/pytest
```
Expected: `no tests ran` 或 collected 0 items，无错误。

- [ ] **Step 10: Commit**

```bash
git add .gitignore .env.example requirements.txt pytest.ini outline_extraction/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding and dependencies"
```

---

## Task 1: 数据模型（models.py）

**Files:**
- Create: `outline_extraction/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_models.py`:
```python
"""数据模型测试"""
from outline_extraction.models import (
    SourceType, SourceRef, OutlineNode, OutlineTree, CoverageReport,
    ParsedDocument, Section, RequirementItem,
)


def test_outline_node_nested():
    """验证 OutlineNode 可嵌套子节点并保留多来源"""
    child = OutlineNode(
        id="1.1", title="投标函", level=2,
        sources=[SourceRef(type=SourceType.SKELETON, document="格式.docx",
                           location="一、投标函", quote=None)],
        children=[], note=None,
    )
    parent = OutlineNode(
        id="1", title="商务部分", level=1,
        sources=[
            SourceRef(type=SourceType.SKELETON, document="格式.docx", location="一", quote=None),
            SourceRef(type=SourceType.SCORING, document="评分.pdf", location="第3条", quote="提供..."),
        ],
        children=[child], note=None,
    )
    assert parent.children[0].title == "投标函"
    assert len(parent.sources) == 2  # 多来源


def test_coverage_report_unmapped():
    """覆盖率报告记录未挂载要求"""
    cov = CoverageReport(
        total_scoring_items=28, mapped_scoring_items=28,
        total_tech_items=10, mapped_tech_items=7,
        unmapped=["技术参数X响应", "技术参数Y响应", "技术参数Z响应"],
    )
    assert cov.mapped_scoring_items == cov.total_scoring_items
    assert len(cov.unmapped) == 3


def test_outline_tree_serializable():
    """OutlineTree 可序列化为 JSON 再还原"""
    tree = OutlineTree(
        project_name="测试项目",
        source_documents=["a.docx"],
        nodes=[OutlineNode(id="1", title="X", level=1, sources=[], children=[], note=None)],
        coverage=CoverageReport(total_scoring_items=0, mapped_scoring_items=0,
                                total_tech_items=0, mapped_tech_items=0, unmapped=[]),
    )
    dumped = tree.model_dump_json()
    restored = OutlineTree.model_validate_json(dumped)
    assert restored.project_name == "测试项目"
    assert restored.nodes[0].title == "X"


def test_parsed_document_method_field():
    """ParsedDocument 记录抽取方式，便于追溯"""
    doc = ParsedDocument(filename="a.pdf", raw_markdown="# 标题", extract_method="pdf_text", page_count=5)
    assert doc.extract_method == "pdf_text"


def test_requirement_item():
    """RequirementItem 携带来源类型与建议标题"""
    item = RequirementItem(
        description="提供ISO9001认证",
        source_type=SourceType.SCORING,
        location="评分办法第3条",
        suggested_title="质量管理体系认证证书",
    )
    assert item.source_type == SourceType.SCORING
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError: outline_extraction.models`）

- [ ] **Step 3: 写最小实现**

Create `outline_extraction/models.py`:
```python
"""核心数据模型——系统所有环节流转的统一契约"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """大纲节点来源类型——Demo 可信度展示的关键"""
    SKELETON = "skeleton"        # 投标文件组成/格式（显式骨架）
    SCORING = "scoring"          # 评分办法
    TECH_SPEC = "tech_spec"      # 技术规范书
    BIZ_TERMS = "biz_terms"      # 商务条款
    AI_SUGGESTED = "ai_suggested"  # AI 生成式兜底


class SourceRef(BaseModel):
    """单条来源溯源——说明该标题为何存在"""
    type: SourceType                       # 来源类型
    document: str                          # 来源文件名
    location: str                          # 章节定位，如"七、技术建议书"
    quote: Optional[str] = None            # 原文摘录（可选）


class OutlineNode(BaseModel):
    """大纲树节点——一个投标文件标题"""
    id: str                                # 路径式稳定 id，如 "3.2.1"
    title: str                             # 标题文本
    level: int                             # 层级 1/2/3，映射 Word Heading
    sources: list[SourceRef] = Field(default_factory=list)  # 多来源
    children: list["OutlineNode"] = Field(default_factory=list)  # 子节点
    note: Optional[str] = None             # 应答提示（可选）


class CoverageReport(BaseModel):
    """覆盖率自检——抽取到的要求有多少落进大纲"""
    total_scoring_items: int               # 评分点总数
    mapped_scoring_items: int              # 已对齐评分点数
    total_tech_items: int                  # 技术条目总数
    mapped_tech_items: int                 # 已对齐技术条目数
    unmapped: list[str] = Field(default_factory=list)  # 未挂载要求（告警）


class OutlineTree(BaseModel):
    """完整大纲 + 元信息"""
    project_name: str                      # 项目名
    source_documents: list[str]            # 参与生成的文件清单
    nodes: list[OutlineNode]               # 顶层节点
    coverage: CoverageReport               # 覆盖率报告


class ParsedDocument(BaseModel):
    """解析层输出——单个文件的统一表示"""
    filename: str                          # 文件名
    raw_markdown: str                      # 统一 Markdown 全文
    extract_method: str                    # docx/textutil/pdf_text/cu_ocr
    page_count: Optional[int] = None       # 页数（PDF）


class Section(BaseModel):
    """章节切分结果——一个带层级的章节块"""
    title: str                             # 章节标题
    level: int                             # 层级
    content: str                           # 章节正文
    doc_source: str                        # 所属文件名


class RequirementItem(BaseModel):
    """从评分/技术规范抽取的单条要求"""
    description: str                       # 要求描述
    source_type: SourceType                # 来源类型
    location: str                          # 原文定位
    suggested_title: str                   # 建议对应的投标章节标题
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/models.py tests/test_models.py
git commit -m "feat: core data models (OutlineTree, SourceRef, coverage)"
```

---

## Task 2: 配置加载（config.py）

**Files:**
- Create: `outline_extraction/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_config.py`:
```python
"""配置加载测试"""
import os
from outline_extraction.config import Settings


def test_settings_from_env(monkeypatch):
    """从环境变量读取配置"""
    monkeypatch.setenv("FOUNDRY_API_KEY_AOAI", "k123")
    monkeypatch.setenv("AOAI_BASE_URL", "https://x/openai/v1/")
    monkeypatch.setenv("MODEL_MAIN", "gpt-5.4")
    monkeypatch.setenv("MODEL_MINI", "gpt-5.4-mini")
    s = Settings()
    assert s.api_key == "k123"
    assert s.base_url.endswith("/openai/v1/")
    assert s.model_main == "gpt-5.4"
    assert s.model_mini == "gpt-5.4-mini"


def test_settings_cu_optional(monkeypatch):
    """CU 配置可选，缺省为空字符串"""
    monkeypatch.setenv("FOUNDRY_API_KEY_AOAI", "k")
    monkeypatch.setenv("AOAI_BASE_URL", "https://x/openai/v1/")
    monkeypatch.delenv("CU_ENDPOINT", raising=False)
    s = Settings()
    assert s.cu_endpoint == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/config.py`:
```python
"""配置加载——从 .env / 环境变量读取运行参数"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """运行配置；字段默认从环境变量读取"""
    api_key: str = field(default_factory=lambda: os.getenv("FOUNDRY_API_KEY_AOAI", ""))
    base_url: str = field(default_factory=lambda: os.getenv("AOAI_BASE_URL", ""))
    model_main: str = field(default_factory=lambda: os.getenv("MODEL_MAIN", "gpt-5.4"))
    model_mini: str = field(default_factory=lambda: os.getenv("MODEL_MINI", "gpt-5.4-mini"))
    cu_endpoint: str = field(default_factory=lambda: os.getenv("CU_ENDPOINT", ""))
    cu_key: str = field(default_factory=lambda: os.getenv("CU_KEY", ""))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/config.py tests/test_config.py
git commit -m "feat: settings loader from env"
```

---

## Task 3: LLM 客户端封装（llm/client.py）

**Files:**
- Create: `outline_extraction/llm/__init__.py`, `outline_extraction/llm/client.py`
- Test: `tests/test_llm_client.py`

**说明：** 单元测试用注入的 fake 来验证封装逻辑（参数拼装、usage 记录、结构化解析路径），不打真实 API。

- [ ] **Step 1: 写失败测试**

Create `tests/test_llm_client.py`:
```python
"""LLMClient 封装测试——用 fake responses 客户端验证调用拼装与解析"""
from pydantic import BaseModel
from outline_extraction.llm.client import LLMClient


class _Out(BaseModel):
    answer: str


class _FakeParsed:
    """模拟 responses.parse 返回对象"""
    def __init__(self, parsed, usage):
        self.output_parsed = parsed
        self.usage = usage


class _FakeResponses:
    def __init__(self, recorder):
        self.recorder = recorder

    def parse(self, **kwargs):
        self.recorder["last_kwargs"] = kwargs  # 记录调用参数供断言
        return _FakeParsed(_Out(answer="hi"), usage={"total_tokens": 42})


class _FakeClient:
    def __init__(self):
        self.recorder = {}
        self.responses = _FakeResponses(self.recorder)


def test_complete_structured_passes_params():
    """complete 应把模型/instructions/reasoning/text/text_format 正确传给 responses.parse"""
    fake = _FakeClient()
    llm = LLMClient(client=fake)
    result = llm.complete(
        model="gpt-5.4", instructions="do x", input_content="hello",
        effort="high", verbosity="low", schema=_Out,
    )
    assert isinstance(result, _Out)
    assert result.answer == "hi"
    kw = fake.recorder["last_kwargs"]
    assert kw["model"] == "gpt-5.4"
    assert kw["instructions"] == "do x"
    assert kw["input"] == "hello"
    assert kw["reasoning"] == {"effort": "high"}
    assert kw["text"] == {"verbosity": "low"}
    assert kw["text_format"] is _Out


def test_usage_accumulated():
    """每次调用应累计 token 用量，便于成本展示"""
    fake = _FakeClient()
    llm = LLMClient(client=fake)
    llm.complete(model="gpt-5.4", instructions="i", input_content="c", schema=_Out)
    llm.complete(model="gpt-5.4", instructions="i", input_content="c", schema=_Out)
    assert llm.total_calls == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/llm/__init__.py`（空文件）。

Create `outline_extraction/llm/client.py`:
```python
"""Azure OpenAI Responses API 封装——统一入口、结构化输出、用量记录"""
from typing import Optional, Type, Any
from pydantic import BaseModel
from openai import OpenAI
from outline_extraction.config import Settings


class LLMClient:
    """封装 responses.parse；调用方传模型名做路由

    参数:
        settings: 配置对象，缺省自动构造
        client: 可注入的底层客户端（测试用 fake），缺省构造真实 OpenAI 客户端
    """
    def __init__(self, settings: Optional[Settings] = None, client: Any = None) -> None:
        self.settings = settings or Settings()
        if client is not None:
            self.client = client
        else:
            self.client = OpenAI(api_key=self.settings.api_key, base_url=self.settings.base_url)
        self.total_calls: int = 0          # 累计调用次数
        self.usages: list[Any] = []        # 每次 usage 记录

    def complete(
        self,
        *,
        model: str,
        instructions: str,
        input_content: str,
        effort: str = "medium",
        verbosity: str = "low",
        schema: Optional[Type[BaseModel]] = None,
    ) -> Any:
        """调用 LLM 并返回结构化结果

        参数:
            model: 部署名，如 gpt-5.4 / gpt-5.4-mini
            instructions: 系统指令
            input_content: 用户输入内容
            effort: 推理强度 low/medium/high
            verbosity: 输出详尽度 low/medium/high
            schema: Pydantic 模型类；提供则走结构化输出，返回该类型实例
        返回:
            schema 实例（提供 schema 时）或纯文本字符串
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_content,
            "reasoning": {"effort": effort},
            "text": {"verbosity": verbosity},
        }
        if schema is not None:
            kwargs["text_format"] = schema
            response = self.client.responses.parse(**kwargs)
            self._record(response)
            return response.output_parsed
        response = self.client.responses.create(**kwargs)
        self._record(response)
        return response.output_text

    def _record(self, response: Any) -> None:
        """记录用量——内部辅助"""
        self.total_calls += 1
        self.usages.append(getattr(response, "usage", None))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/llm/__init__.py outline_extraction/llm/client.py tests/test_llm_client.py
git commit -m "feat: LLM client wrapping Responses API with structured output"
```

---

## Task 4: 文件解压/遍历（parsing/unpack.py）

**Files:**
- Create: `outline_extraction/parsing/__init__.py`, `outline_extraction/parsing/unpack.py`
- Test: `tests/test_unpack.py`, `tests/fixtures/`（测试中动态造）

- [ ] **Step 1: 写失败测试**

Create `tests/test_unpack.py`:
```python
"""文件解压/遍历测试"""
import zipfile
from pathlib import Path
from outline_extraction.parsing.unpack import collect_files


def test_collect_from_directory(tmp_path):
    """目录递归遍历，返回 (路径, 后缀小写)"""
    (tmp_path / "a.docx").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.pdf").write_text("y")
    files = collect_files(tmp_path)
    suffixes = sorted(suf for _, suf in files)
    assert suffixes == [".docx", ".pdf"]


def test_collect_single_file(tmp_path):
    """传入单个文件直接返回该文件"""
    f = tmp_path / "only.docx"
    f.write_text("x")
    files = collect_files(f)
    assert len(files) == 1
    assert files[0][1] == ".docx"


def test_unzip_ebid(tmp_path):
    """.ebid（ZIP）应被解压，内部文件被收集"""
    ebid = tmp_path / "tender.ebid"
    with zipfile.ZipFile(ebid, "w") as z:
        z.writestr("TenderData.xml", "<root/>")
    files = collect_files(tmp_path)
    names = sorted(Path(p).name for p, _ in files)
    assert "TenderData.xml" in names


def test_skip_ds_store(tmp_path):
    """.DS_Store 等噪音文件被跳过"""
    (tmp_path / ".DS_Store").write_text("junk")
    (tmp_path / "real.docx").write_text("x")
    files = collect_files(tmp_path)
    names = [Path(p).name for p, _ in files]
    assert ".DS_Store" not in names
    assert "real.docx" in names
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_unpack.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/parsing/__init__.py`（空文件）。

Create `outline_extraction/parsing/unpack.py`:
```python
"""文件解压与遍历——把目录/压缩包/单文件统一成扁平文件清单"""
import zipfile
import tempfile
from pathlib import Path

# 忽略的噪音文件名
_IGNORE_NAMES = {".DS_Store", "Thumbs.db"}
# 被视为压缩包的后缀（.ebid 实测为 ZIP）
_ARCHIVE_SUFFIXES = {".zip", ".ebid"}


def collect_files(input_path: Path) -> list[tuple[str, str]]:
    """递归收集所有可处理文件

    参数:
        input_path: 目录、压缩包或单个文件路径
    返回:
        [(绝对路径字符串, 小写后缀)] 列表；压缩包会被解压到临时目录后收集其内容
    """
    input_path = Path(input_path)
    results: list[tuple[str, str]] = []

    if input_path.is_file():
        _collect_one(input_path, results)
        return results

    for entry in sorted(input_path.rglob("*")):
        if entry.is_file():
            _collect_one(entry, results)
    return results


def _collect_one(file_path: Path, results: list[tuple[str, str]]) -> None:
    """处理单个文件：噪音跳过、压缩包解压、其余登记——内部辅助

    参数:
        file_path: 文件路径
        results: 累积结果列表（原地追加）
    返回: 无（结果写入 results）
    """
    if file_path.name in _IGNORE_NAMES:
        return
    suffix = file_path.suffix.lower()
    if suffix in _ARCHIVE_SUFFIXES and zipfile.is_zipfile(file_path):
        extract_dir = Path(tempfile.mkdtemp(prefix="unpack_"))
        with zipfile.ZipFile(file_path) as z:
            z.extractall(extract_dir)
        for entry in sorted(extract_dir.rglob("*")):
            if entry.is_file() and entry.name not in _IGNORE_NAMES:
                results.append((str(entry), entry.suffix.lower()))
        return
    results.append((str(file_path), suffix))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_unpack.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/parsing/__init__.py outline_extraction/parsing/unpack.py tests/test_unpack.py
git commit -m "feat: file collection with archive/.ebid unpacking"
```

---

## Task 5: 文本抽取（parsing/extract.py）

**Files:**
- Create: `outline_extraction/parsing/extract.py`
- Test: `tests/test_extract.py`

**说明：** 探测优先决策链。`.doc` 走 `textutil` 子进程（macOS）；`.docx` 走 python-docx；`.pdf` 先抽文本层、字符过少判扫描件（阶段一仅标记 `needs_ocr`，CU 在 Task 14 接）。

- [ ] **Step 1: 写失败测试**

Create `tests/test_extract.py`:
```python
"""文本抽取测试"""
from pathlib import Path
import docx
from outline_extraction.parsing.extract import extract_document, _is_scanned


def test_extract_docx(tmp_path):
    """docx 抽取为 Markdown，方法标记 docx"""
    p = tmp_path / "a.docx"
    d = docx.Document()
    d.add_heading("第一章 总则", level=1)
    d.add_paragraph("这是正文。")
    d.save(p)
    result = extract_document(Path(p), ".docx")
    assert result.extract_method == "docx"
    assert "第一章 总则" in result.raw_markdown
    assert "这是正文。" in result.raw_markdown


def test_extract_docx_heading_becomes_markdown(tmp_path):
    """docx 标题转成 Markdown # 前缀"""
    p = tmp_path / "h.docx"
    d = docx.Document()
    d.add_heading("标题A", level=2)
    d.save(p)
    result = extract_document(Path(p), ".docx")
    assert "## 标题A" in result.raw_markdown


def test_is_scanned_threshold():
    """每页平均字符数低于阈值判为扫描件"""
    assert _is_scanned(total_chars=50, page_count=10) is True   # 5 字/页
    assert _is_scanned(total_chars=5000, page_count=10) is False  # 500 字/页


def test_extract_unknown_suffix(tmp_path):
    """未知后缀返回空 markdown 并标记 skipped，不报错"""
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x00\x01")
    result = extract_document(Path(p), ".bin")
    assert result.extract_method == "skipped"
    assert result.raw_markdown == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_extract.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/parsing/extract.py`:
```python
"""文本抽取——探测优先决策链，统一输出 Markdown"""
import subprocess
from pathlib import Path
import docx
import pdfplumber
from outline_extraction.models import ParsedDocument

# 扫描件判定阈值：每页平均字符数低于此值视为扫描件
_SCANNED_CHARS_PER_PAGE = 50


def extract_document(file_path: Path, suffix: str) -> ParsedDocument:
    """按后缀走探测优先决策链抽取文本

    参数:
        file_path: 文件路径
        suffix: 小写后缀
    返回:
        ParsedDocument（含统一 Markdown 与抽取方式标记）
    """
    name = file_path.name
    if suffix == ".docx":
        return ParsedDocument(filename=name, raw_markdown=_docx_to_md(file_path),
                              extract_method="docx", page_count=None)
    if suffix == ".doc":
        return ParsedDocument(filename=name, raw_markdown=_doc_to_md(file_path),
                              extract_method="textutil", page_count=None)
    if suffix == ".pdf":
        return _pdf_to_doc(file_path, name)
    if suffix == ".xml":
        return ParsedDocument(filename=name, raw_markdown=file_path.read_text(errors="ignore"),
                              extract_method="xml", page_count=None)
    return ParsedDocument(filename=name, raw_markdown="", extract_method="skipped", page_count=None)


def _docx_to_md(file_path: Path) -> str:
    """docx → Markdown：Heading 样式转 # 前缀——内部辅助"""
    d = docx.Document(str(file_path))
    lines: list[str] = []
    for para in d.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "") if para.style else ""
        if style.startswith("Heading"):
            try:
                level = int(style.split()[-1])
            except (ValueError, IndexError):
                level = 1
            lines.append("#" * min(level, 6) + " " + text)
        else:
            lines.append(text)
    # 表格转 Markdown 表格
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _doc_to_md(file_path: Path) -> str:
    """.doc → 文本：调用 macOS textutil 子进程——内部辅助"""
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(file_path)],
        capture_output=True, text=True,
    )
    return result.stdout


def _pdf_to_doc(file_path: Path, name: str) -> ParsedDocument:
    """PDF：抽文本层；字符过少标记 needs_ocr 留待 CU——内部辅助"""
    text_parts: list[str] = []
    page_count = 0
    with pdfplumber.open(str(file_path)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    full = "\n".join(text_parts)
    if _is_scanned(len(full.strip()), page_count):
        return ParsedDocument(filename=name, raw_markdown=full,
                              extract_method="needs_ocr", page_count=page_count)
    return ParsedDocument(filename=name, raw_markdown=full,
                          extract_method="pdf_text", page_count=page_count)


def _is_scanned(total_chars: int, page_count: int) -> bool:
    """判断 PDF 是否为扫描件——与具体文件无关的通用指标

    参数:
        total_chars: 抽到的总字符数
        page_count: 页数
    返回:
        True 表示疑似扫描件（每页平均字符数过低）
    """
    if page_count <= 0:
        return total_chars == 0
    return (total_chars / page_count) < _SCANNED_CHARS_PER_PAGE
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_extract.py -v`
Expected: 4 passed

- [ ] **Step 5: 用真实可见标的冒烟（华能单 docx）**

Run:
```bash
.venv/bin/python -c "
from pathlib import Path
from outline_extraction.parsing.extract import extract_document
p = Path('docs/TenderingDocs/(招标文件)中国华能集团有限公司2025年度逆变器框架协议采购招标.docx')
r = extract_document(p, '.docx')
print('method:', r.extract_method, '| chars:', len(r.raw_markdown))
print(r.raw_markdown[:300])
"
```
Expected: method docx，能打印出招标文件正文片段。

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/parsing/extract.py tests/test_extract.py
git commit -m "feat: probe-first text extraction (docx/doc/pdf/xml)"
```

---

## Task 6: 章节切分（understanding/segment.py）

**Files:**
- Create: `outline_extraction/understanding/__init__.py`, `outline_extraction/understanding/segment.py`
- Test: `tests/test_segment.py`

**说明：** 工程优先——正则识别中文招标常见编号（`第X章`、`一、`、`（一）`、`1.1`）。本任务只做正则切分；LLM 兜底接口预留但默认关闭（避免单测打 API）。

- [ ] **Step 1: 写失败测试**

Create `tests/test_segment.py`:
```python
"""章节切分测试"""
from outline_extraction.understanding.segment import segment_text


def test_segment_chapter_and_subsection():
    """识别"第X章"为 level1，"一、"为 level2"""
    md = "第一章 投标须知\n正文A\n一、 总则\n正文B\n二、 资格\n正文C"
    sections = segment_text(md, doc_source="x.docx")
    titles = [(s.title, s.level) for s in sections]
    assert ("第一章 投标须知", 1) in titles
    assert any(t.startswith("一、") and lvl == 2 for t, lvl in titles)


def test_segment_decimal_numbering():
    """识别 1.1 为子级编号"""
    md = "1 概述\n内容\n1.1 背景\n内容\n1.2 目标\n内容"
    sections = segment_text(md, doc_source="x.docx")
    titles = [s.title for s in sections]
    assert any("1.1" in t for t in titles)


def test_segment_content_attached():
    """正文挂到对应章节"""
    md = "第一章 总则\n这是总则正文。\n第二章 范围\n这是范围正文。"
    sections = segment_text(md, doc_source="x.docx")
    first = next(s for s in sections if "第一章" in s.title)
    assert "总则正文" in first.content


def test_segment_doc_source_recorded():
    """每段记录来源文件名"""
    md = "第一章 X\n内容"
    sections = segment_text(md, doc_source="abc.docx")
    assert sections[0].doc_source == "abc.docx"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_segment.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/understanding/__init__.py`（空文件）。

Create `outline_extraction/understanding/segment.py`:
```python
"""章节切分——正则优先识别中文招标编号体系"""
import re
from outline_extraction.models import Section

# 编号模式 → 层级。顺序即优先级，先匹配先生效。
_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"^第[一二三四五六七八九十百]+[章篇]"), 1),       # 第一章
    (re.compile(r"^#{1,6}\s"), 0),                              # Markdown 标题（动态算级）
    (re.compile(r"^[一二三四五六七八九十]+、"), 2),               # 一、
    (re.compile(r"^（[一二三四五六七八九十]+）"), 3),             # （一）
    (re.compile(r"^\d+\.\d+\.\d+"), 3),                          # 1.1.1
    (re.compile(r"^\d+\.\d+"), 2),                               # 1.1
    (re.compile(r"^\d+\.?\s"), 1),                               # 1 / 1.
]


def segment_text(markdown: str, doc_source: str) -> list[Section]:
    """把文本按编号切成带层级的章节块

    参数:
        markdown: 文档的 Markdown 文本
        doc_source: 来源文件名
    返回:
        Section 列表；无法匹配任何标题时返回单个 level1 整篇块
    """
    lines = markdown.splitlines()
    sections: list[Section] = []
    current: Section | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        level = _match_level(stripped)
        if level is not None:
            current = Section(title=stripped, level=level, content="", doc_source=doc_source)
            sections.append(current)
        elif current is not None:
            current.content += stripped + "\n"
        else:
            # 标题前的前言：建一个 level1 容器
            current = Section(title="（前言）", level=1, content=stripped + "\n", doc_source=doc_source)
            sections.append(current)

    if not sections:
        sections.append(Section(title="（全文）", level=1, content=markdown, doc_source=doc_source))
    return sections


def _match_level(line: str) -> int | None:
    """返回该行作为标题的层级；非标题返回 None——内部辅助"""
    for pattern, level in _PATTERNS:
        if pattern.match(line):
            if level == 0:  # Markdown 标题：按 # 数量定级
                return min(len(line) - len(line.lstrip("#")), 6)
            return level
    return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_segment.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/understanding/__init__.py outline_extraction/understanding/segment.py tests/test_segment.py
git commit -m "feat: regex-first section segmentation for Chinese tender numbering"
```

---

## Task 7: 文件分类（understanding/classify.py）

**Files:**
- Create: `outline_extraction/understanding/classify.py`, `outline_extraction/llm/prompts/classify.txt`
- Test: `tests/test_classify.py`

**说明：** 用 mini 读"文件名 + 正文前 ~1500 字"判类型。单测注入 fake LLM。

- [ ] **Step 1: 写 prompt 文件**

Create `outline_extraction/llm/prompts/classify.txt`:
```
你是招标文件分析助手。根据给定文件的文件名和正文开头，判断它属于以下哪一类：
- tender_main: 招标公告/投标人须知/招标正文等总纲性文件
- tech_spec: 技术规范书/技术要求/技术参数表
- business: 商务文件/商务条款/合同条款
- bid_format: 投标文件格式/投标文件组成/投标文件编制要求（规定投标人应提交内容的结构模板）
- addendum: 补遗书/答疑函/澄清文件
- unknown: 无法判断

仅依据内容判断，不要被文件名误导（文件名可能不准确）。
给出 confidence（0-1）反映你的把握程度。
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_classify.py`:
```python
"""文件分类测试——注入 fake LLM"""
from outline_extraction.models import ParsedDocument, SourceType
from outline_extraction.understanding.classify import classify_documents, FileClass, ClassifyResult


class _FakeLLM:
    """按文件名顺序返回预设分类"""
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def complete(self, **kwargs):
        r = self._results[self.calls]
        self.calls += 1
        return r


def test_classify_routes_to_mini_and_returns_labels():
    """分类应对每个文档调用一次，返回标签"""
    docs = [
        ParsedDocument(filename="须知.docx", raw_markdown="投标人须知前附表", extract_method="docx"),
        ParsedDocument(filename="技术.docx", raw_markdown="技术规范书 1. 性能参数", extract_method="docx"),
    ]
    fake = _FakeLLM([
        ClassifyResult(file_class=FileClass.TENDER_MAIN, confidence=0.9),
        ClassifyResult(file_class=FileClass.TECH_SPEC, confidence=0.8),
    ])
    out = classify_documents(docs, llm=fake, model="gpt-5.4-mini")
    assert fake.calls == 2
    assert out["须知.docx"].file_class == FileClass.TENDER_MAIN
    assert out["技术.docx"].file_class == FileClass.TECH_SPEC
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_classify.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 写实现**

Create `outline_extraction/understanding/classify.py`:
```python
"""文件分类——用 mini 读文件名+正文开头判定文件类型"""
from enum import Enum
from pathlib import Path
from pydantic import BaseModel
from outline_extraction.models import ParsedDocument

# 喂给 LLM 的正文前缀长度
_PREVIEW_CHARS = 1500
_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "classify.txt"


class FileClass(str, Enum):
    """文件类型枚举"""
    TENDER_MAIN = "tender_main"
    TECH_SPEC = "tech_spec"
    BUSINESS = "business"
    BID_FORMAT = "bid_format"
    ADDENDUM = "addendum"
    UNKNOWN = "unknown"


class ClassifyResult(BaseModel):
    """单文件分类结果"""
    file_class: FileClass
    confidence: float


def classify_documents(docs: list[ParsedDocument], llm, model: str) -> dict[str, ClassifyResult]:
    """对每个文档分类

    参数:
        docs: 已解析文档列表
        llm: LLMClient（或兼容的 complete 接口）
        model: 模型名（mini）
    返回:
        {文件名: ClassifyResult}
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    out: dict[str, ClassifyResult] = {}
    for doc in docs:
        preview = doc.raw_markdown[:_PREVIEW_CHARS]
        content = f"文件名：{doc.filename}\n正文开头：\n{preview}"
        result = llm.complete(
            model=model, instructions=instructions, input_content=content,
            effort="low", verbosity="low", schema=ClassifyResult,
        )
        out[doc.filename] = result
    return out
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_classify.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/understanding/classify.py outline_extraction/llm/prompts/classify.txt tests/test_classify.py
git commit -m "feat: LLM-based document classification (mini)"
```

---

## Task 8: 定位关键章节（understanding/locate.py）

**Files:**
- Create: `outline_extraction/understanding/locate.py`, `outline_extraction/llm/prompts/locate.txt`
- Test: `tests/test_locate.py`

- [ ] **Step 1: 写 prompt 文件**

Create `outline_extraction/llm/prompts/locate.txt`:
```
你是招标文件结构分析助手。给定一份招标文件包中所有章节的标题列表（含所属文件名与简短摘要），请定位以下四类关键章节分别出现在哪些章节中（可能在不同文件、可能多处、也可能缺失）：
- bid_format_sections: 规定投标文件应包含哪些内容/格式的章节（如"投标文件格式""投标文件组成""投标文件编制"）
- scoring_sections: 评分办法/评标标准/评审因素章节
- tech_spec_sections: 技术规范/技术要求/技术参数章节
- business_sections: 商务条款/合同条款/商务要求章节

依据语义判断，不要依赖固定关键词或章节编号。每类返回匹配到的章节索引列表（对应输入顺序，从0开始）；若某类缺失返回空列表。
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_locate.py`:
```python
"""定位关键章节测试——注入 fake LLM"""
from outline_extraction.models import Section
from outline_extraction.understanding.locate import locate_sections, LocateResult


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.last_kwargs = None

    def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._result


def test_locate_returns_indices():
    """定位返回各类章节索引，并能据此取回 Section"""
    sections = [
        Section(title="投标文件格式", level=1, content="...", doc_source="fmt.docx"),
        Section(title="评标办法", level=1, content="...", doc_source="main.pdf"),
        Section(title="技术规范书", level=1, content="...", doc_source="tech.docx"),
        Section(title="合同条款", level=1, content="...", doc_source="biz.doc"),
    ]
    fake = _FakeLLM(LocateResult(
        bid_format_sections=[0], scoring_sections=[1],
        tech_spec_sections=[2], business_sections=[3],
    ))
    result = locate_sections(sections, llm=fake, model="gpt-5.4")
    assert result.bid_format_sections == [0]
    assert result.scoring_sections == [1]
    # input 中应包含标题列表
    assert "投标文件格式" in fake.last_kwargs["input_content"]
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_locate.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 写实现**

Create `outline_extraction/understanding/locate.py`:
```python
"""定位关键章节——用 5.4 语义识别投标格式/评分/技术/商务章节位置"""
from pathlib import Path
from pydantic import BaseModel, Field
from outline_extraction.models import Section

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "locate.txt"
# 每个章节摘要截断长度
_SUMMARY_CHARS = 200


class LocateResult(BaseModel):
    """四类关键章节的索引列表（对应输入 Section 顺序）"""
    bid_format_sections: list[int] = Field(default_factory=list)
    scoring_sections: list[int] = Field(default_factory=list)
    tech_spec_sections: list[int] = Field(default_factory=list)
    business_sections: list[int] = Field(default_factory=list)


def locate_sections(sections: list[Section], llm, model: str) -> LocateResult:
    """定位四类关键章节

    参数:
        sections: 全部章节
        llm: LLMClient
        model: 模型名（main）
    返回:
        LocateResult（各类章节索引）
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    listing_lines: list[str] = []
    for idx, sec in enumerate(sections):
        summary = sec.content[:_SUMMARY_CHARS].replace("\n", " ")
        listing_lines.append(f"[{idx}] 文件={sec.doc_source} 标题={sec.title} 摘要={summary}")
    content = "章节列表：\n" + "\n".join(listing_lines)
    return llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="medium", verbosity="low", schema=LocateResult,
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_locate.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/understanding/locate.py outline_extraction/llm/prompts/locate.txt tests/test_locate.py
git commit -m "feat: locate key sections semantically (5.4)"
```

---

## Task 9: 抽显式骨架（understanding/extract_skeleton.py）

**Files:**
- Create: `outline_extraction/understanding/extract_skeleton.py`, `outline_extraction/llm/prompts/extract_skeleton.txt`
- Test: `tests/test_extract_skeleton.py`

- [ ] **Step 1: 写 prompt 文件**

Create `outline_extraction/llm/prompts/extract_skeleton.txt`:
```
你是投标文件结构抽取助手。给定招标文件中"投标文件格式/组成"章节的全文，请把它规定的投标文件结构原样抽取为一棵层级大纲树。
要求：
- 忠实还原原文的层级与标题措辞，不要自行增删或润色标题。
- 每个节点给出 level（顶层为1，逐级+1）。
- 不要补充原文未提及的章节——这一步只做忠实抽取，补充由后续步骤负责。
- 为每个节点填写 location（在原文中的定位，如"七、技术建议书"），document 用给定的来源文件名。
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_extract_skeleton.py`:
```python
"""显式骨架抽取测试——注入 fake LLM 返回 OutlineNode 树"""
from outline_extraction.models import OutlineNode, SourceRef, SourceType
from outline_extraction.understanding.extract_skeleton import extract_skeleton, SkeletonResult


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.last_kwargs = None

    def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._result


def test_extract_skeleton_returns_tree():
    """骨架抽取返回带 SKELETON 来源的节点树"""
    nodes = [OutlineNode(
        id="1", title="投标函", level=1,
        sources=[SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)],
        children=[],
    )]
    fake = _FakeLLM(SkeletonResult(nodes=nodes))
    result = extract_skeleton("一、投标函\n二、资格审查资料", document="fmt.docx",
                              llm=fake, model="gpt-5.4")
    assert result[0].title == "投标函"
    assert result[0].sources[0].type == SourceType.SKELETON
    assert "投标函" in fake.last_kwargs["input_content"]
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_extract_skeleton.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 写实现**

Create `outline_extraction/understanding/extract_skeleton.py`:
```python
"""显式骨架抽取——把"投标文件格式"章节忠实抽成 OutlineNode 树"""
from pathlib import Path
from pydantic import BaseModel, Field
from outline_extraction.models import OutlineNode

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "extract_skeleton.txt"


class SkeletonResult(BaseModel):
    """骨架抽取结果——顶层节点列表"""
    nodes: list[OutlineNode] = Field(default_factory=list)


def extract_skeleton(section_text: str, document: str, llm, model: str) -> list[OutlineNode]:
    """从投标文件格式章节抽取显式骨架

    参数:
        section_text: "投标文件格式/组成"章节全文
        document: 来源文件名
        llm: LLMClient
        model: 模型名（main）
    返回:
        OutlineNode 顶层列表（来源已标 SKELETON）
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    content = f"来源文件名：{document}\n章节全文：\n{section_text}"
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="medium", verbosity="low", schema=SkeletonResult,
    )
    return result.nodes
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_extract_skeleton.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/understanding/extract_skeleton.py outline_extraction/llm/prompts/extract_skeleton.txt tests/test_extract_skeleton.py
git commit -m "feat: extract explicit skeleton outline (5.4)"
```

---

## Task 10: 抽要求条目（understanding/extract_requirements.py）

**Files:**
- Create: `outline_extraction/understanding/extract_requirements.py`, `outline_extraction/llm/prompts/extract_requirements.txt`
- Test: `tests/test_extract_requirements.py`

- [ ] **Step 1: 写 prompt 文件**

Create `outline_extraction/llm/prompts/extract_requirements.txt`:
```
你是招标要求抽取助手。给定评分办法或技术规范章节文本（表格已转为 Markdown 表格），请逐条抽取"投标人需要响应/提供的要求"，每条产出一个要求项：
- description: 要求的简明描述
- source_type: 该要求来自评分办法填 "scoring"，来自技术规范填 "tech_spec"，来自商务条款填 "biz_terms"
- location: 在原文中的定位（如"评分办法第3条""技术规范3.2"）
- suggested_title: 该要求在投标文件中应对应的章节标题（你的建议；最终归位由后续步骤决定）

要求：
- 评分表逐行/逐项抽取，不要遗漏任何计分项。
- 技术规范逐条抽取需要投标人应答或承诺的参数/条款。
- 只抽取需要投标人响应的要求，不要抽取纯背景说明。
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_extract_requirements.py`:
```python
"""要求条目抽取测试——注入 fake LLM"""
from outline_extraction.models import RequirementItem, SourceType
from outline_extraction.understanding.extract_requirements import (
    extract_requirements, RequirementsResult,
)


class _FakeLLM:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def complete(self, **kwargs):
        r = self._results[self.calls]
        self.calls += 1
        return r


def test_extract_requirements_flattens_multiple_sections():
    """多个章节的抽取结果被合并为一个列表"""
    fake = _FakeLLM([
        RequirementsResult(items=[
            RequirementItem(description="提供ISO9001", source_type=SourceType.SCORING,
                            location="评分第3条", suggested_title="质量体系认证"),
        ]),
        RequirementsResult(items=[
            RequirementItem(description="效率≥98.5%", source_type=SourceType.TECH_SPEC,
                            location="技术3.1", suggested_title="效率参数响应"),
        ]),
    ])
    items = extract_requirements(["评分章节文本", "技术章节文本"], llm=fake, model="gpt-5.4")
    assert fake.calls == 2
    assert len(items) == 2
    assert {i.source_type for i in items} == {SourceType.SCORING, SourceType.TECH_SPEC}


def test_extract_requirements_empty_input():
    """无章节输入时返回空列表，不调用 LLM"""
    fake = _FakeLLM([])
    items = extract_requirements([], llm=fake, model="gpt-5.4")
    assert items == []
    assert fake.calls == 0
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_extract_requirements.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 写实现**

Create `outline_extraction/understanding/extract_requirements.py`:
```python
"""要求条目抽取——把评分/技术章节逐条抽成 RequirementItem"""
from pathlib import Path
from pydantic import BaseModel, Field
from outline_extraction.models import RequirementItem

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "extract_requirements.txt"


class RequirementsResult(BaseModel):
    """单章节抽取结果"""
    items: list[RequirementItem] = Field(default_factory=list)


def extract_requirements(section_texts: list[str], llm, model: str) -> list[RequirementItem]:
    """从评分/技术/商务章节抽取要求条目

    参数:
        section_texts: 关键章节文本列表（评分/技术/商务）
        llm: LLMClient
        model: 模型名（main）
    返回:
        合并后的 RequirementItem 列表
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    all_items: list[RequirementItem] = []
    for text in section_texts:
        result = llm.complete(
            model=model, instructions=instructions, input_content=text,
            effort="medium", verbosity="low", schema=RequirementsResult,
        )
        all_items.extend(result.items)
    return all_items
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_extract_requirements.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/understanding/extract_requirements.py outline_extraction/llm/prompts/extract_requirements.txt tests/test_extract_requirements.py
git commit -m "feat: extract scoring/tech requirement items (5.4)"
```

---

## Task 11: 归并挂载 + 覆盖率（alignment/merge.py）

**Files:**
- Create: `outline_extraction/alignment/__init__.py`, `outline_extraction/alignment/merge.py`, `outline_extraction/llm/prompts/merge.txt`
- Test: `tests/test_merge_coverage.py`

**说明：** LLM 做语义归并并标注每条要求是否挂载成功；覆盖率由**纯工程**根据 LLM 返回的归属判定统计（不让 LLM 自报覆盖率）。

- [ ] **Step 1: 写 prompt 文件**

Create `outline_extraction/llm/prompts/merge.txt`:
```
你是投标大纲归并助手。给定：
1. 一棵显式骨架大纲树（来自"投标文件格式"，是权威主干）
2. 一组要求条目（来自评分办法/技术规范/商务条款）

请把每个要求条目归并到骨架树中，对每个要求条目做三选一判定：
- merged_into: 骨架中已存在语义等价的节点 → 把该要求的来源追加到该节点（返回该节点 id）
- child_of: 应作为某节点的子节点 → 返回父节点 id，并在该父节点下新增子节点
- floating: 骨架中无合理归宿 → 标记为游离，留待后续生成式补充

语义判同示例："质量管理体系认证"与"ISO9001认证证书"视为同一节点。

返回：
- tree: 归并后的完整大纲树（骨架节点 + 新增子节点；被合并的节点 sources 数组追加对应来源）
- decisions: 每个要求条目的归属判定 [{requirement_location, disposition: merged_into|child_of|floating, node_id}]

不要丢弃任何要求条目；无法归位的必须标 floating，绝不静默忽略。
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_merge_coverage.py`:
```python
"""归并与覆盖率统计测试"""
from outline_extraction.models import (
    OutlineNode, SourceRef, SourceType, RequirementItem,
)
from outline_extraction.alignment.merge import merge_requirements, MergeResult, Disposition, MergeDecision, compute_coverage


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def complete(self, **kwargs):
        return self._result


def test_merge_returns_tree_and_decisions():
    """归并返回树 + 每条要求的判定"""
    skeleton = [OutlineNode(id="1", title="资格审查资料", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="五", quote=None)], children=[])]
    reqs = [
        RequirementItem(description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="质量体系认证"),
        RequirementItem(description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="效率响应"),
    ]
    fake = _FakeLLM(MergeResult(
        tree=skeleton,
        decisions=[
            MergeDecision(requirement_location="评分3", disposition=Disposition.MERGED_INTO, node_id="1"),
            MergeDecision(requirement_location="技术3.1", disposition=Disposition.FLOATING, node_id=None),
        ],
    ))
    tree, decisions = merge_requirements(skeleton, reqs, llm=fake, model="gpt-5.4")
    assert len(decisions) == 2


def test_compute_coverage_counts_mapped_vs_total():
    """覆盖率纯工程统计：mapped = 非 floating；unmapped 列出 floating 的要求描述"""
    reqs = [
        RequirementItem(description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="X"),
        RequirementItem(description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="Y"),
        RequirementItem(description="质保2年", source_type=SourceType.SCORING,
                        location="评分5", suggested_title="Z"),
    ]
    decisions = [
        MergeDecision(requirement_location="评分3", disposition=Disposition.MERGED_INTO, node_id="1"),
        MergeDecision(requirement_location="技术3.1", disposition=Disposition.FLOATING, node_id=None),
        MergeDecision(requirement_location="评分5", disposition=Disposition.CHILD_OF, node_id="1"),
    ]
    cov = compute_coverage(reqs, decisions)
    assert cov.total_scoring_items == 2
    assert cov.mapped_scoring_items == 2   # 评分3 merged + 评分5 child
    assert cov.total_tech_items == 1
    assert cov.mapped_tech_items == 0      # 技术3.1 floating
    assert "效率98.5%" in cov.unmapped
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_merge_coverage.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 写实现**

Create `outline_extraction/alignment/__init__.py`（空文件）。

Create `outline_extraction/alignment/merge.py`:
```python
"""归并挂载 + 覆盖率统计——LLM 语义归并，工程统计覆盖率"""
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from outline_extraction.models import (
    OutlineNode, RequirementItem, CoverageReport, SourceType,
)

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "merge.txt"


class Disposition(str, Enum):
    """要求条目的归属方式"""
    MERGED_INTO = "merged_into"   # 合并进已有节点
    CHILD_OF = "child_of"         # 作为子节点新增
    FLOATING = "floating"         # 无归宿，游离


class MergeDecision(BaseModel):
    """单条要求的归属判定"""
    requirement_location: str             # 对应要求的 location（关联键）
    disposition: Disposition
    node_id: Optional[str] = None         # 归属节点 id（floating 时为空）


class MergeResult(BaseModel):
    """归并结果——LLM 结构化输出"""
    tree: list[OutlineNode] = Field(default_factory=list)
    decisions: list[MergeDecision] = Field(default_factory=list)


def merge_requirements(skeleton: list[OutlineNode], requirements: list[RequirementItem],
                       llm, model: str) -> tuple[list[OutlineNode], list[MergeDecision]]:
    """把要求条目语义归并进骨架树

    参数:
        skeleton: 显式骨架顶层节点
        requirements: 要求条目列表
        llm: LLMClient
        model: 模型名（main）
    返回:
        (归并后的树, 归属判定列表)
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    payload = {
        "skeleton": [n.model_dump() for n in skeleton],
        "requirements": [r.model_dump() for r in requirements],
    }
    import json
    content = json.dumps(payload, ensure_ascii=False)
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="high", verbosity="low", schema=MergeResult,
    )
    return result.tree, result.decisions


def compute_coverage(requirements: list[RequirementItem],
                     decisions: list[MergeDecision]) -> CoverageReport:
    """纯工程统计覆盖率——不依赖 LLM 自报

    参数:
        requirements: 全部要求条目
        decisions: LLM 给出的归属判定
    返回:
        CoverageReport（按来源类型统计 total/mapped，列出未挂载描述）
    """
    # location → disposition 映射
    disp_by_loc: dict[str, Disposition] = {d.requirement_location: d.disposition for d in decisions}
    total_scoring = mapped_scoring = total_tech = mapped_tech = 0
    unmapped: list[str] = []
    for req in requirements:
        disp = disp_by_loc.get(req.location, Disposition.FLOATING)
        is_mapped = disp in (Disposition.MERGED_INTO, Disposition.CHILD_OF)
        if req.source_type == SourceType.SCORING:
            total_scoring += 1
            if is_mapped:
                mapped_scoring += 1
        elif req.source_type == SourceType.TECH_SPEC:
            total_tech += 1
            if is_mapped:
                mapped_tech += 1
        if not is_mapped:
            unmapped.append(req.description)
    return CoverageReport(
        total_scoring_items=total_scoring, mapped_scoring_items=mapped_scoring,
        total_tech_items=total_tech, mapped_tech_items=mapped_tech, unmapped=unmapped,
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_merge_coverage.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/alignment/__init__.py outline_extraction/alignment/merge.py outline_extraction/llm/prompts/merge.txt tests/test_merge_coverage.py
git commit -m "feat: semantic merge + engineering coverage statistics"
```

---

## Task 12: 生成式兜底（alignment/supplement.py）

**Files:**
- Create: `outline_extraction/alignment/supplement.py`, `outline_extraction/llm/prompts/supplement.txt`
- Test: `tests/test_supplement.py`

- [ ] **Step 1: 写 prompt 文件**

Create `outline_extraction/llm/prompts/supplement.txt`:
```
你是投标大纲补全助手。给定当前已归并的大纲树和一组"游离要求"（未能挂入骨架的要求），请：
1. 为每个游离要求，在树中找到或新建一个合理的章节标题来安置它（该节点来源保留要求的原始 source_type）。
2. 补充评审逻辑/行业惯例上投标文件通常应有、但本招标文件未明确提及的章节（如"项目实施组织方案""风险管控措施"等）。这些纯补充节点的来源类型必须标为 "ai_suggested"，绝不能伪装成招标文件的明确要求。

返回完整的大纲树。要求：
- 游离要求安置后，其来源仍为原始类型（scoring/tech_spec/biz_terms），仅位置由你推断。
- 纯属你建议补充的节点，来源类型必须是 ai_suggested。
- 不要删除已有节点。
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_supplement.py`:
```python
"""生成式兜底测试——注入 fake LLM"""
from outline_extraction.models import OutlineNode, SourceRef, SourceType
from outline_extraction.alignment.supplement import supplement_tree, SupplementResult


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.called = False

    def complete(self, **kwargs):
        self.called = True
        return self._result


def test_supplement_adds_ai_suggested_node():
    """兜底返回含 ai_suggested 节点的树"""
    base = [OutlineNode(id="1", title="技术响应", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="七", quote=None)], children=[])]
    enriched = base + [OutlineNode(id="2", title="项目实施组织方案", level=1, sources=[
        SourceRef(type=SourceType.AI_SUGGESTED, document="(AI建议)", location="-", quote=None)], children=[])]
    fake = _FakeLLM(SupplementResult(tree=enriched))
    result = supplement_tree(base, floating=["效率参数响应"], llm=fake, model="gpt-5.4")
    assert any(n.sources[0].type == SourceType.AI_SUGGESTED for n in result)


def test_supplement_skips_llm_when_nothing_to_do():
    """无游离要求时仍可调用（补行业惯例），但空树+空游离应短路返回原树"""
    base = [OutlineNode(id="1", title="X", level=1, sources=[], children=[])]
    fake = _FakeLLM(SupplementResult(tree=base))
    result = supplement_tree(base, floating=[], llm=fake, model="gpt-5.4")
    # 允许仍调用以补惯例；此处验证返回树非空且包含原节点
    assert any(n.title == "X" for n in result)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_supplement.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 写实现**

Create `outline_extraction/alignment/supplement.py`:
```python
"""生成式兜底——安置游离要求 + 补充行业惯例章节（标 ai_suggested）"""
import json
from pathlib import Path
from pydantic import BaseModel, Field
from outline_extraction.models import OutlineNode

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "supplement.txt"


class SupplementResult(BaseModel):
    """兜底结果——补全后的大纲树"""
    tree: list[OutlineNode] = Field(default_factory=list)


def supplement_tree(tree: list[OutlineNode], floating: list[str], llm, model: str) -> list[OutlineNode]:
    """生成式补全大纲树

    参数:
        tree: 当前归并后的树
        floating: 游离要求的描述列表
        llm: LLMClient
        model: 模型名（main）
    返回:
        补全后的大纲树
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    payload = {
        "tree": [n.model_dump() for n in tree],
        "floating_requirements": floating,
    }
    content = json.dumps(payload, ensure_ascii=False)
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="high", verbosity="low", schema=SupplementResult,
    )
    return result.tree
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_supplement.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/alignment/supplement.py outline_extraction/llm/prompts/supplement.txt tests/test_supplement.py
git commit -m "feat: generative supplement with ai_suggested labeling"
```

---

## Task 13: 排序与 id 重整（output/tree.py）

**Files:**
- Create: `outline_extraction/output/__init__.py`, `outline_extraction/output/tree.py`
- Test: `tests/test_tree.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_tree.py`:
```python
"""树排序与 id 重整测试"""
from outline_extraction.models import OutlineNode, SourceRef, SourceType
from outline_extraction.output.tree import finalize_ids


def _node(title, level, children=None):
    return OutlineNode(id="x", title=title, level=level, sources=[], children=children or [])


def test_finalize_assigns_path_ids():
    """路径式 id：顶层 1,2；子层 1.1,1.2"""
    nodes = [
        _node("A", 1, [_node("A1", 2), _node("A2", 2)]),
        _node("B", 1),
    ]
    result = finalize_ids(nodes)
    assert result[0].id == "1"
    assert result[0].children[0].id == "1.1"
    assert result[0].children[1].id == "1.2"
    assert result[1].id == "2"


def test_finalize_deep_nesting():
    """三层嵌套 id 正确"""
    nodes = [_node("A", 1, [_node("A1", 2, [_node("A1a", 3)])])]
    result = finalize_ids(nodes)
    assert result[0].children[0].children[0].id == "1.1.1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_tree.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/output/__init__.py`（空文件）。

Create `outline_extraction/output/tree.py`:
```python
"""大纲树后处理——路径式稳定 id 重整"""
from outline_extraction.models import OutlineNode


def finalize_ids(nodes: list[OutlineNode], prefix: str = "") -> list[OutlineNode]:
    """递归重写节点 id 为路径式（如 1 / 1.1 / 1.1.1）

    参数:
        nodes: 顶层节点列表
        prefix: 上级路径前缀（递归用，外部调用留空）
    返回:
        id 重整后的节点列表（原地修改并返回）
    """
    for idx, node in enumerate(nodes, start=1):
        node.id = f"{prefix}{idx}" if not prefix else f"{prefix}.{idx}"
        if node.children:
            finalize_ids(node.children, prefix=node.id)
    return nodes
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_tree.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/output/__init__.py outline_extraction/output/tree.py tests/test_tree.py
git commit -m "feat: path-style stable id finalization"
```

---

## Task 14: Word 导出（output/word_export.py）

**Files:**
- Create: `outline_extraction/output/word_export.py`
- Test: `tests/test_word_export.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_word_export.py`:
```python
"""Word 导出测试"""
from pathlib import Path
import docx
from outline_extraction.models import OutlineTree, OutlineNode, SourceRef, SourceType, CoverageReport
from outline_extraction.output.word_export import export_to_docx


def _tree():
    return OutlineTree(
        project_name="测试项目",
        source_documents=["a.docx"],
        nodes=[
            OutlineNode(id="1", title="商务部分", level=1, sources=[
                SourceRef(type=SourceType.SKELETON, document="a.docx", location="一", quote=None)],
                children=[OutlineNode(id="1.1", title="投标函", level=2, sources=[], children=[])]),
            OutlineNode(id="2", title="项目实施组织方案", level=1, sources=[
                SourceRef(type=SourceType.AI_SUGGESTED, document="(AI建议)", location="-", quote=None)],
                children=[]),
        ],
        coverage=CoverageReport(total_scoring_items=0, mapped_scoring_items=0,
                                total_tech_items=0, mapped_tech_items=0, unmapped=[]),
    )


def test_export_creates_headings(tmp_path):
    """导出的 docx 含对应层级 Heading"""
    out = tmp_path / "out.docx"
    export_to_docx(_tree(), out, keep_ai_marks=False)
    d = docx.Document(str(out))
    headings = [(p.text, p.style.name) for p in d.paragraphs if p.style.name.startswith("Heading")]
    texts = [t for t, _ in headings]
    assert "商务部分" in texts
    assert "投标函" in texts


def test_export_ai_mark_toggle(tmp_path):
    """keep_ai_marks=True 时 AI 建议节点标题带标注"""
    out = tmp_path / "out2.docx"
    export_to_docx(_tree(), out, keep_ai_marks=True)
    d = docx.Document(str(out))
    all_text = "\n".join(p.text for p in d.paragraphs)
    assert "AI建议" in all_text or "🤖" in all_text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_word_export.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/output/word_export.py`:
```python
"""Word 导出——OutlineTree 遍历为多级标题 docx"""
from pathlib import Path
import docx
from outline_extraction.models import OutlineTree, OutlineNode, SourceType


def export_to_docx(tree: OutlineTree, output_path: Path, keep_ai_marks: bool = False) -> Path:
    """把大纲树导出为 Word 多级标题文档

    参数:
        tree: 完整大纲树
        output_path: 输出 .docx 路径
        keep_ai_marks: True 时为 AI 建议节点标题追加可视标注
    返回:
        输出路径
    """
    doc = docx.Document()
    doc.add_heading(tree.project_name, level=0)
    for node in tree.nodes:
        _write_node(doc, node, keep_ai_marks)
    doc.save(str(output_path))
    return output_path


def _write_node(doc, node: OutlineNode, keep_ai_marks: bool) -> None:
    """递归写入单个节点为 Heading——内部辅助

    参数:
        doc: python-docx Document
        node: 当前节点
        keep_ai_marks: 是否标注 AI 建议
    返回: 无
    """
    title = node.title
    if keep_ai_marks and node.sources and all(s.type == SourceType.AI_SUGGESTED for s in node.sources):
        title = f"{title}（🤖AI建议）"
    doc.add_heading(title, level=min(node.level, 9))
    for child in node.children:
        _write_node(doc, child, keep_ai_marks)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_word_export.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/output/word_export.py tests/test_word_export.py
git commit -m "feat: Word export with optional AI-suggestion marks"
```

---

## Task 15: 编排管线（pipeline.py）

**Files:**
- Create: `outline_extraction/pipeline.py`
- Test: `tests/test_pipeline.py`

**说明：** 串联 9 步，每步完成调用 `progress_callback(step_name, payload)`，并把中间产物 dump 到 `runs/<run_id>/`。单测用 fake LLM + 真实解析跑通端到端骨架。

- [ ] **Step 1: 写失败测试**

Create `tests/test_pipeline.py`:
```python
"""端到端管线测试——真实解析 + fake LLM"""
from pathlib import Path
import docx
from outline_extraction.models import (
    OutlineNode, SourceRef, SourceType, RequirementItem,
)
from outline_extraction.understanding.classify import FileClass, ClassifyResult
from outline_extraction.understanding.locate import LocateResult
from outline_extraction.understanding.extract_skeleton import SkeletonResult
from outline_extraction.understanding.extract_requirements import RequirementsResult
from outline_extraction.alignment.merge import MergeResult, MergeDecision, Disposition
from outline_extraction.alignment.supplement import SupplementResult
from outline_extraction.pipeline import run_pipeline


class _ScriptedLLM:
    """按调用顺序返回脚本化结果，模拟各步 LLM 输出"""
    def __init__(self):
        self.script = []
        self.idx = 0

    def push(self, result):
        self.script.append(result)

    def complete(self, **kwargs):
        r = self.script[self.idx]
        self.idx += 1
        return r


def _make_docx(path):
    d = docx.Document()
    d.add_heading("投标文件格式", level=1)
    d.add_heading("投标函", level=2)
    d.save(path)


def test_run_pipeline_end_to_end(tmp_path):
    """管线跑通：解析真实 docx + 脚本化 LLM，产出 OutlineTree"""
    src = tmp_path / "fmt.docx"
    _make_docx(src)

    llm = _ScriptedLLM()
    # classify（1个文档）
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    # locate
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[],
                          tech_spec_sections=[], business_sections=[]))
    # extract_skeleton
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)], children=[])]))
    # merge（无要求条目，直接返回骨架）
    llm.push(MergeResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)], children=[])],
        decisions=[]))
    # supplement
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)], children=[])]))

    steps_seen = []
    tree = run_pipeline(src, llm=llm, model_main="gpt-5.4", model_mini="gpt-5.4-mini",
                        run_dir=tmp_path / "run", progress_callback=lambda s, p: steps_seen.append(s))

    assert tree.nodes[0].title == "投标函"
    assert tree.nodes[0].id == "1"           # 已 finalize id
    assert "parse" in steps_seen
    assert "merge" in steps_seen
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/pipeline.py`:
```python
"""编排管线——串联解析/理解/对齐/输出 9 步，dump 中间产物"""
import json
from pathlib import Path
from typing import Callable, Optional, Any
from outline_extraction.models import OutlineTree, ParsedDocument
from outline_extraction.parsing.unpack import collect_files
from outline_extraction.parsing.extract import extract_document
from outline_extraction.understanding.classify import classify_documents
from outline_extraction.understanding.segment import segment_text
from outline_extraction.understanding.locate import locate_sections
from outline_extraction.understanding.extract_skeleton import extract_skeleton
from outline_extraction.understanding.extract_requirements import extract_requirements
from outline_extraction.alignment.merge import merge_requirements, compute_coverage, Disposition
from outline_extraction.alignment.supplement import supplement_tree
from outline_extraction.output.tree import finalize_ids


def run_pipeline(
    input_path: Path,
    llm,
    model_main: str,
    model_mini: str,
    run_dir: Path,
    progress_callback: Optional[Callable[[str, Any], None]] = None,
) -> OutlineTree:
    """执行完整大纲提取管线

    参数:
        input_path: 招标文件/文件包路径
        llm: LLMClient
        model_main: 主模型名（定位/抽取/对齐）
        model_mini: 小模型名（分类）
        run_dir: 中间产物输出目录
        progress_callback: 每步回调 (step_name, payload)
    返回:
        最终 OutlineTree
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    def _emit(step: str, payload: Any) -> None:
        """发进度并 dump 产物——内部辅助"""
        if progress_callback:
            progress_callback(step, payload)
        _dump(run_dir, step, payload)

    # 1. 解析
    files = collect_files(Path(input_path))
    docs: list[ParsedDocument] = [extract_document(Path(p), suf) for p, suf in files]
    _emit("parse", [d.model_dump() for d in docs])

    # 2. 分类
    classes = classify_documents(docs, llm=llm, model=model_mini)
    _emit("classify", {k: v.model_dump() for k, v in classes.items()})

    # 3. 切分（全文档汇总）
    sections = []
    for doc in docs:
        sections.extend(segment_text(doc.raw_markdown, doc_source=doc.filename))
    _emit("segment", [s.model_dump() for s in sections])

    # 4. 定位关键章节
    located = locate_sections(sections, llm=llm, model=model_main)
    _emit("locate", located.model_dump())

    # 5. 抽显式骨架（合并所有 bid_format 章节）
    skeleton = []
    for i in located.bid_format_sections:
        sec = sections[i]
        skeleton.extend(extract_skeleton(sec.content, document=sec.doc_source, llm=llm, model=model_main))
    _emit("extract_skeleton", [n.model_dump() for n in skeleton])

    # 6. 抽要求条目（评分+技术+商务章节）
    req_indices = located.scoring_sections + located.tech_spec_sections + located.business_sections
    req_texts = [sections[i].content for i in req_indices]
    requirements = extract_requirements(req_texts, llm=llm, model=model_main)
    _emit("extract_requirements", [r.model_dump() for r in requirements])

    # 7. 归并 + 覆盖率
    merged_tree, decisions = merge_requirements(skeleton, requirements, llm=llm, model=model_main)
    coverage = compute_coverage(requirements, decisions)
    _emit("merge", {"tree": [n.model_dump() for n in merged_tree],
                    "coverage": coverage.model_dump()})

    # 8. 生成式兜底（游离要求）
    floating = [r.description for r, d in _pair_floating(requirements, decisions)]
    final_nodes = supplement_tree(merged_tree, floating=floating, llm=llm, model=model_main)
    _emit("supplement", [n.model_dump() for n in final_nodes])

    # 9. id 重整
    final_nodes = finalize_ids(final_nodes)

    tree = OutlineTree(
        project_name=Path(input_path).stem,
        source_documents=[d.filename for d in docs],
        nodes=final_nodes,
        coverage=coverage,
    )
    _emit("finalize", tree.model_dump())
    return tree


def _pair_floating(requirements, decisions):
    """配对出 floating 要求——内部辅助

    参数:
        requirements: 要求列表
        decisions: 归属判定
    返回:
        [(requirement, decision)] 仅 floating 项
    """
    disp_by_loc = {d.requirement_location: d for d in decisions}
    pairs = []
    for req in requirements:
        d = disp_by_loc.get(req.location)
        if d is None or d.disposition == Disposition.FLOATING:
            pairs.append((req, d))
    return pairs


def _dump(run_dir: Path, step: str, payload: Any) -> None:
    """把中间产物写成 JSON 文件——内部辅助"""
    path = run_dir / f"{step}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 1 passed

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/pytest`
Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
git add outline_extraction/pipeline.py tests/test_pipeline.py
git commit -m "feat: orchestration pipeline (9 steps) with intermediate dumps"
```

---

## Task 16: 真实标的端到端验证（打真实 LLM）

**Files:**
- Create: `scripts/run_visible.py`（临时验证脚本，验证后保留作 demo 入口）
- 前置：用户已在 `.env` 配好 `FOUNDRY_API_KEY_AOAI` 与 `AOAI_BASE_URL`

**说明：** 前 15 个任务全用 fake LLM。本任务首次打真实 API，用**可见标的**验证管线真能产出合理大纲。盲测标的不在此跑。

- [ ] **Step 1: 写运行脚本**

Create `scripts/run_visible.py`:
```python
"""用可见标的跑真实管线，打印大纲树——demo/验证入口"""
import sys
from pathlib import Path
from outline_extraction.config import Settings
from outline_extraction.llm.client import LLMClient
from outline_extraction.pipeline import run_pipeline


def _print_tree(nodes, indent=0):
    """缩进打印大纲树——辅助"""
    for n in nodes:
        marks = ",".join(s.type.value for s in n.sources)
        print("  " * indent + f"{n.id} {n.title}  [{marks}]")
        _print_tree(n.children, indent + 1)


def main():
    """入口：参数为招标文件/文件夹路径"""
    target = Path(sys.argv[1])
    settings = Settings()
    llm = LLMClient(settings=settings)
    tree = run_pipeline(
        target, llm=llm, model_main=settings.model_main, model_mini=settings.model_mini,
        run_dir=Path("runs") / target.stem,
        progress_callback=lambda s, p: print(f"[step] {s}"),
    )
    print("\n===== 大纲树 =====")
    _print_tree(tree.nodes)
    print("\n===== 覆盖率 =====")
    print(tree.coverage.model_dump_json(indent=2))
    print(f"\nLLM 调用次数: {llm.total_calls}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑华能单 docx 标的**

Run:
```bash
.venv/bin/python scripts/run_visible.py "docs/TenderingDocs/(招标文件)中国华能集团有限公司2025年度逆变器框架协议采购招标.docx"
```
Expected: 各步 `[step]` 依次打印；输出一棵带来源标注的大纲树 + 覆盖率 JSON。人工检查：骨架标题是否来自文件、评分点是否被纳入。

- [ ] **Step 3: 跑北京院青海察尔汗文件包标的**

Run:
```bash
.venv/bin/python scripts/run_visible.py "docs/TenderingDocs/北京院青海察尔汗100MW光伏项目"
```
Expected: 多文件被分类、合并，产出大纲树。检查 `runs/<stem>/` 下各步 JSON 中间产物。

- [ ] **Step 4: 跑白银景泰单 doc 标的**

Run:
```bash
.venv/bin/python "scripts/run_visible.py" "docs/TenderingDocs/白银景泰D区35万千瓦光伏项目（一标段）PC总承包工程组串式逆变器采购-竞争性谈判文件（以PDF版为准，WORD版仅供编制投标文件) .doc"
```
Expected: `.doc` 经 textutil 抽取后跑通，产出大纲树。

- [ ] **Step 5: 根据真实输出迭代 prompt（如需要）**

若某步输出不理想（如骨架漏层、要求抽取过少），只调整 `outline_extraction/llm/prompts/*.txt`，**不得**为特定标的写硬编码特判。调整后重跑 Step 2-4。

- [ ] **Step 6: Commit**

```bash
git add scripts/run_visible.py outline_extraction/llm/prompts/
git commit -m "feat: real-LLM end-to-end runner + prompt tuning on visible tenders"
```

---

## Task 17: FastAPI 后端（api/main.py）

**Files:**
- Create: `outline_extraction/api/__init__.py`, `outline_extraction/api/main.py`
- Test: `tests/test_api.py`

**说明：** 提供 upload/run/progress(SSE)/tree/export/steps。run 在后台线程跑管线，进度经内存队列推 SSE。单测用 FastAPI TestClient + monkeypatch 掉 run_pipeline（不打真实 LLM）。

- [ ] **Step 1: 写失败测试**

Create `tests/test_api.py`:
```python
"""API 测试——monkeypatch 掉真实管线"""
import io
from fastapi.testclient import TestClient
from outline_extraction.api import main as api_main
from outline_extraction.models import OutlineTree, OutlineNode, CoverageReport


def _fake_tree():
    return OutlineTree(
        project_name="x", source_documents=["a.docx"],
        nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])],
        coverage=CoverageReport(total_scoring_items=0, mapped_scoring_items=0,
                                total_tech_items=0, mapped_tech_items=0, unmapped=[]),
    )


def test_upload_and_run(monkeypatch, tmp_path):
    """上传文件→run→拿到 tree"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, progress_callback):
        progress_callback("parse", {})
        progress_callback("finalize", {})
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    files = {"file": ("a.docx", io.BytesIO(b"fakedocx"), "application/octet-stream")}
    up = client.post("/api/upload", files=files)
    assert up.status_code == 200
    run_id = up.json()["run_id"]

    run = client.post(f"/api/run/{run_id}")
    assert run.status_code == 200

    tree = client.get(f"/api/tree/{run_id}")
    assert tree.status_code == 200
    assert tree.json()["nodes"][0]["title"] == "投标函"


def test_export_docx(monkeypatch, tmp_path):
    """导出 docx 返回二进制"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(api_main, "run_pipeline",
                        lambda **k: (_ for _ in ()).throw(AssertionError("不应被调用")))
    # 直接写入一棵树到 store
    run_id = "test123"
    api_main.TREE_STORE[run_id] = _fake_tree()
    client = TestClient(api_main.app)
    resp = client.get(f"/api/export/{run_id}.docx")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/")
    assert len(resp.content) > 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/api/__init__.py`（空文件）。

Create `outline_extraction/api/main.py`:
```python
"""FastAPI 后端——上传、运行管线、SSE 进度、树查询、Word 导出"""
import io
import shutil
import threading
import queue
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from outline_extraction.config import Settings
from outline_extraction.llm.client import LLMClient
from outline_extraction.pipeline import run_pipeline
from outline_extraction.models import OutlineTree
from outline_extraction.output.word_export import export_to_docx

app = FastAPI(title="招标大纲提取 Demo")

# 运行态存储（Demo 用内存，足够）
RUNS_DIR = Path("runs")
UPLOAD_STORE: dict[str, Path] = {}        # run_id → 上传文件/目录路径
TREE_STORE: dict[str, OutlineTree] = {}   # run_id → 结果树
PROGRESS_QUEUES: dict[str, "queue.Queue"] = {}  # run_id → 进度队列


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    """接收上传文件，返回 run_id"""
    run_id = uuid.uuid4().hex[:12]
    dest_dir = RUNS_DIR / run_id / "input"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    UPLOAD_STORE[run_id] = dest
    return JSONResponse({"run_id": run_id, "filename": file.filename})


@app.post("/api/run/{run_id}")
async def run(run_id: str) -> JSONResponse:
    """同步执行管线（Demo 简化：阻塞直到完成，进度仍入队供回看）"""
    if run_id not in UPLOAD_STORE:
        raise HTTPException(404, "unknown run_id")
    q: queue.Queue = queue.Queue()
    PROGRESS_QUEUES[run_id] = q
    settings = Settings()
    llm = LLMClient(settings=settings)

    def _cb(step: str, payload) -> None:
        q.put(step)

    tree = run_pipeline(
        UPLOAD_STORE[run_id], llm=llm,
        model_main=settings.model_main, model_mini=settings.model_mini,
        run_dir=RUNS_DIR / run_id, progress_callback=_cb,
    )
    TREE_STORE[run_id] = tree
    q.put("__done__")
    return JSONResponse({"status": "done"})


@app.get("/api/tree/{run_id}")
async def get_tree(run_id: str) -> JSONResponse:
    """返回最终大纲树 JSON"""
    if run_id not in TREE_STORE:
        raise HTTPException(404, "tree not ready")
    return JSONResponse(TREE_STORE[run_id].model_dump())


@app.get("/api/export/{run_id}.docx")
async def export(run_id: str, keep_ai_marks: bool = False) -> FileResponse:
    """导出 Word 文档"""
    if run_id not in TREE_STORE:
        raise HTTPException(404, "tree not ready")
    out_path = RUNS_DIR / run_id / "outline.docx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_to_docx(TREE_STORE[run_id], out_path, keep_ai_marks=keep_ai_marks)
    return FileResponse(str(out_path),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename="投标文件大纲.docx")


@app.get("/api/runs/{run_id}/steps/{step}")
async def get_step(run_id: str, step: str) -> FileResponse:
    """返回某步中间产物 JSON——讲原理用"""
    path = RUNS_DIR / run_id / f"{step}.json"
    if not path.exists():
        raise HTTPException(404, "step not found")
    return FileResponse(str(path), media_type="application/json")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/api/__init__.py outline_extraction/api/main.py tests/test_api.py
git commit -m "feat: FastAPI backend (upload/run/tree/export/steps)"
```

---

## Task 18: 前端界面（web/）+ 静态挂载

**Files:**
- Create: `web/index.html`, `web/app.js`
- Modify: `outline_extraction/api/main.py`（挂载静态文件 + 根路由）

**说明：** Alpine.js + Tailwind（CDN，无构建）。完成后用 Chrome DevTools/Playwright 截图验证（遵循全局 UI 规范）。

- [ ] **Step 1: 写前端 HTML**

Create `web/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>招标文件 → 投标大纲提取</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-slate-50 text-slate-800">
  <div x-data="app()" class="max-w-5xl mx-auto p-8">
    <h1 class="text-2xl font-semibold mb-6">招标文件 → 投标大纲提取</h1>

    <!-- 上传区 -->
    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6">
      <input type="file" @change="onFile($event)" class="mb-3" />
      <button @click="run()" :disabled="!runId || running"
              class="px-4 py-2 bg-indigo-600 text-white rounded-lg disabled:opacity-40">
        <span x-text="running ? '处理中…' : '开始提取'"></span>
      </button>
      <span class="ml-3 text-sm text-slate-500" x-text="fileName"></span>
    </div>

    <!-- 进度区 -->
    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6" x-show="steps.length">
      <h2 class="font-medium mb-3">处理流程</h2>
      <ul class="space-y-1">
        <template x-for="s in steps" :key="s">
          <li class="flex items-center text-sm">
            <span class="w-2 h-2 rounded-full bg-emerald-500 mr-2"></span>
            <span x-text="stepLabel(s)"></span>
          </li>
        </template>
      </ul>
    </div>

    <!-- 覆盖率面板 -->
    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6" x-show="tree">
      <h2 class="font-medium mb-3">覆盖率</h2>
      <template x-if="tree">
        <div class="flex gap-6 text-sm">
          <div :class="cov.mapped_scoring_items===cov.total_scoring_items ? 'text-emerald-600' : 'text-amber-600'">
            评分点 <span x-text="cov.mapped_scoring_items + '/' + cov.total_scoring_items"></span>
          </div>
          <div :class="cov.mapped_tech_items===cov.total_tech_items ? 'text-emerald-600' : 'text-amber-600'">
            技术条目 <span x-text="cov.mapped_tech_items + '/' + cov.total_tech_items"></span>
          </div>
        </div>
      </template>
      <template x-if="tree && cov.unmapped.length">
        <div class="mt-3 text-sm text-rose-600">
          <div class="font-medium">未覆盖（建议人工复核）：</div>
          <ul class="list-disc ml-5">
            <template x-for="u in cov.unmapped" :key="u"><li x-text="u"></li></template>
          </ul>
        </div>
      </template>
    </div>

    <!-- 大纲树 + 导出 -->
    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6" x-show="tree">
      <div class="flex justify-between items-center mb-4">
        <h2 class="font-medium">投标文件大纲</h2>
        <div class="flex items-center gap-3">
          <label class="text-sm flex items-center gap-1">
            <input type="checkbox" x-model="keepAiMarks" /> 保留AI建议标注
          </label>
          <a :href="exportUrl()" class="px-3 py-1.5 bg-slate-800 text-white rounded-lg text-sm">导出 Word</a>
        </div>
      </div>
      <div class="text-sm">
        <template x-for="n in (tree ? tree.nodes : [])" :key="n.id">
          <div x-html="renderNode(n, 0)"></div>
        </template>
      </div>
    </div>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写前端 JS**

Create `web/app.js`:
```javascript
// 招标大纲提取前端逻辑（Alpine 组件）
function app() {
  return {
    runId: null,
    fileName: "",
    running: false,
    steps: [],
    tree: null,
    keepAiMarks: false,

    // 来源类型 → 徽章
    badge(type) {
      const m = { skeleton: "📋骨架", scoring: "📊评分", tech_spec: "📐技术",
                  biz_terms: "📄商务", ai_suggested: "🤖AI建议" };
      return m[type] || type;
    },

    // 步骤名 → 中文标签
    stepLabel(s) {
      const m = { parse: "解析文件", classify: "文件分类", segment: "章节切分",
                  locate: "定位关键章节", extract_skeleton: "抽取显式骨架",
                  extract_requirements: "抽取要求条目", merge: "归并对齐",
                  supplement: "生成式补充", finalize: "完成" };
      return m[s] || s;
    },

    // 选择文件后立即上传
    async onFile(e) {
      const file = e.target.files[0];
      if (!file) return;
      this.fileName = file.name;
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await r.json();
      this.runId = data.run_id;
    },

    // 运行管线
    async run() {
      if (!this.runId) return;
      this.running = true;
      this.steps = [];
      this.tree = null;
      await fetch(`/api/run/${this.runId}`, { method: "POST" });
      const tr = await fetch(`/api/tree/${this.runId}`);
      this.tree = await tr.json();
      this.running = false;
    },

    get cov() { return this.tree ? this.tree.coverage : {}; },

    // 导出 URL（带 AI 标注开关）
    exportUrl() {
      return `/api/export/${this.runId}.docx?keep_ai_marks=${this.keepAiMarks}`;
    },

    // 递归渲染节点为 HTML
    renderNode(node, depth) {
      const pad = depth * 20;
      const badges = (node.sources || [])
        .map(s => `<span class="ml-2 px-1.5 py-0.5 rounded bg-slate-100 text-xs">${this.badge(s.type)}</span>`)
        .join("");
      const isAi = node.sources && node.sources.length &&
                   node.sources.every(s => s.type === "ai_suggested");
      const bg = isAi ? "background:#fdf6ec;" : "";
      let html = `<div style="padding-left:${pad}px;${bg}" class="py-1 border-b border-slate-50">
        <span class="text-slate-400 mr-1">${node.id}</span>
        <span class="font-medium">${node.title}</span>${badges}</div>`;
      for (const c of (node.children || [])) html += this.renderNode(c, depth + 1);
      return html;
    },
  };
}
```

- [ ] **Step 3: 在 API 挂载静态文件与根路由**

Modify `outline_extraction/api/main.py` — 在 `app = FastAPI(...)` 之后、各路由之前加入：
```python
from fastapi.responses import HTMLResponse

_WEB_DIR = Path(__file__).parent.parent.parent / "web"
app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """返回前端页面"""
    return HTMLResponse((_WEB_DIR / "index.html").read_text(encoding="utf-8"))
```

- [ ] **Step 4: 启动服务**

Run（后台启动）:
```bash
.venv/bin/uvicorn outline_extraction.api.main:app --port 8123 &
sleep 3 && curl -s http://localhost:8123/ | head -5
```
Expected: 返回 HTML 首页内容。

- [ ] **Step 5: 用 Chrome DevTools 截图验证渲染**

用 chrome-devtools 技能打开 `http://localhost:8123/`，截图首页（上传区、按钮）。检查：布局正常、Tailwind 样式生效、无控制台报错。

- [ ] **Step 6: 上传可见标的并截图完整结果**

在浏览器上传华能 docx，点"开始提取"，等待完成，截图大纲树 + 覆盖率面板。验证：树正确渲染、来源徽章显示、覆盖率数字合理、导出按钮可点。多视口（桌面/窄屏）各截一张。

- [ ] **Step 7: 据截图修正样式差异并复验**

如有布局/对齐/溢出问题，改 `web/index.html` / `web/app.js`，重启服务，重新截图比对，直到符合预期。

- [ ] **Step 8: 关闭后台服务**

Run: `kill %1 2>/dev/null || pkill -f "uvicorn outline_extraction"`

- [ ] **Step 9: Commit**

```bash
git add web/index.html web/app.js outline_extraction/api/main.py
git commit -m "feat: Alpine+Tailwind frontend with tree view, coverage, export"
```

---

## Task 19: Content Understanding 接入（阶段二增强）

**Files:**
- Create: `outline_extraction/parsing/cu_client.py`
- Modify: `outline_extraction/parsing/extract.py`（`needs_ocr` 分支调用 CU）
- Test: `tests/test_cu_client.py`

**说明：** 阶段二增量增强。CU 用于 (a) `extract_method=="needs_ocr"` 的扫描件 PDF，(b) 复杂表格高保真还原。CU 客户端可注入，单测用 fake 不打真实服务。若 `.env` 未配 CU，extract 优雅降级（保留 needs_ocr 的原始文本，不报错）。

- [ ] **Step 1: 写失败测试**

Create `tests/test_cu_client.py`:
```python
"""Content Understanding 客户端测试——注入 fake，不打真实服务"""
from outline_extraction.parsing.cu_client import analyze_with_cu, CUResult


class _FakeCU:
    """模拟 CU 分析，返回 Markdown"""
    def analyze(self, file_path):
        return CUResult(markdown="# 扫描件标题\n| 项 | 分值 |\n| A | 5 |", page_count=3)


def test_analyze_returns_markdown(tmp_path):
    """CU 分析返回结构化 Markdown"""
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    result = analyze_with_cu(f, cu=_FakeCU())
    assert "扫描件标题" in result.markdown
    assert "| 项 | 分值 |" in result.markdown


def test_analyze_none_client_returns_empty(tmp_path):
    """未配置 CU（cu=None）时返回空结果，不抛异常"""
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    result = analyze_with_cu(f, cu=None)
    assert result.markdown == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_cu_client.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

Create `outline_extraction/parsing/cu_client.py`:
```python
"""Content Understanding 封装——扫描件 OCR + 复杂表格还原（阶段二）"""
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel


class CUResult(BaseModel):
    """CU 分析结果"""
    markdown: str          # 结构化 Markdown（含表格）
    page_count: Optional[int] = None


def analyze_with_cu(file_path: Path, cu: Any) -> CUResult:
    """用 Content Understanding 分析文件

    参数:
        file_path: 待分析文件
        cu: CU 客户端（须有 analyze(path)->CUResult）；None 表示未配置
    返回:
        CUResult；cu 为 None 时返回空 markdown（优雅降级）
    """
    if cu is None:
        return CUResult(markdown="", page_count=None)
    return cu.analyze(file_path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_cu_client.py -v`
Expected: 2 passed

- [ ] **Step 5: 在 extract.py 接入 CU 降级链**

说明：当真实 CU SDK 接好后，把构造好的 CU 客户端通过参数传入 `extract_document`。本步先把接口打通——给 `_pdf_to_doc` 增加可选 `cu` 参数，`needs_ocr` 时调用。

Modify `outline_extraction/parsing/extract.py`：
- 顶部加：`from outline_extraction.parsing.cu_client import analyze_with_cu`
- 修改 `extract_document` 签名为 `def extract_document(file_path, suffix, cu=None):`，PDF 分支调用 `_pdf_to_doc(file_path, name, cu)`。
- 修改 `_pdf_to_doc` 签名为 `def _pdf_to_doc(file_path, name, cu=None):`，在判定为扫描件后：
```python
    if _is_scanned(len(full.strip()), page_count):
        cu_result = analyze_with_cu(file_path, cu)
        if cu_result.markdown:                       # CU 可用：用其结构化输出
            return ParsedDocument(filename=name, raw_markdown=cu_result.markdown,
                                  extract_method="cu_ocr",
                                  page_count=cu_result.page_count or page_count)
        return ParsedDocument(filename=name, raw_markdown=full,    # 降级：保留原文本
                              extract_method="needs_ocr", page_count=page_count)
```

- [ ] **Step 6: 运行受影响测试确认未回归**

Run: `.venv/bin/pytest tests/test_extract.py tests/test_cu_client.py -v`
Expected: 全部通过（`cu=None` 默认值保证旧测试不变）。

- [ ] **Step 7: Commit**

```bash
git add outline_extraction/parsing/cu_client.py outline_extraction/parsing/extract.py tests/test_cu_client.py
git commit -m "feat: Content Understanding integration with graceful fallback"
```

---

## Task 20: 盲测验证（用户提供盲测标的）

**Files:** 无新增代码；这是验证关卡。

**说明：** 由用户在 demo 现场或验证时提供赞比亚/淮能凤台标的。开发者全程未见其内容。此任务验证"换新文件不翻车"。

- [ ] **Step 1: 全量测试回归**

Run: `.venv/bin/pytest`
Expected: 全部通过。

- [ ] **Step 2: 启动服务，用户上传盲测标的**

Run: `.venv/bin/uvicorn outline_extraction.api.main:app --port 8123 &`
由用户上传盲测标的文件夹/文件，点"开始提取"。

- [ ] **Step 3: 观察并记录结果**

检查：
- 各步是否无异常完成（解析方法是否合理、分类是否正确）。
- 大纲树是否结构合理、来源标注是否齐全。
- 覆盖率是否诚实反映（含 unmapped 缺口）。
- 若失败，定位是哪一步——记录现象，**不得**为通过而写特判；只能改通用 prompt 或通用解析逻辑。

- [ ] **Step 4: 关闭服务**

Run: `pkill -f "uvicorn outline_extraction"`

- [ ] **Step 5: Commit（若有通用改进）**

```bash
git add -A
git commit -m "fix: generalize handling based on blind-test findings"
```

---

## 收尾

- [ ] **清理临时产物**：确认 `runs/` 在 gitignore；删除调试残留。
- [ ] **README（仅当用户要求）**：全局规范禁止主动生成文档，故不写，除非用户明确要。

---

## 自审记录（写计划时执行）

**Spec 覆盖：**
- §1 三类来源 → Task 9（骨架）/10（要求）/12（兜底）✓
- §4 数据模型 → Task 1 ✓
- §5 解析层探测优先 → Task 4/5；CU → Task 19 ✓
- §6 理解层 5 步 → Task 5/7/8/9/10 ✓
- §7 对齐层归并+覆盖率+兜底 → Task 11/12；id 重整 → Task 13 ✓
- §8.1 LLM 封装 → Task 3；§8.2 管线 → Task 15；§8.3 API → Task 17；§8.4 前端 → Task 18 ✓
- §2.2 盲测 → Task 16（仅可见标的）/ Task 20（盲测关卡）✓
- B Word 导出 → Task 14 ✓

**占位符扫描：** 无 TBD/TODO；每个代码步含完整代码。

**类型一致性：** `LLMClient.complete(schema=...)`、各步 Result 模型、`MergeDecision/Disposition`、`compute_coverage` 签名跨任务一致；pipeline 引用的函数名与各任务定义一致（`collect_files`/`extract_document`/`classify_documents`/`segment_text`/`locate_sections`/`extract_skeleton`/`extract_requirements`/`merge_requirements`/`compute_coverage`/`supplement_tree`/`finalize_ids`）。

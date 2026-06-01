# 鲁棒性与体验修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复盲测暴露的覆盖率 0/0/0（要求抽取为空）与标题重复，并增强多文件上传与 Apple 风界面，全部以普适性为原则（不为单个文件写特判）。

**Architecture:** A 方案——修主链路的脆弱假设，不改"先定位再抽取"的两阶段架构。四组修复：①解析层表格就地保留；②segment 信任 docx 原生 `#` 标题；③locate 摘要加长+prompt 强化；④merge prompt 骨架去重。外加多文件上传（前后端）与前端 Apple 风重做。

**Tech Stack:** Python 3.14（`.venv`，`uv pip` 装依赖）、python-docx、Pydantic v2、FastAPI、Alpine.js + Tailwind（CDN）、pytest。

**贯穿约定：**
- 跑测试：`.venv/bin/pytest`，跑脚本：`PYTHONPATH=. .venv/bin/python ...`。
- commit 信息结尾加：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- **普适性铁律**：所有 prompt / 代码改动只描述通用方法，绝不出现针对"淮能/某具体文件/某章节号"的特判。
- **关联键链路勿破**：`pipeline` 第6步赋 `req.ref_id="R{idx}"` → merge 把 ref_id 填进 `SourceRef.ref_ids` → supplement 保留 → 第9步 `compute_coverage(requirements, final_nodes)` 用 `_collect_ref_ids(tree)` 反查。任何改动（尤其 merge 去重）不得丢 ref_ids。

---

## 通读发现的关键约束（实现时必须遵守）

1. **`_docx_to_md` 现状**（[extract.py:39-61](outline_extraction/parsing/extract.py#L39)）：先遍历 `d.paragraphs` 再遍历 `d.tables`，**表格被统一追加到文末**，与所属章节失联。这是 0/0 的首要根因。
2. **body 流式遍历已验证可行**：`d.element.body.iterchildren()` 按真实顺序返回 `<w:p>`/`<w:tbl>`，用 `qn('w:p')`/`qn('w:tbl')` 区分，`Paragraph(child, doc)` / `Table(child, doc)` 包装。段落与表格顺序正确。
3. **segment 表格行不被误判**：现有正则模式 7 `^\d+\.?\s` 要求数字后跟空白，故 `| ... |` 表格行不会被当标题。新逻辑必须保持这一点。
4. **多文件上传的副作用**：`UPLOAD_STORE[run_id]` 若改指 input **目录**，`run_pipeline` 里 `project_name = Path(input_path).stem` 会变成字面量 `"input"`。必须修正 project_name 来源。
5. **`extract_document` 调用未传 cu**（[pipeline.py 第1步](outline_extraction/pipeline.py)），cu 恒 None，表格还原纯靠 `_docx_to_md`——印证表格修复是关键。
6. **不改的**：`_gather_span`、`compute_coverage`、`merge.py` 代码本体（去重改 prompt）、`supplement.py`、`tree.py`、`word_export.py`、`llm/client.py`。

---

## 文件结构（改动地图）

| 文件 | 改什么 | 责任 |
|---|---|---|
| `outline_extraction/parsing/extract.py` | `_docx_to_md` 改为 body 流式遍历，表格就地 + 加表头分隔行 | 解析层：保留表格位置 |
| `outline_extraction/understanding/segment.py` | `segment_text`/`_match_level` 增加"有#则只认#"档 | 切分层：信任原生标题 |
| `outline_extraction/understanding/locate.py` | `_SUMMARY_CHARS` 200→450 | 定位层：摘要加长 |
| `outline_extraction/llm/prompts/locate.txt` | 加表格/深层卷册/正文特征提示 | 定位 prompt |
| `outline_extraction/llm/prompts/merge.txt` | 加骨架语义去重指令 | 归并 prompt |
| `outline_extraction/api/main.py` | `upload` 接收多文件存 input 目录；run 用目录；project_name 修正 | API：多文件 |
| `outline_extraction/pipeline.py` | `run_pipeline` 增加 `project_name` 可选参数 | 管线：项目名来源 |
| `web/index.html` | `<input multiple>` + 拖拽 + Apple 风重做 | 前端 |
| `web/app.js` | `onFile` 收集多文件 + 文件列表展示 | 前端 |
| `tests/test_extract.py` | 新增表格就地保留用例 | 测试 |
| `tests/test_segment.py` | 新增有#标题信任用例 | 测试 |
| `tests/test_api.py` | 多文件上传用例 | 测试 |

---

## Task 1: 解析层——表格就地保留（修复 #1 核心）

**Files:**
- Modify: `outline_extraction/parsing/extract.py`（`_docx_to_md`，当前 39-61 行）
- Test: `tests/test_extract.py`

**背景**：当前 `_docx_to_md` 先收所有段落、再把所有表格追加到文末。改为按 body 真实顺序遍历，表格留在原章节位置，并补 Markdown 表头分隔行（`| --- |`）使其成为合法表格。已验证 `d.element.body.iterchildren()` 可按序返回段落与表格。

- [ ] **Step 1: 写失败测试**

在 `tests/test_extract.py` 末尾追加：
```python
def test_docx_table_stays_in_place(tmp_path):
    """表格应保留在其所属段落之间，而非被甩到文末"""
    p = tmp_path / "t.docx"
    d = docx.Document()
    d.add_heading("评分办法", level=1)
    d.add_paragraph("评分标准如下：")
    tbl = d.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "评分项"; tbl.cell(0, 1).text = "分值"
    tbl.cell(1, 0).text = "ISO9001"; tbl.cell(1, 1).text = "2分"
    d.add_paragraph("以上为评分细则。")
    d.save(p)
    md = extract_document(Path(p), ".docx").raw_markdown
    lines = md.splitlines()
    # 表格行应出现在"评分标准如下："之后、"以上为评分细则。"之前
    idx_intro = next(i for i, l in enumerate(lines) if "评分标准如下" in l)
    idx_table = next(i for i, l in enumerate(lines) if "ISO9001" in l)
    idx_after = next(i for i, l in enumerate(lines) if "以上为评分细则" in l)
    assert idx_intro < idx_table < idx_after
    # 表格是合法 Markdown 表格（含表头分隔行）
    assert any(set(l.strip()) <= set("| -") and "-" in l for l in lines)


def test_docx_table_has_header_separator(tmp_path):
    """表格首行后应有 | --- | 分隔行"""
    p = tmp_path / "t2.docx"
    d = docx.Document()
    tbl = d.add_table(rows=2, cols=3)
    for c in range(3):
        tbl.cell(0, c).text = f"列{c}"
        tbl.cell(1, c).text = f"值{c}"
    d.save(p)
    md = extract_document(Path(p), ".docx").raw_markdown
    lines = [l for l in md.splitlines() if l.startswith("|")]
    assert len(lines) >= 3   # 表头 + 分隔行 + 至少一数据行
    assert "---" in lines[1]  # 第二行是分隔行
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_extract.py::test_docx_table_stays_in_place tests/test_extract.py::test_docx_table_has_header_separator -v`
Expected: FAIL（当前表格被追加到文末，顺序断言不成立；且无分隔行）

- [ ] **Step 3: 改写 `_docx_to_md`**

把 `outline_extraction/parsing/extract.py` 的 `_docx_to_md`（39-61 行）整体替换为：
```python
def _docx_to_md(file_path: Path) -> str:
    """docx → Markdown：按文档真实顺序遍历段落与表格——内部辅助

    段落 Heading 样式转 # 前缀；表格在其原始位置转 Markdown 表格（含表头分隔行），
    不再统一追加到文末，从而保住表格与所属章节的相邻关系（评分表/技术参数表常为表格）。

    参数:
        file_path: docx 文件路径
    返回:
        统一 Markdown 文本
    """
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(file_path))
    lines: list[str] = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            para = Paragraph(child, doc)
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
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            lines.extend(_table_to_md(table))
    return "\n".join(lines)


def _table_to_md(table) -> list[str]:
    """把一个 docx 表格转成 Markdown 表格行（含表头分隔行）——内部辅助

    参数:
        table: python-docx Table 对象
    返回:
        Markdown 表格行列表；空表返回空列表
    """
    rows = table.rows
    if not rows:
        return []
    md_rows: list[str] = []
    for r_idx, row in enumerate(rows):
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        md_rows.append("| " + " | ".join(cells) + " |")
        if r_idx == 0:  # 首行后插入表头分隔行
            md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return md_rows
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_extract.py -v`
Expected: 全部 passed（含 2 个新测试 + 原有 4 个）

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/parsing/extract.py tests/test_extract.py
git commit -m "fix: keep docx tables in document order with header separators

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 切分层——信任 docx 原生 # 标题（修复 #1）

**Files:**
- Modify: `outline_extraction/understanding/segment.py`（`segment_text`，当前 17-47 行）
- Test: `tests/test_segment.py`

**背景**：当文档含 docx 转出的 `#` 标题时，应只用 `#` 作标题来源，避免正则把正文（如"1. 投标价格…"、表格行）误判为标题、压乱层级。无 `#` 的纯文本（textutil 抽的 .doc）退回现有正则。

- [ ] **Step 1: 写失败测试**

在 `tests/test_segment.py` 末尾追加：
```python
def test_segment_trusts_markdown_headings_when_present():
    """含 # 标题时，正文里的“1. xxx”不应被误判为标题"""
    md = "# 第一章 投标须知\n1. 投标价格应完整填写。\n2. 投标有效期为90天。\n## 1、资格要求\n须满足资质。"
    sections = segment_text(md, doc_source="x.docx")
    titles = [s.title for s in sections]
    # # 与 ## 是标题
    assert any(t == "# 第一章 投标须知" for t in titles)
    assert any(t == "## 1、资格要求" for t in titles)
    # “1. 投标价格…”“2. 投标有效期…”是正文，不应成为独立 Section 标题
    assert not any(t.startswith("1. 投标价格") for t in titles)
    assert not any(t.startswith("2. 投标有效期") for t in titles)
    # 正文挂到“第一章”下
    ch1 = next(s for s in sections if s.title == "# 第一章 投标须知")
    assert "投标价格应完整填写" in ch1.content


def test_segment_table_rows_not_titles_with_headings():
    """含 # 标题时，Markdown 表格行应作为正文，不被当标题"""
    md = "# 评分办法\n| 评分项 | 分值 |\n| --- | --- |\n| ISO9001 | 2分 |"
    sections = segment_text(md, doc_source="x.docx")
    titles = [s.title for s in sections]
    assert titles == ["# 评分办法"]   # 只有一个标题
    body = sections[0].content
    assert "ISO9001" in body and "评分项" in body


def test_segment_falls_back_to_regex_without_headings():
    """无 # 标题的纯文本仍走正则兜底（不回退此能力）"""
    md = "第一章 总则\n正文A\n一、 适用范围\n正文B"
    sections = segment_text(md, doc_source="x.doc")
    titles = [(s.title, s.level) for s in sections]
    assert ("第一章 总则", 1) in titles
    assert any(t.startswith("一、") and lvl == 2 for t, lvl in titles)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_segment.py::test_segment_trusts_markdown_headings_when_present tests/test_segment.py::test_segment_table_rows_not_titles_with_headings -v`
Expected: FAIL（当前正则会把"1. 投标价格…"当成 level-1 标题）

- [ ] **Step 3: 改写 `segment_text`**

把 `outline_extraction/understanding/segment.py` 的 `segment_text`（17-47 行）整体替换为：
```python
def segment_text(markdown: str, doc_source: str) -> list[Section]:
    """把文本按编号切成带层级的章节块

    优先信任 docx 原生 Markdown 标题：若全文存在以 # 开头的标题行，则只用 # 作为标题
    来源（# 数量即层级），其余行一律视为正文——避免正则把正文/表格行误判为标题。
    若全文无 # 标题（如 textutil 抽取的纯文本 .doc），退回正则编号识别。

    参数:
        markdown: 文档的 Markdown 文本
        doc_source: 来源文件名
    返回:
        Section 列表；无法匹配任何标题时返回单个 level1 整篇块
    """
    lines = markdown.splitlines()
    has_md_heading = any(line.lstrip().startswith("#") and _md_heading_level(line.lstrip()) for line in lines)

    sections: list[Section] = []
    current: Section | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if has_md_heading:
            # 信任原生标题档：仅 # 行作标题，其余皆正文
            level = _md_heading_level(stripped)
        else:
            # 正则兜底档：沿用编号模式
            level = _match_level(stripped)
        if level is not None:
            current = Section(title=stripped, level=level, content="", doc_source=doc_source)
            sections.append(current)
        elif current is not None:
            current.content += stripped + "\n"
        else:
            current = Section(title="（前言）", level=1, content=stripped + "\n", doc_source=doc_source)
            sections.append(current)

    if not sections:
        sections.append(Section(title="（全文）", level=1, content=markdown, doc_source=doc_source))
    return sections


def _md_heading_level(line: str) -> int | None:
    """若该行是 Markdown 标题（# 开头且 # 后有空格），返回层级，否则 None——内部辅助

    参数:
        line: 已 strip 的行文本
    返回:
        层级（# 个数，封顶 6）或 None
    """
    if not line.startswith("#"):
        return None
    hashes = len(line) - len(line.lstrip("#"))
    rest = line[hashes:]
    if hashes >= 1 and rest.startswith(" "):
        return min(hashes, 6)
    return None
```

保留现有 `_match_level` 与 `_PATTERNS` 不变（兜底档仍用）。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_segment.py -v`
Expected: 全部 passed（含 3 个新测试 + 原有 4 个；原 `test_segment_chapter_and_subsection` 等用无 # 文本，走兜底档仍通过）

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/understanding/segment.py tests/test_segment.py
git commit -m "fix: segment trusts native docx headings, avoids misclassifying body text

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 定位层——摘要加长 + prompt 强化（修复 #1）

**Files:**
- Modify: `outline_extraction/understanding/locate.py`（`_SUMMARY_CHARS`，第 8 行）
- Modify: `outline_extraction/llm/prompts/locate.txt`

**背景**：locate 只看 200 字摘要，漏定位藏在表格/深层卷册里的技术评分内容。加长摘要 + prompt 提示按正文特征判断。纯 prompt/常量改动，无独立单测（行为靠盲测验证），仅确保不破坏现有 `test_locate.py`。

- [ ] **Step 1: 加长摘要常量**

把 `outline_extraction/understanding/locate.py` 第 8 行：
```python
_SUMMARY_CHARS = 200
```
改为：
```python
_SUMMARY_CHARS = 450  # 加长摘要，让 LLM 看到评分项/技术参数/表格等内容特征，减少漏定位
```

- [ ] **Step 2: 强化 locate prompt**

把 `outline_extraction/llm/prompts/locate.txt` 整体替换为：
```
你是招标文件结构分析助手。给定一份招标文件包中所有章节的标题列表（含所属文件名与正文摘要），请定位以下四类关键章节分别出现在哪些章节中（可能在不同文件、可能多处、也可能缺失）：
- bid_format_sections: 规定投标文件应包含哪些内容/格式的章节（如"投标文件格式""投标文件组成""投标文件编制"）
- scoring_sections: 评分办法/评标标准/评审因素章节
- tech_spec_sections: 技术规范/技术要求/技术参数章节
- business_sections: 商务条款/合同条款/商务要求章节

判别要点（依据语义与内容特征，不要只看标题、不要依赖固定关键词或编号）：
- 关键内容常以表格形式出现（摘要里会看到 | 分隔的表格行），或藏在"技术部分""第二卷""技术规范书"等卷册/附件之下，标题未必含明显关键词。
- 当摘要中出现"得分/分值/评分因素/权重"等 → 很可能是 scoring。
- 当摘要中出现"技术参数/性能指标/≥或≤的指标/偏离表/技术响应"等 → 很可能是 tech_spec。
- 当摘要中出现"付款/交货/质保/合同条款/违约"等 → 很可能是 business。
- 一类内容若分散在多个章节，应返回全部相关索引；确实没有则返回空列表。

每类返回匹配到的章节索引列表（对应输入顺序，从0开始）。
```

- [ ] **Step 3: 确认现有 locate 测试不破**

Run: `.venv/bin/pytest tests/test_locate.py -v`
Expected: passed（test_locate.py 用 fake LLM，不依赖摘要长度/prompt 文本，应仍通过）

- [ ] **Step 4: Commit**

```bash
git add outline_extraction/understanding/locate.py outline_extraction/llm/prompts/locate.txt
git commit -m "fix: locate uses longer summaries + content-feature hints to reduce misses

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 归并层——骨架语义去重（修复 #2）

**Files:**
- Modify: `outline_extraction/llm/prompts/merge.txt`

**背景**：同一投标文件结构多处出现 → 平铺多份。在 merge prompt 加去重指令，且**强调合并时把被合并节点的 ref_ids 并入保留节点**（保护覆盖率关联键）。纯 prompt 改动；现有 `test_merge_coverage.py` 用 fake LLM 不读 prompt，应不破。

- [ ] **Step 1: 在 merge.txt 增加去重段落**

读取 `outline_extraction/llm/prompts/merge.txt`，在"语义判同示例"那一段之后、"返回："之前，插入以下段落：
```
关于骨架去重（务必遵守）：
- 骨架树中可能存在多个语义等价的章节（例如多处“商务投标文件/投标函”、同一“技术投标文件”在不同位置重复出现）。请把它们合并为一个节点，保留信息最完整的一份，删除重复的标题，不要在最终树里平铺多份相同含义的章节。
- 合并节点时，必须把被合并节点的所有来源（sources）与其 ref_ids 一并归入保留的那个节点，不得因合并而丢失任何 ref_id。
- 合并依据语义判同（与上面的判同示例同理），不针对具体词语。
```

- [ ] **Step 2: 确认现有 merge 测试不破**

Run: `.venv/bin/pytest tests/test_merge_coverage.py -v`
Expected: passed（fake LLM 不读 prompt）

- [ ] **Step 3: Commit**

```bash
git add outline_extraction/llm/prompts/merge.txt
git commit -m "fix: merge prompt deduplicates semantically-equivalent skeleton nodes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 多文件上传——后端（修复 #4）

**Files:**
- Modify: `outline_extraction/api/main.py`（`upload` 与 `run`）
- Modify: `outline_extraction/pipeline.py`（`run_pipeline` 增加 `project_name` 参数）
- Test: `tests/test_api.py`

**背景**：当前 `/api/upload` 只收单文件、`UPLOAD_STORE[run_id]` 指单文件。改为接收多文件、全存 `runs/<id>/input/`、`UPLOAD_STORE` 指 input 目录。`collect_files` 已支持目录遍历。**关键副作用修正**：`run_pipeline` 用 `Path(input_path).stem` 作 project_name，传目录会得到 `"input"`，故给 `run_pipeline` 增加可选 `project_name`，API 传上传文件名（多文件时取公共名/首个文件名 stem）。

- [ ] **Step 1: 给 run_pipeline 增加 project_name 参数（写失败测试）**

先看现有 `tests/test_pipeline.py` 的 `run_pipeline` 调用方式，在其末尾追加测试：
```python
def test_run_pipeline_accepts_explicit_project_name(tmp_path):
    """run_pipeline 可显式指定 project_name，覆盖默认的 input_path.stem"""
    src = tmp_path / "input"
    src.mkdir()
    f = src / "fmt.docx"
    import docx
    d = docx.Document()
    d.add_heading("投标文件格式", level=1)
    d.save(f)

    from outline_extraction.understanding.classify import FileClass, ClassifyResult
    from outline_extraction.understanding.locate import LocateResult
    from outline_extraction.understanding.extract_skeleton import SkeletonResult
    from outline_extraction.alignment.merge import MergeResult
    from outline_extraction.alignment.supplement import SupplementResult
    from outline_extraction.models import OutlineNode

    class _ScriptedLLM:
        def __init__(self):
            self.script = []
            self.idx = 0
        def push(self, r):
            self.script.append(r)
        def complete(self, **kwargs):
            r = self.script[self.idx]; self.idx += 1; return r

    llm = _ScriptedLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    llm.push(MergeResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])], decisions=[]))
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    from outline_extraction.pipeline import run_pipeline
    tree = run_pipeline(src, llm=llm, model_main="m", model_mini="mini",
                        run_dir=tmp_path / "run", project_name="淮能项目")
    assert tree.project_name == "淮能项目"   # 不是 "input"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_pipeline.py::test_run_pipeline_accepts_explicit_project_name -v`
Expected: FAIL（`run_pipeline` 还没有 `project_name` 参数 → TypeError）

- [ ] **Step 3: 给 run_pipeline 增加 project_name**

在 `outline_extraction/pipeline.py` 的 `run_pipeline` 签名增加可选参数（加在 `log_callback` 之后）：
```python
def run_pipeline(
    input_path: Path,
    llm,
    model_main: str,
    model_mini: str,
    run_dir: Path,
    progress_callback: Optional[Callable[[str, Any], None]] = None,
    log_callback: Optional[Callable[[dict], None]] = None,
    project_name: Optional[str] = None,
) -> OutlineTree:
```
更新 docstring 增加一行：`project_name: 显式项目名；缺省用 input_path.stem`。
然后把构造 `OutlineTree` 处的 `project_name=Path(input_path).stem` 改为：
```python
        project_name=project_name or Path(input_path).stem,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 全部 passed

- [ ] **Step 5: 写多文件上传的失败测试**

在 `tests/test_api.py` 末尾追加：
```python
def test_upload_multiple_files_stores_dir(monkeypatch, tmp_path):
    """上传多个文件应全部存入 input 目录，UPLOAD_STORE 指向该目录"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    client = TestClient(api_main.app)
    files = [
        ("files", ("tech.docx", io.BytesIO(b"t"), "application/octet-stream")),
        ("files", ("biz.docx", io.BytesIO(b"b"), "application/octet-stream")),
    ]
    up = client.post("/api/upload", files=files)
    assert up.status_code == 200
    run_id = up.json()["run_id"]
    stored = api_main.UPLOAD_STORE[run_id]
    assert stored.is_dir()
    names = sorted(p.name for p in stored.iterdir())
    assert names == ["biz.docx", "tech.docx"]
    assert up.json()["filenames"] == ["tech.docx", "biz.docx"]
```

- [ ] **Step 6: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_api.py::test_upload_multiple_files_stores_dir -v`
Expected: FAIL（当前 upload 是单文件 `file` 参数）

- [ ] **Step 7: 改写 upload 端点 + run 传 project_name**

在 `outline_extraction/api/main.py`：
- 顶部 imports 增加 `List`：`from typing import List`（若已 import typing 则合并）。
- 把 `upload` 端点替换为接收多文件：
```python
@app.post("/api/upload")
async def upload(files: List[UploadFile] = File(...)) -> JSONResponse:
    """接收一个或多个文件，全部存入 input 目录，返回 run_id 与文件名列表"""
    run_id = uuid.uuid4().hex[:12]
    dest_dir = RUNS_DIR / run_id / "input"
    dest_dir.mkdir(parents=True, exist_ok=True)
    filenames: list[str] = []
    for f in files:
        dest = dest_dir / f.filename
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        filenames.append(f.filename)
    UPLOAD_STORE[run_id] = dest_dir       # 指向 input 目录（支持单/多文件）
    return JSONResponse({"run_id": run_id, "filenames": filenames})
```
- 在 `run` 端点的 `_worker` 内，给 `run_pipeline` 传 `project_name`（用目录里第一个文件名的 stem，多文件时用目录所在 run 的可读名）。把 worker 里的 `run_pipeline(...)` 调用改为：
```python
            input_dir = UPLOAD_STORE[run_id]
            names = sorted(p.name for p in input_dir.iterdir()) if input_dir.is_dir() else [input_dir.name]
            proj = Path(names[0]).stem if names else run_id
            tree = run_pipeline(
                input_dir, llm=llm,
                model_main=settings.model_main, model_mini=settings.model_mini,
                run_dir=RUNS_DIR / run_id, log_callback=_log_cb, project_name=proj,
            )
```

- [ ] **Step 8: 运行 API 测试确认通过**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: 全部 passed（含新多文件测试 + 原有 3 个；注意原 `test_upload_and_run` 用单文件字段 `file=` 上传——需同步改为 `files=` 字段，见 Step 9）

- [ ] **Step 9: 修原有单文件测试以适配新字段**

原 `test_upload_and_run` 和 `test_progress_sse_streams_phase_events` 用 `files={"file": (...)}`。FastAPI 多文件端点字段名变为 `files`，把这两个测试里的上传改为列表形式：
```python
    files = [("files", ("a.docx", io.BytesIO(b"fakedocx"), "application/octet-stream"))]
    up = client.post("/api/upload", files=files)
```
（其余断言不变；`fake_run` 的签名已是 `log_callback`，若新增 `project_name` 参数需在 fake 里接受 `**kwargs` 或加该形参——确保 fake_run 兼容 `project_name`。把两个 fake_run 的签名改为 `def fake_run(input_path, llm, model_main, model_mini, run_dir, log_callback, project_name=None):`）

- [ ] **Step 10: 全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全部 passed

- [ ] **Step 11: Commit**

```bash
git add outline_extraction/api/main.py outline_extraction/pipeline.py tests/test_api.py tests/test_pipeline.py
git commit -m "feat: multi-file upload stored as input dir; explicit project_name

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 前端——多选上传 + Apple 风重做（修复 #3 + #4）

**Files:**
- Modify: `web/index.html`（整体视觉重做 + `<input multiple>` + 拖拽）
- Modify: `web/app.js`（`onFile` 收集多文件 + 文件列表展示）

**背景**：前端改 Apple 风（极简、留白、中性灰 + 单一强调色、系统字体、大圆角轻阴影），并支持多文件。数据流不变。完成后用 Chrome DevTools 截图验证。

- [ ] **Step 1: 改 app.js 支持多文件**

把 `web/app.js` 的状态 `fileName: ""` 改为 `fileNames: []`，并替换 `onFile`：
```javascript
    // 选择文件后立即上传（支持多文件）
    async onFile(e) {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      this.fileNames = files.map(f => f.name);
      const fd = new FormData();
      files.forEach(f => fd.append("files", f));   // 字段名 files，与后端一致
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await r.json();
      this.runId = data.run_id;
    },
```
（若 `index.html` 里别处引用 `fileName`，同步改为 `fileNames.join(", ")`。）

- [ ] **Step 2: 重做 index.html（Apple 风 + 多选）**

把 `web/index.html` 整体替换为下方内容（保留 Alpine/Tailwind CDN、保留时间线/覆盖率/大纲树的数据绑定逻辑，只改视觉与上传控件）：
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>招标文件 → 投标大纲提取</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "PingFang SC", sans-serif; }
  </style>
</head>
<body class="bg-neutral-50 text-neutral-800 antialiased">
  <div x-data="app()" class="max-w-3xl mx-auto px-6 py-16">
    <!-- 标题 -->
    <header class="mb-12">
      <h1 class="text-3xl font-semibold tracking-tight text-neutral-900">投标大纲提取</h1>
      <p class="mt-2 text-neutral-500">上传招标文件，自动生成结构化投标文件大纲。</p>
    </header>

    <!-- 上传区 -->
    <div class="mb-8">
      <label class="block border border-dashed border-neutral-300 rounded-2xl bg-white px-8 py-10 text-center cursor-pointer hover:border-neutral-400 transition-colors">
        <input type="file" multiple class="hidden" @change="onFile($event)" />
        <div class="text-neutral-700 font-medium">选择文件或拖拽到此处</div>
        <div class="text-sm text-neutral-400 mt-1">支持 docx / doc / pdf，可多选（文件包）</div>
        <template x-if="fileNames.length">
          <div class="mt-4 text-sm text-neutral-600 space-y-1">
            <template x-for="n in fileNames" :key="n"><div x-text="n"></div></template>
          </div>
        </template>
      </label>
      <button @click="run()" :disabled="!runId || running"
              class="mt-5 w-full sm:w-auto px-6 py-2.5 rounded-full bg-neutral-900 text-white text-sm font-medium disabled:opacity-30 hover:bg-neutral-700 transition-colors">
        <span x-text="running ? '处理中…' : '开始提取'"></span>
      </button>
    </div>

    <!-- 错误 -->
    <div class="mb-8 rounded-2xl bg-red-50 text-red-600 px-5 py-4 text-sm" x-show="errorMsg" x-text="errorMsg"></div>

    <!-- 处理流程时间线 -->
    <section class="mb-8 rounded-2xl bg-white border border-neutral-100 p-6" x-show="phases.length">
      <h2 class="text-sm font-semibold text-neutral-400 uppercase tracking-wide mb-5">处理流程</h2>
      <ol class="space-y-1">
        <template x-for="(p, i) in phases" :key="p.key">
          <li>
            <div class="flex items-center px-2 py-2 rounded-xl transition-colors"
                 :class="p.status === 'running' ? 'bg-neutral-50' : ''">
              <span class="w-5 h-5 mr-3 flex items-center justify-center shrink-0">
                <template x-if="p.status === 'done'">
                  <span class="w-4 h-4 rounded-full bg-neutral-900 text-white text-[10px] flex items-center justify-center">✓</span>
                </template>
                <template x-if="p.status === 'running'">
                  <span class="w-4 h-4 rounded-full border-2 border-neutral-900 border-t-transparent animate-spin"></span>
                </template>
                <template x-if="p.status === 'pending'">
                  <span class="w-1.5 h-1.5 rounded-full bg-neutral-300"></span>
                </template>
              </span>
              <span class="text-sm"
                    :class="p.status === 'running' ? 'font-semibold text-neutral-900' : (p.status === 'done' ? 'text-neutral-600' : 'text-neutral-300')"
                    x-text="(i + 1) + '. ' + p.label"></span>
            </div>
            <template x-for="line in p.logs" :key="line">
              <div class="ml-10 text-xs text-neutral-400 py-0.5" x-text="line"></div>
            </template>
          </li>
        </template>
      </ol>
    </section>

    <!-- 覆盖率 -->
    <section class="mb-8 rounded-2xl bg-white border border-neutral-100 p-6" x-show="tree">
      <h2 class="text-sm font-semibold text-neutral-400 uppercase tracking-wide mb-4">覆盖率</h2>
      <template x-if="tree">
        <div class="flex flex-wrap gap-8 text-sm">
          <div>
            <div class="text-neutral-400 text-xs mb-1">评分点</div>
            <div :class="cov.mapped_scoring_items===cov.total_scoring_items ? 'text-neutral-900' : 'text-amber-600'"
                 class="text-lg font-medium" x-text="cov.mapped_scoring_items + ' / ' + cov.total_scoring_items"></div>
          </div>
          <div>
            <div class="text-neutral-400 text-xs mb-1">技术条目</div>
            <div :class="cov.mapped_tech_items===cov.total_tech_items ? 'text-neutral-900' : 'text-amber-600'"
                 class="text-lg font-medium" x-text="cov.mapped_tech_items + ' / ' + cov.total_tech_items"></div>
          </div>
          <div>
            <div class="text-neutral-400 text-xs mb-1">商务</div>
            <div :class="cov.mapped_biz_items===cov.total_biz_items ? 'text-neutral-900' : 'text-amber-600'"
                 class="text-lg font-medium" x-text="cov.mapped_biz_items + ' / ' + cov.total_biz_items"></div>
          </div>
        </div>
      </template>
      <template x-if="tree && cov.unmapped && cov.unmapped.length">
        <div class="mt-4 text-sm">
          <div class="text-amber-600 font-medium mb-1">未覆盖（建议人工复核）</div>
          <ul class="list-disc ml-5 text-neutral-500 space-y-0.5">
            <template x-for="u in cov.unmapped" :key="u"><li x-text="u"></li></template>
          </ul>
        </div>
      </template>
    </section>

    <!-- 大纲树 -->
    <section class="rounded-2xl bg-white border border-neutral-100 p-6" x-show="tree">
      <div class="flex justify-between items-center mb-5">
        <h2 class="text-sm font-semibold text-neutral-400 uppercase tracking-wide">投标文件大纲</h2>
        <div class="flex items-center gap-4">
          <label class="text-xs text-neutral-500 flex items-center gap-1.5">
            <input type="checkbox" x-model="keepAiMarks" class="rounded" /> 保留 AI 建议标注
          </label>
          <a :href="exportUrl()" class="px-4 py-1.5 rounded-full border border-neutral-300 text-neutral-700 text-xs font-medium hover:bg-neutral-50 transition-colors">导出 Word</a>
        </div>
      </div>
      <div class="text-sm leading-relaxed">
        <template x-for="n in (tree ? tree.nodes : [])" :key="n.id">
          <div x-html="renderNode(n, 0)"></div>
        </template>
      </div>
    </section>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: 调整 app.js 的 renderNode 配色为中性低饱和**

把 `web/app.js` 的 `renderNode` 替换为（徽章低饱和中性灰、AI 节点极浅背景）：
```javascript
    // 递归渲染节点为 HTML（Apple 风：低饱和、克制）
    renderNode(node, depth) {
      const pad = depth * 18;
      const types = [...new Set((node.sources || []).map(s => s.type))];
      const badges = types
        .map(t => `<span class="ml-2 px-1.5 py-0.5 rounded text-[11px] bg-neutral-100 text-neutral-500">${this.badge(t)}</span>`)
        .join("");
      const isAi = types.length === 1 && types[0] === "ai_suggested";
      const bg = isAi ? "background:#fafafa;" : "";
      let html = `<div style="padding-left:${pad}px;${bg}" class="py-1.5 border-b border-neutral-50">
        <span class="text-neutral-300 mr-2 text-xs">${node.id}</span>
        <span class="text-neutral-800">${node.title}</span>${badges}</div>`;
      for (const c of (node.children || [])) html += this.renderNode(c, depth + 1);
      return html;
    },
```

- [ ] **Step 4: 启动服务**

Run（后台）:
```bash
cd /Users/jiqingyou/Documents/Code/VSCode/Microsoft/Demo/Customers/Sungrow/OutlineExtraction
pkill -f "uvicorn outline_extraction" 2>/dev/null; sleep 1
PYTHONPATH=. .venv/bin/uvicorn outline_extraction.api.main:app --port 8131 > /tmp/uvicorn_outline.log 2>&1 &
sleep 4 && curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8131/
```
Expected: HTTP 200

- [ ] **Step 5: Chrome DevTools 截图验证（初始态 + 模拟运行态）**

用 chrome-devtools 打开 `http://localhost:8131/`，截初始页面（上传区 Apple 风）。再用 evaluate_script 注入 Alpine 组件模拟 phases/tree（参考既有验证手法），截"运行中"与"完成"两态。检查：极简留白、中性灰、单一强调（近黑）、大圆角、时间线高亮、覆盖率三栏、大纲树徽章低饱和。桌面（1440）+ 窄屏（390）各一张。

- [ ] **Step 6: 据截图修正样式差异**

如有对齐/溢出/配色过重问题，改 `web/index.html`/`web/app.js`，刷新重新截图，直到符合 Apple 风预期。

- [ ] **Step 7: 关闭服务**

Run: `pkill -f "uvicorn outline_extraction"`

- [ ] **Step 8: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: Apple-style minimal UI + multi-file upload (drag/multi-select)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Content Understanding 真正接入管线（修复 #5）

**Files:**
- Modify: `outline_extraction/parsing/cu_client.py`（真实现 CU REST 调用）
- Modify: `outline_extraction/parsing/extract.py`（`extract_document` 分流：docx 本地，其余走 CU）
- Modify: `outline_extraction/pipeline.py`（构造 CU 客户端并传入 `extract_document`）
- Modify: `requirements.txt`（加 `requests`）
- Test: `tests/test_cu_client.py`、`tests/test_extract.py`

**背景与已验证事实（实现时遵守，勿再猜）**：
- **教训**：CU 之前从未真正接入——`pipeline` 调 `extract_document` 不传 cu，cu 恒 None，全走纯文本兜底；单测全是 fake。本任务要让 CU 真被调用且可观测。
- **分流规则**：`.docx` → 本地抽取（已由 Task 1/2 处理）；**其余所有后缀（.doc/.pdf/.xml 等）→ CU**。CU 失败则降级回现有本地抽取（pdfplumber/textutil），不崩。
- **CU REST 已实测可用**（GA `2025-11-01`）：
  - `POST {endpoint}/contentunderstanding/analyzers/prebuilt-layout:analyzeBinary?api-version=2025-11-01`，header `Ocp-Apim-Subscription-Key`、`Content-Type: application/octet-stream`，body=文件字节 → 返回 202 + `Operation-Location` 头。
  - 轮询 `GET {Operation-Location}`（带 key 头），`status=="Succeeded"` 读 `result["contents"][0]["markdown"]`。
  - **实测确认**：CU **接受老 `.doc` 二进制**（白银景泰 .doc 785KB → 202 成功，markdown 77895 字、433 表格行）。
  - **analyzer 选型 = `prebuilt-layout`**（不是 documentSearch）。实测三种配置（documentSearch / layout 默认 / layout+returnDetails）对该 .doc 输出**完全一致**（md 77895 字、433 表格行、**0 个 `#` 标题**）。选 layout 的理由：它**不调底层 LLM 模型**（documentSearch 要调，做摘要/图表描述），更快更省，输出等价。
  - **实测重要真相**：CU 对老 .doc **不产出 `#` 标题层级**（0 个），即便 `returnDetails:true` 也不返回 sections/paragraphs。即 **CU 解决表格、但不产出 `#` 层级**。故走 CU 的文档在 segment 阶段会落到正则兜底档（Task 2 已保留）。本任务不强求 CU 补层级——.doc 层级增强（TOC 反推）是 spec §7 盲测后预案。
  - `endpoint`/`key` 来自 `Settings.cu_endpoint`/`cu_key`（`.env` 已配）。`requests` 已可用（`uv pip install requests` 已装，需补进 requirements.txt）。
- **可观测**：CU 路径的 `extract_method` 标为 `"cu"`，写入 `parse.json`，验证时肉眼可查。

- [ ] **Step 1: 把 requests 加入 requirements.txt**

在 `requirements.txt` 末尾追加一行：
```
requests>=2.31
```

- [ ] **Step 2: 写 cu_client 真实现的失败测试**

把 `tests/test_cu_client.py` 替换为（保留 fake 注入测分流，新增对真实 client 结构的单元测试，用 monkeypatch 掉 requests 不打网络）：
```python
"""Content Understanding 客户端测试——注入 fake/mock，不打真实服务"""
from outline_extraction.parsing.cu_client import analyze_with_cu, CUResult, CUClient


class _FakeCU:
    """模拟 CU 分析，返回 Markdown"""
    def analyze(self, file_path):
        return CUResult(markdown="# 扫描件标题\n| 项 | 分值 |\n| --- | --- |\n| A | 5 |", page_count=3)


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


def test_cuclient_analyze_polls_and_reads_markdown(tmp_path, monkeypatch):
    """CUClient.analyze：POST→拿 Operation-Location→轮询→读 markdown（mock requests）"""
    import outline_extraction.parsing.cu_client as cu_mod

    posted = {}

    class _Resp:
        def __init__(self, status_code=200, headers=None, payload=None):
            self.status_code = status_code
            self.headers = headers or {}
            self._payload = payload or {}
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")
        def json(self):
            return self._payload

    def fake_post(url, headers=None, data=None, timeout=None):
        posted["url"] = url
        posted["bytes"] = len(data) if data else 0
        return _Resp(202, {"Operation-Location": "https://x/op/123"})

    def fake_get(url, headers=None, timeout=None):
        return _Resp(200, {}, {"status": "Succeeded",
                               "result": {"contents": [{"markdown": "# 标题\n| a | b |\n| --- | --- |"}]}})

    monkeypatch.setattr(cu_mod.requests, "post", fake_post)
    monkeypatch.setattr(cu_mod.requests, "get", fake_get)

    f = tmp_path / "doc.doc"
    f.write_bytes(b"\xd0\xcf fake doc bytes")
    client = CUClient(endpoint="https://res.cognitiveservices.azure.com", key="k")
    out = client.analyze(f)
    assert "# 标题" in out.markdown
    assert "analyzeBinary" in posted["url"]
    assert posted["bytes"] > 0
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_cu_client.py::test_cuclient_analyze_polls_and_reads_markdown -v`
Expected: FAIL（`CUClient` 尚不存在 → ImportError）

- [ ] **Step 4: 实现 CUClient（真实 REST）**

把 `outline_extraction/parsing/cu_client.py` 替换为：
```python
"""Content Understanding 封装——扫描件/非 docx 文档的版面+表格还原（GA 2025-11-01）"""
import time
from pathlib import Path
from typing import Optional, Any
import requests
from pydantic import BaseModel

# CU REST 常量（已查证 Microsoft Learn，GA 版本）
_API_VERSION = "2025-11-01"
_ANALYZER_ID = "prebuilt-layout"   # 版面/表格还原预置分析器（不调 LLM，比 documentSearch 更省，输出等价）
_POLL_INTERVAL_S = 3
_POLL_MAX_TRIES = 80


class CUResult(BaseModel):
    """CU 分析结果"""
    markdown: str          # 结构化 Markdown（含表格）
    page_count: Optional[int] = None


class CUClient:
    """Azure AI Content Understanding REST 客户端

    参数:
        endpoint: 资源端点，如 https://<res>.cognitiveservices.azure.com
        key: 订阅密钥
    """
    def __init__(self, endpoint: str, key: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.key = key

    def analyze(self, file_path: Path) -> CUResult:
        """上传文件字节给 CU，轮询取结构化 markdown

        参数:
            file_path: 待分析文件
        返回:
            CUResult（含 markdown）；失败抛异常由调用方降级处理
        """
        with open(file_path, "rb") as f:
            data = f.read()
        url = (f"{self.endpoint}/contentunderstanding/analyzers/"
               f"{_ANALYZER_ID}:analyzeBinary?api-version={_API_VERSION}")
        resp = requests.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": self.key,
                     "Content-Type": "application/octet-stream"},
            data=data, timeout=120,
        )
        resp.raise_for_status()
        op_url = resp.headers["Operation-Location"]
        for _ in range(_POLL_MAX_TRIES):
            poll = requests.get(op_url, headers={"Ocp-Apim-Subscription-Key": self.key}, timeout=60)
            poll.raise_for_status()
            body = poll.json()
            status = body.get("status")
            if status == "Succeeded":
                contents = body["result"]["contents"]
                markdown = contents[0].get("markdown", "") if contents else ""
                return CUResult(markdown=markdown, page_count=None)
            if status in ("Failed", "Canceled"):
                raise RuntimeError(f"CU 分析 {status}: {body.get('error')}")
            time.sleep(_POLL_INTERVAL_S)
        raise RuntimeError("CU 分析轮询超时")


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


def build_cu_client(endpoint: str, key: str) -> Optional[CUClient]:
    """按配置构造 CU 客户端；endpoint/key 缺失则返回 None——内部辅助

    参数:
        endpoint: CU 端点
        key: CU 密钥
    返回:
        CUClient 或 None（未配置时，调用方走本地兜底）
    """
    if endpoint and key:
        return CUClient(endpoint=endpoint, key=key)
    return None
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/pytest tests/test_cu_client.py -v`
Expected: 3 passed

- [ ] **Step 6: extract_document 分流（写失败测试）**

在 `tests/test_extract.py` 末尾追加：
```python
def test_extract_docx_does_not_use_cu(tmp_path):
    """docx 走本地抽取，不调用 CU"""
    p = tmp_path / "a.docx"
    d = docx.Document()
    d.add_heading("第一章", level=1)
    d.save(p)

    class _BoomCU:
        def analyze(self, fp):
            raise AssertionError("docx 不应调用 CU")

    result = extract_document(Path(p), ".docx", cu=_BoomCU())
    assert result.extract_method == "docx"


def test_extract_doc_uses_cu_when_available(tmp_path):
    """.doc 走 CU，extract_method 标为 cu"""
    from outline_extraction.parsing.cu_client import CUResult
    p = tmp_path / "b.doc"
    p.write_bytes(b"\xd0\xcf fake")

    class _FakeCU:
        def analyze(self, fp):
            return CUResult(markdown="# 标题\n| a | b |\n| --- | --- |", page_count=None)

    result = extract_document(Path(p), ".doc", cu=_FakeCU())
    assert result.extract_method == "cu"
    assert "标题" in result.raw_markdown


def test_extract_doc_falls_back_when_cu_fails(tmp_path):
    """.doc 走 CU 但 CU 抛错 → 降级回 textutil（method=textutil 或 skipped，不崩）"""
    p = tmp_path / "c.doc"
    p.write_bytes(b"\xd0\xcf fake")

    class _BoomCU:
        def analyze(self, fp):
            raise RuntimeError("CU down")

    result = extract_document(Path(p), ".doc", cu=_BoomCU())
    # 不抛异常；降级路径产出 ParsedDocument（method 为 textutil 兜底）
    assert result.extract_method in ("textutil", "skipped")
```

- [ ] **Step 7: 运行测试确认失败**

Run: `.venv/bin/pytest tests/test_extract.py::test_extract_doc_uses_cu_when_available -v`
Expected: FAIL（当前 .doc 恒走 textutil，不看 cu）

- [ ] **Step 8: 改 extract_document 分流逻辑**

修改 `outline_extraction/parsing/extract.py` 的 `extract_document`（当前 14 行起）。把后缀分发逻辑改为：docx 本地；其余优先 CU（cu 可用时），CU 失败降级回原有本地逻辑。替换 `extract_document` 函数体为：
```python
def extract_document(file_path: Path, suffix: str, cu: Any = None) -> ParsedDocument:
    """按后缀分流抽取文本

    分流规则：.docx 走本地抽取（保留 Word 原生标题层级）；其余后缀优先用 CU
    出结构化 markdown，CU 不可用或失败时降级回本地（textutil/pdfplumber/xml）。

    参数:
        file_path: 文件路径
        suffix: 小写后缀
        cu: CU 客户端（None 表示未配置，走本地兜底）
    返回:
        ParsedDocument（含统一 Markdown 与抽取方式标记）
    """
    name = file_path.name
    if suffix == ".docx":
        return ParsedDocument(filename=name, raw_markdown=_docx_to_md(file_path),
                              extract_method="docx", page_count=None)
    # 其余后缀：优先 CU
    if cu is not None:
        try:
            cu_result = analyze_with_cu(file_path, cu)
            if cu_result.markdown.strip():
                return ParsedDocument(filename=name, raw_markdown=cu_result.markdown,
                                      extract_method="cu", page_count=cu_result.page_count)
        except Exception:
            pass  # CU 失败 → 降级本地，不让管线崩
    # 本地兜底
    if suffix == ".doc":
        return ParsedDocument(filename=name, raw_markdown=_doc_to_md(file_path),
                              extract_method="textutil", page_count=None)
    if suffix == ".pdf":
        return _pdf_to_doc(file_path, name)
    if suffix == ".xml":
        return ParsedDocument(filename=name, raw_markdown=file_path.read_text(errors="ignore"),
                              extract_method="xml", page_count=None)
    return ParsedDocument(filename=name, raw_markdown="", extract_method="skipped", page_count=None)
```
确保文件顶部已 `from outline_extraction.parsing.cu_client import analyze_with_cu`（若无则加；`Any` 来自 `typing`，确认已 import）。注意 `_pdf_to_doc` 内原有的 CU 调用（needs_ocr 分支）可保留或简化——本任务以 `extract_document` 层的分流为主，`_pdf_to_doc` 仅作 PDF 本地降级（pdfplumber 抽文本）。

- [ ] **Step 9: 运行 extract 测试确认通过**

Run: `.venv/bin/pytest tests/test_extract.py -v`
Expected: 全部 passed（含 3 个新 CU 分流测试 + Task 1 的表格测试 + 原有）

- [ ] **Step 10: pipeline 构造并传入 CU 客户端**

修改 `outline_extraction/pipeline.py`：
- 顶部 import：`from outline_extraction.parsing.cu_client import build_cu_client`
- `run_pipeline` 再加一个可选参数（在 `project_name` 之后）：`cu: Any = None`，docstring 加一行 `cu: CU 客户端，缺省 None（仅本地抽取）`。
- 第 1 步解析改为把 cu 传给 extract_document：
```python
    files = collect_files(Path(input_path))
    docs: list[ParsedDocument] = [extract_document(Path(p), suf, cu=cu) for p, suf in files]
```
- 注意：`run_pipeline` 不自己读 Settings 构造 cu（保持可测、可注入）；由调用方（API / run_visible）构造后传入。

- [ ] **Step 11: API 与 run_visible 构造 CU 客户端传入**

修改 `outline_extraction/api/main.py` 的 `run` 端点 `_worker` 内，构造 cu 并传入：
```python
            from outline_extraction.parsing.cu_client import build_cu_client
            cu = build_cu_client(settings.cu_endpoint, settings.cu_key)
            tree = run_pipeline(
                input_dir, llm=llm,
                model_main=settings.model_main, model_mini=settings.model_mini,
                run_dir=RUNS_DIR / run_id, log_callback=_log_cb, project_name=proj, cu=cu,
            )
```
修改 `scripts/run_visible.py` 的 `main()`，构造 cu 传入：
```python
    from outline_extraction.parsing.cu_client import build_cu_client
    cu = build_cu_client(settings.cu_endpoint, settings.cu_key)
    tree = run_pipeline(target, llm=llm, model_main=settings.model_main, model_mini=settings.model_mini,
                        run_dir=Path("runs") / target.stem,
                        progress_callback=lambda s, p: print(f"[step] {s}"), cu=cu)
```

- [ ] **Step 12: 全量单测回归**

Run: `.venv/bin/pytest -q`
Expected: 全部 passed

- [ ] **Step 13: 真打 CU 冒烟验证（消耗 token/CU，肉眼确认不旁路）**

Run（用一个含 .doc/.pdf 的真实标的，如山东高速含 pdf+doc）：
```bash
cd /Users/jiqingyou/Documents/Code/VSCode/Microsoft/Demo/Customers/Sungrow/OutlineExtraction
PYTHONPATH=. .venv/bin/python scripts/run_visible.py "docs/TenderingDocs/山东高速能源发展有限公司2025年度逆变器框架协议采购"
```
然后检查 parse.json 里 CU 是否真生效：
```bash
.venv/bin/python -c "
import json, glob
f = sorted(glob.glob('runs/*/parse.json'))[-1]
docs = json.load(open(f))
from collections import Counter
print('extract_method 分布:', Counter(d['extract_method'] for d in docs))
print('走 CU 的文件:', [d['filename'][:40] for d in docs if d['extract_method']=='cu'])
"
```
Expected（**通过标准 = 肉眼确认，不是绿灯**）：`extract_method` 分布里**出现 `cu`**（非 docx 文件走了 CU），docx 文件仍是 `docx`。若全无 `cu`，说明又旁路了，必须排查。

- [ ] **Step 14: Commit**

```bash
git add outline_extraction/parsing/cu_client.py outline_extraction/parsing/extract.py outline_extraction/pipeline.py outline_extraction/api/main.py scripts/run_visible.py requirements.txt tests/test_cu_client.py tests/test_extract.py
git commit -m "feat: wire Content Understanding into pipeline (docx local, others via CU)

CU 之前从未真正接入（pipeline 不传 cu、cu_client.analyze 无实现、单测全 fake），
真实运行全走纯文本兜底而无人察觉。本次：实现 CUClient REST 调用（GA 2025-11-01,
analyzeBinary 上传+轮询）；extract_document 分流——docx 走本地保留原生标题层级，
其余（.doc/.pdf/.xml）走 CU 出结构化 markdown（含表格），CU 失败降级本地；
pipeline/api/run_visible 构造并传入 cu。extract_method='cu' 可观测，附真打 CU 冒烟验证。
实测确认 CU 接受老 .doc 且表格还原良好。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: 回归 + 盲测验证（真实 LLM + CU，消耗 token）

**Files:** 无代码改动；验证关卡。

**背景**：A 方案 + CU 接入修完，必须验证 (a) 不破坏已跑通的北京院标的；(b) 淮能 0/0 是否解决、重复是否消除；(c) CU 真在为非 docx 文件工作。诚实记录结果——若仍有缺口，进入 §7 B 预案评估（不在本期改）。

- [ ] **Step 1: 全量单测回归**

Run: `.venv/bin/pytest -q`
Expected: 全部 passed

- [ ] **Step 2: 回归——重跑北京院标的（确认不退化）**

Run:
```bash
cd /Users/jiqingyou/Documents/Code/VSCode/Microsoft/Demo/Customers/Sungrow/OutlineExtraction
PYTHONPATH=. .venv/bin/python scripts/run_visible.py "docs/TenderingDocs/北京院青海察尔汗100MW光伏项目"
```
Expected: 各步正常完成；覆盖率仍合理（评分/技术/商务有数值、不回退为 0）；大纲树结构合理。记录覆盖率数字。

- [ ] **Step 3: 盲测——重跑淮能标的**

Run:
```bash
PYTHONPATH=. .venv/bin/python scripts/run_visible.py "docs/TenderingDocs/淮能电力凤台丁集矿采煤沉陷区二期光伏电站项目EPC总承包工程 储能系统 招标文件.docx"
```
（若该文件已被删除做盲测，由用户提供后再跑。）
Expected 检查点：
- `extract_requirements` 不再为空（评分/技术/商务有抽到要求，覆盖率不再 0/0/0）；
- 大纲树不再出现"商务投标文件"重复 3 次；
- 若仍 0 或仍重复，**如实记录现象**，定位是 segment/locate/merge 哪一环，不写特判。

- [ ] **Step 4: 抽查覆盖率真实性**

Run:
```bash
.venv/bin/python -c "
import json
D='runs/淮能电力凤台丁集矿采煤沉陷区二期光伏电站项目EPC总承包工程 储能系统 招标文件'
fin=json.load(open(D+'/finalize.json'))
reqs=json.load(open(D+'/extract_requirements.json'))
def collect(ns,acc):
    for n in ns:
        for s in n.get('sources',[]): acc.update(s.get('ref_ids',[]))
        collect(n.get('children',[]),acc)
t=set(); collect(fin['nodes'],t)
print('要求条数:',len(reqs),'| 树中 ref_id:',len(t),'| 覆盖率:',fin['coverage'])
"
```
Expected: 要求条数 > 0；树中 ref_id 与覆盖率自洽（参考之前北京院的核对手法）。

- [ ] **Step 5: 记录结论**

把回归 + 盲测结果（覆盖率数字、是否解决 0/0 与重复、若有残留缺口的现象）汇报给用户，由用户决定是否启用 §7 的 B 兜底预案。无代码 commit。

---

## 自审记录（写计划时执行）

**Spec 覆盖（对照 spec §2 范围表 4 项 + §8 验证）：**
- #1 要求抽取 0/0 → Task 1（表格就地）+ Task 2（segment 信任#）+ Task 3（locate 强化）✓
- #2 标题重复 → Task 4（merge 去重 prompt）✓
- #3 前端美化 → Task 6（Apple 风重做 + 截图验证）✓
- #4 多文件上传 → Task 5（后端）+ Task 6（前端多选）✓
- §8 验证（回归北京院 + 盲测淮能 + 抽查真实性）→ Task 7 ✓
- §7 B 兜底明确不做，Task 7 Step 5 留作按需评估 ✓

**占位符扫描：** 无 TBD/TODO；每个代码步含完整代码与确切命令。

**类型一致性：**
- `run_pipeline` 新增 `project_name` 参数在 Task 5 定义，API（Task 5 Step 7）与 fake（Task 5 Step 9）调用一致。
- upload 字段名 `files`（Task 5 后端）与前端 `fd.append("files", f)`（Task 6 Step 1）、测试 `("files", ...)`（Task 5 Step 5/9）一致。
- 前端状态 `fileName`→`fileNames`（Task 6 Step 1）与 index.html 引用（Task 6 Step 2 用 `fileNames`）一致。
- `_md_heading_level`（Task 2 新增）在 `segment_text` 与 `has_md_heading` 判定中一致使用。
- `_table_to_md`（Task 1 新增）被 `_docx_to_md` 调用，签名一致。

**关联键链路：** Task 4 去重 prompt 明确"合并时 ref_ids 并入保留节点"，保护 `req.ref_id → SourceRef.ref_ids → compute_coverage` 链路不破。

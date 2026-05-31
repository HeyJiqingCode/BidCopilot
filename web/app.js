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
      // 同类型来源去重，避免徽章重复堆叠
      const types = [...new Set((node.sources || []).map(s => s.type))];
      const badges = types
        .map(t => `<span class="ml-2 px-1.5 py-0.5 rounded bg-slate-100 text-xs">${this.badge(t)}</span>`)
        .join("");
      const isAi = types.length === 1 && types[0] === "ai_suggested";
      const bg = isAi ? "background:#fdf6ec;" : "";
      let html = `<div style="padding-left:${pad}px;${bg}" class="py-1 border-b border-slate-50">
        <span class="text-slate-400 mr-1">${node.id}</span>
        <span class="font-medium">${node.title}</span>${badges}</div>`;
      for (const c of (node.children || [])) html += this.renderNode(c, depth + 1);
      return html;
    },
  };
}

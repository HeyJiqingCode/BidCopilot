// 招标大纲提取前端逻辑（Alpine 组件）

// 9 阶段固定顺序与中文标签
const PHASE_DEFS = [
  { key: "parse", label: "解析文件" },
  { key: "classify", label: "文件分类" },
  { key: "segment", label: "章节切分" },
  { key: "locate", label: "定位关键章节" },
  { key: "extract_skeleton", label: "抽取显式骨架" },
  { key: "extract_requirements", label: "抽取要求条目" },
  { key: "merge", label: "归并对齐" },
  { key: "supplement", label: "生成式补充" },
  { key: "finalize", label: "完成" },
];

function app() {
  return {
    runId: null,
    fileNames: [],
    running: false,
    phases: [],        // [{key,label,status:'pending'|'running'|'done',logs:[]}]
    errorMsg: "",
    tree: null,
    keepAiMarks: false,

    // 初始化阶段时间线为全 pending——辅助
    initPhases() {
      this.phases = PHASE_DEFS.map(p => ({ key: p.key, label: p.label, status: "pending", logs: [] }));
    },

    // 来源类型 → 徽章
    badge(type) {
      const m = { skeleton: "📋骨架", scoring: "📊评分", tech_spec: "📐技术",
                  biz_terms: "📄商务", ai_suggested: "🤖AI建议" };
      return m[type] || type;
    },

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

    // 运行管线：启动后台执行，并用 SSE 实时接收阶段日志
    async run() {
      if (!this.runId) return;
      this.running = true;
      this.errorMsg = "";
      this.tree = null;
      this.initPhases();
      await fetch(`/api/run/${this.runId}`, { method: "POST" });

      const es = new EventSource(`/api/progress/${this.runId}`);
      es.onmessage = async (e) => {
        const ev = JSON.parse(e.data);
        if (ev.event === "done") {
          es.close();
          const tr = await fetch(`/api/tree/${this.runId}`);
          this.tree = await tr.json();
          this.running = false;
        } else if (ev.event === "error") {
          es.close();
          this.errorMsg = ev.message || "运行出错";
          this.running = false;
        } else {
          this.applyPhaseEvent(ev);
        }
      };
      es.onerror = () => { es.close(); this.running = false; };
    },

    // 应用一条阶段日志事件到时间线——辅助
    applyPhaseEvent(ev) {
      const p = this.phases.find(x => x.key === ev.phase);
      if (!p) return;
      if (ev.status === "start") {
        p.status = "running";
      } else if (ev.status === "done") {
        p.status = "done";
        if (ev.message) p.logs.push(ev.message);
      }
    },

    get cov() { return this.tree ? this.tree.coverage : {}; },

    // 导出 URL（带 AI 标注开关）
    exportUrl() {
      return `/api/export/${this.runId}.docx?keep_ai_marks=${this.keepAiMarks}`;
    },

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
  };
}

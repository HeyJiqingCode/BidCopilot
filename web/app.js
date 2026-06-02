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
    phases: [],
    errorMsg: "",
    tree: null,
    keepAiMarks: false,
    history: [],        // 历史 run 列表
    viewing: null,      // 正在回看的 run_id（null=新建/实时模式）
    expanded: {},       // {phaseKey: bool} 手动展开状态

    initPhases() {
      this.phases = PHASE_DEFS.map(p => ({ key: p.key, label: p.label, status: "pending", logs: [] }));
      this.expanded = {};
    },

    badge(type) {
      const m = { skeleton: "📋骨架", scoring: "📊评分", tech_spec: "📐技术",
                  biz_terms: "📄商务", ai_suggested: "🤖AI建议" };
      return m[type] || type;
    },

    // 来源类型 → 徽章配色类（功能色，低饱和）
    badgeClass(type) {
      const m = {
        skeleton: "bg-blue-50 text-blue-600",
        scoring: "bg-green-50 text-green-600",
        tech_spec: "bg-purple-50 text-purple-600",
        biz_terms: "bg-orange-50 text-orange-600",
        ai_suggested: "bg-neutral-100 text-neutral-500",
      };
      return m[type] || "bg-neutral-100 text-neutral-500";
    },

    async loadHistory() {
      try {
        const r = await fetch("/api/runs");
        this.history = await r.json();
      } catch (e) { this.history = []; }
    },

    async onFile(e) {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      this.fileNames = files.map(f => f.name);
      const fd = new FormData();
      files.forEach(f => fd.append("files", f));
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      this.runId = (await r.json()).run_id;
    },

    newRun() {
      this.viewing = null; this.runId = null; this.fileNames = [];
      this.tree = null; this.errorMsg = ""; this.phases = []; this.running = false;
    },

    async run() {
      if (!this.runId) return;
      this.viewing = null;
      this.running = true; this.errorMsg = ""; this.tree = null;
      this.initPhases();
      await fetch(`/api/run/${this.runId}`, { method: "POST" });
      const es = new EventSource(`/api/progress/${this.runId}`);
      es.onmessage = async (e) => {
        const ev = JSON.parse(e.data);
        if (ev.event === "done") {
          es.close();
          this.tree = await (await fetch(`/api/tree/${this.runId}`)).json();
          this.running = false;
          this.loadHistory();
        } else if (ev.event === "error") {
          es.close(); this.errorMsg = ev.message || "运行出错"; this.running = false;
        } else {
          this.applyPhaseEvent(ev);
        }
      };
      es.onerror = () => { es.close(); this.running = false; };
    },

    applyPhaseEvent(ev) {
      const p = this.phases.find(x => x.key === ev.phase);
      if (!p) return;
      if (ev.status === "start") {
        p.status = "running";
      } else if (ev.status === "done") {
        p.status = "done";
        if (ev.message) p.logs.push({ level: "main", text: ev.message });
      } else if (ev.status === "progress") {
        p.status = "running";
        if (ev.message) p.logs.push({ level: ev.level || "detail", text: ev.message });
      }
    },

    // 阶段日志窗是否展开：运行中自动开，完成后看手动状态
    isExpanded(p) {
      if (p.status === "running") return true;
      return !!this.expanded[p.key];
    },
    toggle(p) { this.expanded[p.key] = !this.expanded[p.key]; },

    // 点击历史项：回看模式，加载日志+树
    async openHistory(runId) {
      this.viewing = runId; this.running = false; this.errorMsg = "";
      this.initPhases();
      const events = await (await fetch(`/api/runs/${runId}/logs`)).json();
      events.forEach(ev => this.applyPhaseEvent(ev));
      this.phases.forEach(p => { if (p.logs.length) p.status = "done"; });
      this.tree = await (await fetch(`/api/tree/${runId}`)).json();
    },

    get cov() { return this.tree ? this.tree.coverage : {}; },
    exportUrl() { return `/api/export/${this.viewing || this.runId}.docx?keep_ai_marks=${this.keepAiMarks}`; },

    renderNode(node, depth) {
      const pad = depth * 18;
      const types = [...new Set((node.sources || []).map(s => s.type))];
      const badges = types
        .map(t => `<span class="ml-2 px-1.5 py-0.5 rounded text-[11px] ${this.badgeClass(t)}">${this.badge(t)}</span>`)
        .join("");
      const isAi = types.length === 1 && types[0] === "ai_suggested";
      const bg = isAi ? "background:#fafafa;" : "";
      let html = `<div style="padding-left:${pad}px;${bg}" class="py-1.5 border-b border-neutral-50">
        <span class="text-neutral-300 mr-2 text-xs">${node.id}</span>
        <span class="text-neutral-800">${node.title}</span>${badges}</div>`;
      for (const c of (node.children || [])) html += this.renderNode(c, depth + 1);
      return html;
    },

    init() { this.loadHistory(); },
  };
}

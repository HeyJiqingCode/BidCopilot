// 智能投标助手前端逻辑（Alpine 组件）

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
    fileNames: [],      // [{name, size}] 已选文件展示信息
    _files: [],         // 对应的原始 File 对象（删除某个后需重新上传）
    running: false,
    phases: [],
    errorMsg: "",
    tree: null,
    keepAiMarks: false,
    history: [],        // 历史 run 列表
    viewing: null,      // 正在回看的 run_id（null=新建/实时模式）
    expanded: {},       // {phaseKey: bool} 手动展开状态
    authEnabled: false, // 是否开启本地登录门（决定是否显示退出登录）
    sourceModal: null,  // 来源详情弹窗数据 {nodeId, title, groups:[{type,label,items:[{location,quote}]}]}
    _es: null,          // 当前 SSE 连接（切任务/新建前必须关，避免多个连接写同一 phases 致日志串台）
    _statusES: null,    // 全局运行态事件流（/api/events 常驻 SSE）：事件驱动刷新侧栏，替代定时轮询

    initPhases() {
      this.phases = PHASE_DEFS.map(p => ({ key: p.key, label: p.label, status: "pending", logs: [] }));
      this.expanded = {};
    },

    badge(type) {
      const m = { skeleton: "骨架", scoring: "评分", tech_spec: "技术",
                  biz_terms: "商务", ai_suggested: "AI建议" };
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

    // 来源类型 → 引用线边框色类（弹窗里引用风格的左竖线，呼应徽章配色）
    borderClass(type) {
      const m = {
        skeleton: "border-blue-200",
        scoring: "border-green-200",
        tech_spec: "border-purple-200",
        biz_terms: "border-orange-200",
        ai_suggested: "border-neutral-200",
      };
      return m[type] || "border-neutral-200";
    },

    // 从文件名提取大写扩展名（无扩展名返回 FILE）——供格式徽章显示
    fileExt(name) {
      const i = (name || "").lastIndexOf(".");
      return i >= 0 ? name.slice(i + 1).toUpperCase() : "FILE";
    },

    // 把字节数格式化为人类可读大小（B/KB/MB）——供文件卡片显示
    humanSize(bytes) {
      if (bytes === null || bytes === undefined) return "";
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
      return (bytes / 1024 / 1024).toFixed(1) + " MB";
    },

    async loadHistory() {
      try {
        const r = await fetch("/api/runs");
        this.history = await r.json();
      } catch (e) { this.history = []; }
    },

    // 订阅全局运行态事件流（/api/events，常驻 SSE）——事件驱动刷新侧栏，替代定时轮询。
    // 任一 run 状态变化（running/done/error）时后端广播，这里收到即重新拉一次 /api/runs，
    // 后台任务跑完也能自动从「运行中」移入「已完成」，无需刷新页面、也无空轮询。
    _listenStatusEvents() {
      if (this._statusES) return;            // 已订阅则不重复开
      const es = new EventSource("/api/events");
      this._statusES = es;
      es.onmessage = () => { this.loadHistory(); };   // 收到任意状态事件就刷新侧栏
      // 连接异常时浏览器会自动重连 EventSource，无需手动处理
    },

    // 运行中的 run（左侧栏「运行中」分组）
    get runningRuns() { return this.history.filter(h => h.status === "running"); },
    // 已完成的 run（左侧栏「已完成」分组）
    get doneRuns() { return this.history.filter(h => h.status !== "running"); },

    async onFile(e) {
      const picked = Array.from(e.target.files || []);
      if (!picked.length) return;
      // 留住 File 对象本身（删除某个后需重新构造上传），同时记录名字与大小
      this._files = picked;
      this.fileNames = picked.map(f => ({ name: f.name, size: f.size }));
      await this.uploadFiles();
    },

    // 把当前 this._files 上传到后端，刷新 runId——内部辅助
    async uploadFiles() {
      if (!this._files || !this._files.length) { this.runId = null; return; }
      const fd = new FormData();
      this._files.forEach(f => fd.append("files", f));
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      this.runId = (await r.json()).run_id;
    },

    // 移除已选列表中的第 idx 个文件，并以剩余文件重新上传
    async removeFile(idx) {
      this._files = (this._files || []).filter((_, i) => i !== idx);
      this.fileNames = this.fileNames.filter((_, i) => i !== idx);
      await this.uploadFiles();
    },

    newRun() {
      this._closeES();        // 关掉可能在跑的旧连接，避免新建后旧任务事件还往 phases 里写
      this.viewing = null; this.runId = null; this.fileNames = []; this._files = [];
      this.tree = null; this.errorMsg = ""; this.phases = []; this.running = false;
    },

    async run() {
      if (!this.runId || this.running) return;   // 防重入：已在跑直接 return
      this.viewing = null;
      this.running = true; this.errorMsg = ""; this.tree = null;
      this.initPhases();
      const resp = await fetch(`/api/run/${this.runId}`, { method: "POST" });
      if (!resp.ok) {                                   // 409 等：已在跑/已完成
        if (resp.status === 409) { this._listenProgress(this.runId); return; }
        this.running = false;
        return;
      }
      this.loadHistory();          // 立刻刷新左侧栏，让新任务出现在「运行中」分组
      this._listenProgress(this.runId);
    },

    // 关闭当前 SSE 连接（若有）——切任务/新建/收尾前调用，确保同一时刻只有一个连接写 phases
    _closeES() {
      if (this._es) { this._es.close(); this._es = null; }
    },

    // 接收某 run 的 SSE 进度事件
    _listenProgress(runId) {
      this._closeES();        // 先关掉上一个连接，杜绝两个任务的事件混进同一 phases（日志串台根因）
      let finished = false;   // 标记是否已正常收尾（done/error），避免 onerror 误复位 running
      const es = new EventSource(`/api/progress/${runId}`);
      this._es = es;          // 存引用，供切任务时关闭
      es.onmessage = async (e) => {
        const ev = JSON.parse(e.data);
        if (ev.event === "done") {
          finished = true; es.close();
          if (this._es === es) this._es = null;     // 仅当仍是当前连接时清引用，避免误清掉新连接
          this.tree = await (await fetch(`/api/tree/${runId}`)).json();
          this.running = false;
          this.loadHistory();
        } else if (ev.event === "error") {
          finished = true; es.close();
          if (this._es === es) this._es = null;
          this.errorMsg = ev.message || "运行出错"; this.running = false;
        } else {
          this.applyPhaseEvent(ev);
        }
      };
      // onerror 只在「尚未正常收尾」时才复位；正常 done 后的 close 不应让上传区重现（这是重复发起的根因）
      es.onerror = () => {
        es.close();
        if (this._es === es) this._es = null;
        if (!finished) this.running = false;
      };
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

    // 是否所有「有日志的阶段」都已展开（供总开关箭头方向判断）
    get allExpanded() {
      const withLogs = this.phases.filter(p => p.logs.length);
      return withLogs.length > 0 && withLogs.every(p => this.isExpanded(p));
    },

    // 总开关：全部展开 / 全部收起（仅作用于有日志的阶段）
    toggleAll() {
      const target = !this.allExpanded;
      this.phases.forEach(p => { if (p.logs.length) this.expanded[p.key] = target; });
    },

    // 点击左侧栏的 run：运行中→重连看实时进度；已完成→回看日志+树
    async openHistory(runId) {
      this._closeES();        // 切任务先关旧连接：done 分支不会重连，必须显式关，否则旧任务继续写 phases 致串台
      this.viewing = runId; this.errorMsg = "";
      this.initPhases();
      // 以服务端权威状态判定是否在跑——不信本地 history（轮询前可能过期：任务已在后台跑完但侧栏还没刷到）
      let isRunning = false;
      try {
        const st = await (await fetch(`/api/run_status/${runId}`)).json();
        isRunning = st.status === "running";
      } catch (e) {
        const item = this.history.find(h => h.run_id === runId);   // 查询失败退回本地快照兜底
        isRunning = !!(item && item.status === "running");
      }
      // 先补已落盘的历史日志，恢复已跑阶段状态
      try {
        const events = await (await fetch(`/api/runs/${runId}/logs`)).json();
        events.forEach(ev => this.applyPhaseEvent(ev));
      } catch (e) { /* 运行中可能暂无日志，忽略 */ }

      if (isRunning) {
        // 运行中：重连 SSE 接后续进度，跑完自动出树（_listenProgress 内处理）
        this.running = true; this.runId = runId; this.tree = null;
        this._listenProgress(runId);
      } else {
        // 已完成：有日志的阶段视为已完成，加载结果树
        this.running = false;
        this.phases.forEach(p => { if (p.logs.length) p.status = "done"; });
        try {
          this.tree = await (await fetch(`/api/tree/${runId}`)).json();
        } catch (e) { this.errorMsg = "加载历史记录失败"; }
      }
    },

    get cov() { return this.tree ? this.tree.coverage : {}; },
    exportUrl() { return `/api/export/${this.viewing || this.runId}.docx?keep_ai_marks=${this.keepAiMarks}`; },

    // 按 id 在大纲树里查找节点——供点击徽章时取该节点的来源
    findNode(nodeId, nodes) {
      for (const n of (nodes || (this.tree ? this.tree.nodes : []))) {
        if (n.id === nodeId) return n;
        const r = this.findNode(nodeId, n.children || []);
        if (r) return r;
      }
      return null;
    },

    // 点击徽章：打开来源详情弹窗，按来源类型分组展示 location+quote
    openSource(nodeId) {
      const node = this.findNode(nodeId);
      if (!node || !node.sources || !node.sources.length) return;
      const order = ["skeleton", "scoring", "tech_spec", "biz_terms", "ai_suggested"];
      const groups = order
        .filter(t => node.sources.some(s => s.type === t))
        .map(t => {
          const seen = new Set();
          const items = node.sources.filter(s => s.type === t).map(s => ({
            document: (s.document || "").trim(),
            location: (s.location || "").trim(),
            quote: (s.quote || "").trim(),
          })).filter(it => {
            const key = it.document + "|" + it.location + "|" + it.quote;
            if (seen.has(key)) return false;
            seen.add(key); return true;
          });
          return { type: t, label: this.badge(t), cls: this.badgeClass(t), borderCls: this.borderClass(t), items };
        });
      this.sourceModal = { nodeId, title: `${node.id} ${node.title}`, groups };
    },
    closeSource() { this.sourceModal = null; },

    renderNode(node, depth) {
      const pad = depth * 18;
      const types = [...new Set((node.sources || []).map(s => s.type))];
      const badges = types
        .map(t => `<span data-node-id="${node.id}" class="source-badge ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[11px] whitespace-nowrap cursor-pointer hover:ring-1 hover:ring-current/30 transition ${this.badgeClass(t)}">${this.badge(t)}</span>`)
        .join("");
      // 含技术参数表聚合的节点：加一个独立标签，提示此处应填技术参数响应表统一应答（非逐条要求）
      const isParamTable = (node.sources || []).some(s => s.is_param_table);
      const paramBadge = isParamTable
        ? `<span class="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[11px] whitespace-nowrap bg-teal-50 text-teal-700" title="此处技术参数在一张技术参数响应表中统一应答，不逐条单列">技术参数响应表</span>`
        : "";
      // flex 布局：标题区占满左侧并缩进，来源徽章统一推到最右对齐
      // AI 建议节点已由徽章标识，不再额外加整行底色（避免突兀）
      let html = `<div class="flex items-center py-1.5 border-b border-neutral-50">
        <div class="flex-1 min-w-0" style="padding-left:${pad}px;">
          <span class="text-neutral-900 font-medium mr-2 text-xs tabular-nums">${node.id}</span>
          <span class="text-neutral-800">${node.title}</span>
        </div>
        <div class="shrink-0 ml-3">${paramBadge}${badges}</div>
      </div>`;
      for (const c of (node.children || [])) html += this.renderNode(c, depth + 1);
      return html;
    },

    // 查询是否开启本地认证（决定退出登录按钮显隐）
    async checkAuth() {
      try {
        const r = await fetch("/auth/session");
        const data = await r.json();
        this.authEnabled = !!data.auth_enabled;
      } catch (e) { this.authEnabled = false; }
    },

    // 退出登录：清后端会话后跳登录页（请求失败也跳，保证能离开）
    async logout() {
      try {
        await fetch("/auth/logout", { method: "POST" });
      } catch (e) {
        // 忽略失败，始终跳转登录页
      } finally {
        window.location.href = "/login";
      }
    },

    init() { this.checkAuth(); this.loadHistory(); this._listenStatusEvents(); },
  };
}

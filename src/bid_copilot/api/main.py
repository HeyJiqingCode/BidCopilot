"""FastAPI 后端——上传、运行管线、SSE 进度、树查询、Word 导出"""
import asyncio
import json
import shutil
import queue
import threading
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from bid_copilot.config import Settings
from bid_copilot.llm.client import LLMClient
from bid_copilot.understanding.pipeline import run_pipeline
from bid_copilot.models import OutlineTree
from bid_copilot.understanding.output.word_export import export_to_docx
from bid_copilot.auth.middleware import register_local_auth_middleware
from bid_copilot.auth.routes import router as auth_router

app = FastAPI(title="智能投标助手 Demo")
register_local_auth_middleware(app)  # 本地登录门（ENABLE_LOCAL_AUTH=false 时完全放行）
app.include_router(auth_router)

# 运行态存储（Demo 用内存，足够）
RUNS_DIR = Path("runs")
UPLOAD_STORE: dict[str, Path] = {}        # run_id → 上传文件/目录路径
TREE_STORE: dict[str, OutlineTree] = {}   # run_id → 结果树
PROGRESS_QUEUES: dict[str, "queue.Queue"] = {}  # run_id → 进度队列

_WEB_DIR = Path(__file__).parent.parent.parent / "web"
if _WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")


# 注：下列做同步文件 I/O 的路由全部声明为普通 def（非 async）。
# FastAPI/Starlette 会把 def 路由放到线程池执行，避免 read_text()/目录遍历/docx 生成
# 这类阻塞操作堵住事件循环——否则一个请求读文件期间，SSE 进度流和其它任务的数据请求全被冻住，
# 表现为「切任务 UI 刷新很慢没反应」。只有真正异步的 progress（SSE 流）与仅起线程的 run 保留 async。
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """返回前端页面"""
    return HTMLResponse((_WEB_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    """返回登录页（仅在开启本地认证时有意义；公开路径，不经认证守卫）"""
    return HTMLResponse((_WEB_DIR / "login.html").read_text(encoding="utf-8"))


@app.post("/api/upload")
def upload(files: list[UploadFile] = File(...)) -> JSONResponse:
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
    UPLOAD_STORE[run_id] = dest_dir
    return JSONResponse({"run_id": run_id, "filenames": filenames})


# 哨兵：管线线程结束时放入队列，通知 SSE 端点收尾
_DONE = object()


@app.post("/api/run/{run_id}")
async def run(run_id: str) -> JSONResponse:
    """启动管线（非阻塞）：后台线程执行，日志事件入队供 SSE 流式推送"""
    if run_id not in UPLOAD_STORE:
        raise HTTPException(404, "unknown run_id")
    # 防重入：已在运行（队列存在且未收尾）或已完成（有结果）则拒绝重复发起，避免重头跑
    if run_id in PROGRESS_QUEUES or run_id in TREE_STORE or (RUNS_DIR / run_id / "finalize.json").exists():
        raise HTTPException(409, "run already started or finished")
    q: queue.Queue = queue.Queue()
    PROGRESS_QUEUES[run_id] = q
    settings = Settings()
    llm = LLMClient(settings=settings)

    def _worker() -> None:
        """后台线程跑管线，把阶段日志/完成/异常事件入队 + 落盘——内部辅助"""
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "logs.jsonl"

        def _log_cb(event: dict) -> None:
            """把单条日志事件入 SSE 队列并追加落盘 logs.jsonl——内部辅助"""
            q.put(event)
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(json.dumps(event, ensure_ascii=False) + "\n")
        try:
            input_dir = UPLOAD_STORE[run_id]
            names = sorted(p.name for p in input_dir.iterdir()) if input_dir.is_dir() else [input_dir.name]
            proj = Path(names[0]).stem if names else run_id
            from bid_copilot.parsing.cu_client import build_cu_client
            cu = build_cu_client(settings.cu_endpoint, settings.cu_key)
            tree = run_pipeline(
                input_dir, llm=llm,
                model_main=settings.model_main, model_mini=settings.model_mini,
                run_dir=run_dir, log_callback=_log_cb, project_name=proj,
                cu=cu,
                efforts={
                    "classify": settings.effort_classify,
                    "locate": settings.effort_locate,
                    "skeleton": settings.effort_skeleton,
                    "requirements": settings.effort_requirements,
                    "merge": settings.effort_merge,
                    "supplement": settings.effort_supplement,
                },
                max_concurrency=settings.max_concurrency,
                models={
                    "classify": settings.model_classify,
                    "locate": settings.model_locate,
                    "skeleton": settings.model_skeleton,
                    "requirements": settings.model_requirements,
                    "merge": settings.model_merge,
                    "supplement": settings.model_supplement,
                },
            )
            TREE_STORE[run_id] = tree
            meta = {
                "run_id": run_id,
                "project_name": tree.project_name,
                "filenames": names,
                "created_at": int(time.time()),
                "coverage": tree.coverage.model_dump(),
            }
            (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            q.put({"event": "done"})
        except Exception as exc:  # 把异常透传到前端，不静默吞
            q.put({"event": "error", "message": str(exc)})
        finally:
            q.put(_DONE)
            # 标记已结束：从 PROGRESS_QUEUES 移除，使 run_status 不再报 running
            # （正在连着的 SSE 已持有 q 引用，仍能读到 _DONE 收尾，不受影响）
            PROGRESS_QUEUES.pop(run_id, None)

    threading.Thread(target=_worker, daemon=True).start()
    return JSONResponse({"status": "started"})


@app.get("/api/progress/{run_id}")
async def progress(run_id: str) -> StreamingResponse:
    """SSE 进度端点——流式推送阶段日志事件，直到收到哨兵收尾"""
    if run_id not in PROGRESS_QUEUES:
        raise HTTPException(404, "unknown run_id")
    q = PROGRESS_QUEUES[run_id]

    async def _stream():
        """从队列取事件并以 SSE 格式 yield——内部辅助"""
        loop = asyncio.get_event_loop()
        while True:
            # 阻塞 get 放到线程池，避免堵住事件循环
            item = await loop.run_in_executor(None, q.get)
            if item is _DONE:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.get("/api/run_status/{run_id}")
def run_status(run_id: str) -> JSONResponse:
    """返回 run 运行态——供前端刷新后判定是否重连：done（已完成）/ running（在跑）/ unknown（未知或失效）"""
    if (RUNS_DIR / run_id / "finalize.json").exists() or run_id in TREE_STORE:
        return JSONResponse({"status": "done"})
    if run_id in PROGRESS_QUEUES:
        return JSONResponse({"status": "running"})
    return JSONResponse({"status": "unknown"})


@app.get("/api/tree/{run_id}")
def get_tree(run_id: str) -> JSONResponse:
    """返回最终大纲树 JSON（内存优先，刷新后从 finalize.json 兜底）——找不到则 404"""
    if run_id in TREE_STORE:
        return JSONResponse(TREE_STORE[run_id].model_dump())
    fin = RUNS_DIR / run_id / "finalize.json"
    if fin.exists():
        return JSONResponse(json.loads(fin.read_text(encoding="utf-8")))
    raise HTTPException(404, "tree not ready")


@app.get("/api/export/{run_id}.docx")
def export(run_id: str, keep_ai_marks: bool = False) -> FileResponse:
    """导出 Word 文档（内存优先，刷新/重启后从 finalize.json 兜底重建大纲树）——找不到则 404"""
    if run_id in TREE_STORE:
        tree = TREE_STORE[run_id]
    else:
        fin = RUNS_DIR / run_id / "finalize.json"
        if not fin.exists():
            raise HTTPException(404, "tree not ready")
        tree = OutlineTree.model_validate(json.loads(fin.read_text(encoding="utf-8")))
    out_path = RUNS_DIR / run_id / "outline.docx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_to_docx(tree, out_path, keep_ai_marks=keep_ai_marks)
    return FileResponse(str(out_path),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename="投标文件大纲.docx")


@app.get("/api/runs/{run_id}/steps/{step}")
def get_step(run_id: str, step: str) -> FileResponse:
    """返回某步中间产物 JSON——讲原理用"""
    path = RUNS_DIR / run_id / f"{step}.json"
    if not path.exists():
        raise HTTPException(404, "step not found")
    return FileResponse(str(path), media_type="application/json")


@app.get("/api/runs")
def list_runs() -> JSONResponse:
    """列出所有 run（已完成的读 meta.json 带 status=done；正在跑的从 PROGRESS_QUEUES 补 status=running）——按时间倒序"""
    items: list[dict] = []
    done_ids: set[str] = set()
    if RUNS_DIR.exists():
        for d in RUNS_DIR.iterdir():
            meta_path = d / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["status"] = "done"          # 有 meta.json = 已完成
                    items.append(meta)
                    done_ids.add(meta.get("run_id", d.name))
                except Exception:
                    continue  # 跳过损坏的 meta.json，不让单个坏文件拖垮整个历史列表
    # 补上正在跑、尚未落盘 meta 的 run（运行中）
    for run_id in list(PROGRESS_QUEUES.keys()):
        if run_id in done_ids:
            continue
        input_dir = UPLOAD_STORE.get(run_id)
        names = sorted(p.name for p in input_dir.iterdir()) if input_dir and input_dir.is_dir() else []
        proj = Path(names[0]).stem if names else run_id
        items.append({"run_id": run_id, "project_name": proj, "filenames": names,
                      "created_at": int(time.time()), "coverage": None, "status": "running"})
    items.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return JSONResponse(items)


@app.get("/api/runs/{run_id}/logs")
def get_logs(run_id: str) -> JSONResponse:
    """返回该 run 的日志事件数组（读 logs.jsonl）——找不到则 404"""
    log_path = RUNS_DIR / run_id / "logs.jsonl"
    if not log_path.exists():
        raise HTTPException(404, "logs not found")
    events: list[dict] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue  # 跳过损坏/半截写入的日志行，不让单条坏行拖垮整个读取
    return JSONResponse(events)

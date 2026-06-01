"""FastAPI 后端——上传、运行管线、SSE 进度、树查询、Word 导出"""
import asyncio
import json
import shutil
import queue
import threading
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
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

_WEB_DIR = Path(__file__).parent.parent.parent / "web"
if _WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """返回前端页面"""
    return HTMLResponse((_WEB_DIR / "index.html").read_text(encoding="utf-8"))


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


# 哨兵：管线线程结束时放入队列，通知 SSE 端点收尾
_DONE = object()


@app.post("/api/run/{run_id}")
async def run(run_id: str) -> JSONResponse:
    """启动管线（非阻塞）：后台线程执行，日志事件入队供 SSE 流式推送"""
    if run_id not in UPLOAD_STORE:
        raise HTTPException(404, "unknown run_id")
    q: queue.Queue = queue.Queue()
    PROGRESS_QUEUES[run_id] = q
    settings = Settings()
    llm = LLMClient(settings=settings)

    def _worker() -> None:
        """后台线程跑管线，把阶段日志/完成/异常事件入队——内部辅助"""
        def _log_cb(event: dict) -> None:
            q.put(event)
        try:
            tree = run_pipeline(
                UPLOAD_STORE[run_id], llm=llm,
                model_main=settings.model_main, model_mini=settings.model_mini,
                run_dir=RUNS_DIR / run_id, log_callback=_log_cb,
            )
            TREE_STORE[run_id] = tree
            q.put({"event": "done"})
        except Exception as exc:  # 把异常透传到前端，不静默吞
            q.put({"event": "error", "message": str(exc)})
        finally:
            q.put(_DONE)

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

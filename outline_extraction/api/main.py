"""FastAPI 后端——上传、运行管线、SSE 进度、树查询、Word 导出"""
import shutil
import queue
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
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

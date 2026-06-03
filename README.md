# Bid Copilot

Reads a tender document (招标文件) and automatically generates a structured **bid-document outline** (投标文件大纲) — the chapter tree a bidder must produce to respond, traced back to where each requirement came from in the tender.

Built as a demo on Azure OpenAI. Upload a tender (single file or a package of files), watch a 9-step pipeline run live, review the outline with per-node source traceability and a coverage report, then export to Word.

## Why

Missing a single required item in a bid means disqualification (漏项 = 废标). Manually reading a multi-hundred-page tender to enumerate every scoring criterion, technical spec, and commercial term is slow and error-prone. Bid Copilot extracts those requirements, aligns them into the bid-document skeleton the tender prescribes, and reports coverage so reviewers can see what is and isn't accounted for.

Two principles drive the design:
- **Accuracy cannot regress** — coverage is computed from the actual outline tree (which requirement `ref_id`s really landed in a node), never from the LLM's self-report. A requirement the LLM claims to have placed but didn't is reported as uncovered.
- **Universal, not overfit** — extraction/merge rules key on *structure and how a bidder responds*, never on a specific tender's wording.

## How it works

A 9-step pipeline (`src/bid_copilot/understanding/pipeline.py`) turns raw files into the outline:

1. **parse** — `.docx` parsed locally (native heading levels preserved); `.doc` / `.pdf` go through Azure Content Understanding for structured markdown.
2. **classify** — label each file (tender body / scoring / tech spec / commercial …).
3. **segment** — split documents into chapter blocks.
4. **locate** — find the key sections (bid-format, scoring, tech-spec, commercial).
5. **extract_skeleton** — pull the explicit bid-document skeleton the tender prescribes.
6. **extract_requirements** — extract response requirements. Scoring/commercial items are extracted one-by-one; technical *parameter-level* indicators are aggregated into a single "technical parameter response" entry (a bidder answers them in one response table, not as separate outline chapters), while requirements that need their own narrative / supporting material / dedicated section stay individual.
7. **merge** — normalize and de-duplicate the skeleton, then attach requirements to nodes. `ref_id`s are back-filled by engineering code, not by the LLM.
8. **supplement** — place any requirement that wasn't attached during merge (the LLM only decides *where*; `ref_id` back-fill is again engineering).
9. **finalize** — renumber the tree and compute the coverage report from the tree's `ref_id`s.

The web UI streams step progress over SSE, renders the outline with clickable source badges, shows a coverage panel, and exports Word.

## Tech stack

- **Backend**: FastAPI + Uvicorn, Python 3.14
- **LLM**: Azure OpenAI (Responses API) via the `openai` SDK; three model tiers (`main` / `mini` / `nano`) selectable per pipeline step
- **Document parsing**: `python-docx`, `pdfplumber`, Azure Content Understanding (for `.doc` / scanned PDFs)
- **Frontend**: Tailwind (CDN) + Alpine.js, no build step
- **No database** — run state lives in memory + the `runs/` directory on disk

## Project layout

```
src/bid_copilot/
  api/main.py            FastAPI app: upload, run, SSE progress/events, tree, export, delete
  config.py              Settings from env (.env)
  models.py              Pydantic models (OutlineTree, RequirementItem, SourceRef, …)
  llm/client.py          Azure OpenAI Responses API wrapper
  parsing/               docx/pdf extraction + Content Understanding client
  understanding/         the 9-step pipeline + per-step modules
    alignment/           merge + supplement (requirement → outline placement)
    output/              tree numbering + Word export
  auth/                  optional local login gate
src/web/                 index.html + app.js (Alpine) + login page
scripts/run_visible.py   run the full pipeline on a file/folder from the CLI
tests/                   pytest suite
```

## Running locally

Requires Python 3.14. Dependencies are imported via `PYTHONPATH=src` (no `pip install -e`).

```bash
# 1. create venv + install deps
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. configure
cp .env.example .env        # then fill in your Azure keys/endpoints

# 3. run the web app
ENABLE_LOCAL_AUTH=false PYTHONPATH=src .venv/bin/uvicorn bid_copilot.api.main:app --port 8080
# open http://127.0.0.1:8080
```

Run the pipeline headless on a file or folder (dumps each step's JSON under `runs/<name>/`):

```bash
PYTHONPATH=src .venv/bin/python scripts/run_visible.py path/to/tender.docx
```

Run the tests:

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `FOUNDRY_API_KEY_AOAI` | Azure OpenAI API key |
| `AOAI_BASE_URL` | Azure OpenAI v1 endpoint (ends with `/openai/v1/`) |
| `MODEL_MAIN` / `MODEL_MINI` / `MODEL_NANO` | the three model deployment names |
| `CU_ENDPOINT` / `CU_KEY` | Azure Content Understanding (optional; needed for `.doc`/scanned PDF) |
| `ENABLE_LOCAL_AUTH` + `LOCAL_AUTH_*` | optional local login gate |
| `MAX_CONCURRENCY` | parallelism cap for per-chapter extraction and merge batching |
| `EFFORT_<STEP>` | reasoning effort per step (`low`/`medium`/`high`) |
| `MODEL_<STEP>` | model tier per step (`main`/`mini`/`nano`) |

**Per-step model tiers** let you trade speed for accuracy. The accuracy-critical steps — `extract_requirements`, `merge`, `supplement` — should stay on `main`; lighter steps (`classify`, `locate`, `skeleton`) can drop to `mini`/`nano`.

## Deployment (Azure Container Apps)

The image is a plain Python service (no local `.doc` converter — `.doc` parsing relies entirely on Content Understanding).

Build the image in the cloud (no local Docker needed) and deploy:

```bash
# build into ACR
az acr build --registry <acr-name> --image bid-copilot:0.0.1 .

# deploy (set --target-port explicitly; the app listens on $PORT, default 8080)
az containerapp up \
  --name bid-copilot \
  --resource-group <rg> \
  --image <acr-name>.azurecr.io/bid-copilot:0.0.1 \
  --target-port 8080 --ingress external
```

Then set the environment variables (`FOUNDRY_API_KEY_AOAI`, `AOAI_BASE_URL`, `CU_*`, `MODEL_*`, …) on the container app; the image ships without an `.env`.

**Note:** `runs/` is ephemeral container storage — run history is cleared when a replica restarts or scales to zero. Mount an Azure Files volume at `/app/runs` if history must persist.

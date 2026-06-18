from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from src.agents.gitlab_agent import GitLabAgent
from src.agents.gemini_agent import GeminiAgent
import traceback

app = FastAPI(title="PipelineIQ", description="Intelligent GitLab CI/CD Agent powered by Gemini 🐕")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join("static", "index.html"))

gitlab_agent = GitLabAgent()
gemini_agent = GeminiAgent()


async def process_pipeline_event(pipeline_id: int, status: str):
    try:
        print(f"🐾 [Gigi Working] Fetching all jobs for Pipeline #{pipeline_id}...")
        jobs = gitlab_agent.get_pipeline_jobs(pipeline_id)

        if status == "failed":
            for job in jobs:
                if job['status'] == 'failed':
                    print(f"🔍 [Failed Job Found] Fetching raw logs for Job #{job['id']}...")
                    log = gitlab_agent.get_job_log(job['id'])

                    print(f"🤖 [AI Analysis] Invoking Gemini to analyze logs and generate RCA report...")
                    report = gemini_agent.analyze_failure(
                        job_log=log,
                        job_id=job['id'],
                        pipeline_id=pipeline_id
                    )

                    branch_name = f"fix/pipeline-{pipeline_id}"
                    try:
                        print(f"🌿 Attempting to create automated hotfix branch: {branch_name} ...")
                        gitlab_agent.create_branch(branch_name)
                    except Exception as branch_err:
                        print(f"⚠️ Branch creation skipped (it might already exist): {branch_err}")

                    print(f"🎫 Creating automated diagnosis Issue on GitLab...")
                    gitlab_agent.create_issue(
                        title=f"🐕 Gigi: Pipeline #{pipeline_id} Failed - Auto Diagnosis",
                        description=report
                    )
                    print(f"🎉 [Success] GitLab Diagnosis Issue has been successfully published!")
                    break

        elif status == "success":
            print(f"💰 [FinOps Triggered] Pipeline #{pipeline_id} succeeded.")
            report = gemini_agent.analyze_finops()
            gitlab_agent.create_issue(
                title=f"🐕 Gigi: Pipeline #{pipeline_id} FinOps Optimization Report",
                description=report
            )

    except Exception as e:
        print(f"❌ [Background Error] Severe crash while processing Pipeline #{pipeline_id}: {e}")
        traceback.print_exc()


@app.post("/webhook/gitlab")
async def gitlab_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()

    if payload.get("object_kind") != "pipeline":
        return {"status": "ignored"}

    pipeline_id = payload["object_attributes"]["id"]
    status = payload["object_attributes"]["status"]

    print(f"🔔 [Webhook Intercepted] Received event for Pipeline #{pipeline_id} | Status: {status}")

    if status in ["failed", "success"]:
        background_tasks.add_task(process_pipeline_event, pipeline_id, status)
        return {"status": "processing", "pipeline_id": pipeline_id}

    return {"status": "ignored", "pipeline_status": status}


@app.get("/pipelines")
async def get_pipelines():
    return gitlab_agent.get_pipelines()


# ── NEW: synchronous analyze endpoint for the frontend ──────────────────────
@app.post("/api/analyze")
async def api_analyze(request: Request):
    """
    Called by the frontend input box.
    Runs the full Gigi analysis synchronously so the UI gets real results back.
    """
    body = await request.json()
    pipeline_id = int(body.get("pipeline_id", 0))

    if not pipeline_id:
        return {"status": "error", "message": "pipeline_id is required"}

    try:
        print(f"🚀 [Frontend Trigger] Analyzing Pipeline #{pipeline_id}...")

        # 1. get real status from GitLab
        pipelines = gitlab_agent.get_pipelines()
        status = "failed"
        for p in pipelines:
            if p["id"] == pipeline_id:
                status = p["status"]
                break

        # 2. fetch jobs
        jobs = gitlab_agent.get_pipeline_jobs(pipeline_id)
        failed_jobs = [j for j in jobs if j["status"] == "failed"]

        if status != "failed" or not failed_jobs:
            return {
                "status": "ok",
                "pipeline_id": pipeline_id,
                "pipeline_status": status,
                "rca": "No failed jobs found — pipeline looks healthy! 🟢",
                "fix": "Nothing to fix.",
                "job_id": None,
                "branch": None,
                "issue": None,
            }

        job = failed_jobs[0]
        log = gitlab_agent.get_job_log(job["id"])

        # 3. real Gemini analysis
        report = gemini_agent.analyze_failure(
            job_log=log,
            job_id=job["id"],
            pipeline_id=pipeline_id
        )

        # 4. create branch + issue
        branch_name = f"fix/pipeline-{pipeline_id}"
        branch_created = False
        try:
            gitlab_agent.create_branch(branch_name)
            branch_created = True
        except Exception:
            branch_created = False  # already exists is fine

        issue_url = None
        try:
            issue = gitlab_agent.create_issue(
                title=f"🐕 Gigi: Pipeline #{pipeline_id} Failed - Auto Diagnosis",
                description=report
            )
            issue_url = issue.get("web_url") if isinstance(issue, dict) else None
        except Exception:
            pass

        return {
            "status": "success",
            "pipeline_id": pipeline_id,
            "pipeline_status": status,
            "job_id": job["id"],
            "rca": report,
            "branch": branch_name if branch_created else f"{branch_name} (already existed)",
            "issue": issue_url,
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# legacy GET trigger (keep for backwards compat)
@app.get("/analyze/{pipeline_id}")
async def analyze_pipeline(pipeline_id: int, background_tasks: BackgroundTasks):
    pipelines = gitlab_agent.get_pipelines()
    status = "failed"
    for p in pipelines:
        if p["id"] == pipeline_id:
            status = p["status"]
            break
    background_tasks.add_task(process_pipeline_event, pipeline_id, status)
    return {"status": "processing started", "pipeline_id": pipeline_id, "gigi_action": "running in background 🐾"}


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "Gigi the Chihuahua 🐕"}

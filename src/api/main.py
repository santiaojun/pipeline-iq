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
                if job['status'] in ['failed', 'error']:
                    print(f"🔍 [Failed Job Found] Fetching raw logs for Job #{job['id']}...")
                    log = gitlab_agent.get_job_log(job['id'])
                    print(f"🤖 [AI Analysis] Invoking Gemini...")
                    report = gemini_agent.analyze_failure(
                        job_log=log,
                        job_id=job['id'],
                        pipeline_id=pipeline_id
                    )
                    branch_name = f"fix/pipeline-{pipeline_id}"
                    try:
                        gitlab_agent.create_branch(branch_name)
                    except Exception as branch_err:
                        print(f"⚠️ Branch skipped: {branch_err}")

                    result = gitlab_agent.create_issue(
                        title=f"🐕 Gigi: Pipeline #{pipeline_id} Failed - Auto Diagnosis",
                        description=report
                    )
                    print(f"🎉 Issue created: {result['web_url']}")
                    break

        elif status == "success":
            report = gemini_agent.analyze_finops()
            gitlab_agent.create_issue(
                title=f"🐕 Gigi: Pipeline #{pipeline_id} FinOps Optimization Report",
                description=report
            )

    except Exception as e:
        print(f"❌ [Background Error] {e}")
        traceback.print_exc()


@app.post("/webhook/gitlab")
async def gitlab_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    if payload.get("object_kind") != "pipeline":
        return {"status": "ignored"}
    pipeline_id = payload["object_attributes"]["id"]
    status = payload["object_attributes"]["status"]
    print(f"🔔 [Webhook] Pipeline #{pipeline_id} | Status: {status}")
    if status in ["failed", "success"]:
        background_tasks.add_task(process_pipeline_event, pipeline_id, status)
        return {"status": "processing", "pipeline_id": pipeline_id}
    return {"status": "ignored", "pipeline_status": status}


@app.get("/pipelines")
async def get_pipelines():
    return gitlab_agent.get_pipelines()


@app.post("/api/analyze")
async def api_analyze(request: Request):
    body = await request.json()
    pipeline_id = int(body.get("pipeline_id", 0))
    if not pipeline_id:
        return {"status": "error", "message": "pipeline_id is required"}

    try:
        print(f"🚀 [Frontend Trigger] Analyzing Pipeline #{pipeline_id}...")

        pipelines = gitlab_agent.get_pipelines()
        status = "failed"
        for p in pipelines:
            if p["id"] == pipeline_id:
                status = p["status"]
                break

        jobs = gitlab_agent.get_pipeline_jobs(pipeline_id)
        failed_jobs = [j for j in jobs if j["status"] in ["failed", "error"]]

        if not failed_jobs:
            return {
                "status": "ok",
                "pipeline_id": pipeline_id,
                "pipeline_status": status,
                "rca": "No failed jobs found — pipeline looks healthy! 🟢",
                "fix": "Nothing to fix.",
                "job_id": None,
                "branch": None,
                "issue_url": None,
            }

        job = failed_jobs[0]
        log = gitlab_agent.get_job_log(job["id"])
        report = gemini_agent.analyze_failure(
            job_log=log,
            job_id=job["id"],
            pipeline_id=pipeline_id
        )

        branch_name = f"fix/pipeline-{pipeline_id}"
        branch_created = False
        try:
            gitlab_agent.create_branch(branch_name)
            branch_created = True
        except Exception:
            branch_created = False

        issue_url = None
        try:
            result = gitlab_agent.create_issue(
                title=f"🐕 Gigi: Pipeline #{pipeline_id} Failed - Auto Diagnosis",
                description=report
            )
            issue_url = result["web_url"]
        except Exception:
            pass

        return {
            "status": "success",
            "pipeline_id": pipeline_id,
            "pipeline_status": status,
            "job_id": job["id"],
            "rca": report,
            "branch": branch_name if branch_created else f"{branch_name} (already existed)",
            "issue_url": issue_url,
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/analyze/{pipeline_id}")
async def analyze_pipeline(pipeline_id: int, background_tasks: BackgroundTasks):
    pipelines = gitlab_agent.get_pipelines()
    status = "failed"
    for p in pipelines:
        if p["id"] == pipeline_id:
            status = p["status"]
            break
    background_tasks.add_task(process_pipeline_event, pipeline_id, status)
    return {"status": "processing started", "pipeline_id": pipeline_id}


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "Gigi the Chihuahua 🐕"}

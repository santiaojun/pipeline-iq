import gitlab
import os
from dotenv import load_dotenv
load_dotenv()

class GitLabAgent:
    def __init__(self):
        self.gl = gitlab.Gitlab(
            'https://gitlab.com',
            private_token=os.getenv('GITLAB_TOKEN')
        )
        self.project_id = os.getenv('GITLAB_PROJECT_ID')
        self.project_namespace = "santiaojun/pipeline-iq-demo"

    def get_project(self):
        return self.gl.projects.get(self.project_id)

    def get_pipelines(self, limit=10):
        project = self.get_project()
        pipelines = project.pipelines.list(per_page=limit)
        result = []
        for p in pipelines:
            result.append({
                'id': p.id,
                'status': p.status,
                'created_at': p.created_at,
                'ref': p.ref,
            })
        return result

    def get_pipeline_jobs(self, pipeline_id):
        project = self.get_project()
        pipeline = project.pipelines.get(pipeline_id)
        jobs = pipeline.jobs.list()
        result = []
        for job in jobs:
            result.append({
                'id': job.id,
                'name': job.name,
                'status': job.status,
                'duration': job.duration,
                'stage': job.stage,
            })
        return result

    def get_job_log(self, job_id):
        project = self.get_project()
        job = project.jobs.get(job_id)
        try:
            return job.trace().decode('utf-8')
        except:
            return "No log available"

    def create_issue(self, title, description):
        project = self.get_project()
        issue = project.issues.create({
            'title': title,
            'description': description,
            'labels': ['pipeline-iq', 'bug']
        })
        return {
            'iid': issue.iid,
            'web_url': f"https://gitlab.com/{self.project_namespace}/-/issues/{issue.iid}"
        }

    def create_branch(self, branch_name, ref='main'):
        project = self.get_project()
        branch = project.branches.create({
            'branch': branch_name,
            'ref': ref
        })
        return branch.name

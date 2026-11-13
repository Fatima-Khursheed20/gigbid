"""Job Analyst: extract a structured JobSpec (no MCP access)."""

from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig

from common import llm
from common.config import prompt
from rag.pipeline import heuristic_requirements
from rag.skills import extract_skills

from ..guards import delimit, neutralise
from ..handoffs import JobSpec, Requirement
from ._base import node


def heuristic_spec(job: dict) -> JobSpec:
    text = f"{job['title']}\n{job['description']}"
    reqs = heuristic_requirements(text)
    weeks = re.search(r"about (\d+) week", job["description"])
    w = float(weeks.group(1)) if weeks else None
    hours = w * 20 if w else None
    if hours is None and job.get("budget"):
        hours = job["budget"] / 40
    hours = hours or 40
    cx = "small" if hours < 25 else ("medium" if hours < 80 else "large")
    deliver = re.findall(r"^\s*-\s+(.*)$", job["description"].split("Deliverables:")[-1], re.M) if "Deliverables:" in job["description"] else []
    hr = job.get("hourly_range") or [None, None]
    return JobSpec(job_id=job["job_id"], title=job["title"], category=job.get("category", "other"),
                   requirements=[Requirement(text=r, skill=(extract_skills(r) or [None])[0]) for r in reqs],
                   skills=extract_skills(text), deliverables=deliver[:6], budget_type=job.get("budget_type", "fixed"),
                   budget_min=job.get("budget") if job.get("budget_type") == "fixed" else hr[0],
                   budget_max=job.get("budget") if job.get("budget_type") == "fixed" else hr[1],
                   timeline_weeks=w, est_hours=round(hours, 1), complexity=cx,
                   screening_questions=job.get("screening_questions") or [], source="heuristic")


async def analyse(job: dict) -> JobSpec:
    if not llm.available():
        return heuristic_spec(job)
    clean, _ = neutralise(job["description"])
    hr = job.get("hourly_range")
    user = (f"job_id: {job['job_id']}\ncategory: {job.get('category')}\nbudget_type: {job.get('budget_type')}\n"
            f"budget: {job.get('budget')}\nhourly_range: {hr}\nscreening_questions: {job.get('screening_questions')}\n\n"
            + delimit(f"{job['title']}\n\n{clean}"))
    try:
        spec = await llm.structured("analyst", prompt("analyst"), user, JobSpec)
    except llm.LLMUnavailable:
        return heuristic_spec(job)
    spec.job_id, spec.source = job["job_id"], "llm"
    spec.screening_questions = job.get("screening_questions") or spec.screening_questions
    return spec


@node("analyst", timeout_s=90)
async def analyst(state: dict, config: RunnableConfig) -> dict:
    spec = await analyse(state["job"])
    return {"job_spec": spec.model_dump(), "analyses_done": ["analyst"]}

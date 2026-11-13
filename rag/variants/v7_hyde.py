"""V7 — HyDE (query group): retrieve with a hypothetical ideal proposal written by the LLM for the job."""
from __future__ import annotations

from common.config import prompt
from common.llm import complete

from ..pipeline import Settings

SETTINGS = Settings(name="v7_hyde", query="hyde", hybrid=True, rerank=True)


async def hyde_text(job_text: str) -> str:
    return await complete("hyde", prompt("hyde"), f"<job_post>\n{job_text}\n</job_post>", max_tokens=350)

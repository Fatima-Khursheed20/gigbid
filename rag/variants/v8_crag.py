"""V8 — corrective RAG loop in LangGraph (agentic group, required one of V8/V9).

retrieve -> grade each requirement's best evidence with the open cross-encoder -> if weak, rewrite the
weak requirements and re-query once -> grade again -> requirements still without evidence are marked
"none" and the writer is told it may NOT claim them (refuse to claim when there is no evidence).
"""

from __future__ import annotations

import re
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from common.config import cfg

from ..corpus import Corpus
from ..index.embeddings import get_reranker
from ..pipeline import Pipeline, Query, Settings, heuristic_requirements

SETTINGS = Settings(name="v8_crag", query="decomposed", hybrid=True, rerank=True, crag=True)
FILLER = re.compile(r"^(hands-on experience with|experience with|experience in|knowledge of|strong|proven)\s+",
                    re.I)


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class CragState(TypedDict, total=False):
    job_text: str
    requirements: list[str]
    rewritten: dict[str, str]
    per_req: Annotated[dict, _merge]
    attempts: int


def build(corpus: Corpus, settings: Settings = SETTINGS):
    pipe = Pipeline(corpus, Settings(**{**settings.__dict__, "crag": False, "query": "whole"}))
    rr = get_reranker()
    threshold = float(cfg("rag", "crag_min_score", default=0.0))

    def retrieve_and_grade(state: CragState) -> dict:
        out = {}
        for req in state["requirements"]:
            if state.get("per_req", {}).get(req, {}).get("status") == "supported":
                continue
            q = state.get("rewritten", {}).get(req, req)
            ev = pipe.retrieve(Query(job_text=q), k=5)[:5]
            scores = rr.score(q[:500], [e["text"] for e in ev]) if ev else []
            best = max(scores) if scores else -99.0
            good = [e | {"score": round(s, 3)} for e, s in zip(ev, scores, strict=True) if s >= threshold]
            out[req] = {"status": "supported" if good else ("weak" if best > threshold - 3 else "none"),
                        "best_score": round(best, 3), "evidence": good[:3] or ev[:1] if good else [],
                        "query_used": q}
        return {"per_req": out, "attempts": state.get("attempts", 0) + 1}

    def rewrite(state: CragState) -> dict:
        rw = {}
        for req, r in state["per_req"].items():
            if r["status"] != "supported":
                core = FILLER.sub("", req).strip().rstrip(".")
                rw[req] = f"{core} project built delivered"  # offline rewrite: strip filler, bias toward project text
        return {"rewritten": rw}

    def route(state: CragState) -> str:
        weak = [r for r in state["per_req"].values() if r["status"] != "supported"]
        return "rewrite" if weak and state["attempts"] < 2 else END

    g = StateGraph(CragState)
    g.add_node("retrieve_and_grade", retrieve_and_grade)
    g.add_node("rewrite", rewrite)
    g.add_edge(START, "retrieve_and_grade")
    g.add_conditional_edges("retrieve_and_grade", route, {"rewrite": "rewrite", END: END})
    g.add_edge("rewrite", "retrieve_and_grade")
    return g.compile()


class CragRetriever:
    def __init__(self, corpus: Corpus, settings: Settings = SETTINGS) -> None:
        self.corpus, self.graph = corpus, build(corpus, settings)

    def run(self, q: Query) -> dict:
        reqs = q.requirements or heuristic_requirements(q.job_text)
        st = self.graph.invoke({"job_text": q.job_text, "requirements": reqs, "per_req": {}, "attempts": 0})
        matrix = [{"requirement": r, **{k: v for k, v in st["per_req"][r].items()}} for r in reqs]
        none = sum(m["status"] == "none" for m in matrix)
        return {"matrix": matrix, "refuse": none / max(1, len(matrix)) > 0.5, "attempts": st["attempts"]}

    def retrieve(self, q: Query, k: int = 5) -> list[dict]:
        res = self.run(q)
        seen, out = set(), []
        # interleave requirement evidence so each requirement is represented near the top
        rows = [m["evidence"] for m in res["matrix"] if m["status"] == "supported"]
        for depth in range(3):
            for evs in rows:
                if depth < len(evs) and evs[depth]["evidence_id"] not in seen:
                    seen.add(evs[depth]["evidence_id"])
                    out.append(evs[depth])
        return out

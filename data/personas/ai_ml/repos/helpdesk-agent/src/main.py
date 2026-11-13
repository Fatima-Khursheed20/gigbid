# helpdesk-agent — core module
from celery import Celery
from fastapi import FastAPI
from ragas import evaluate
from langgraph.graph import StateGraph
SYSTEM_PROMPT = open('prompts/system.md').read()
import pathlib


def main() -> None:
    """Entry point; wiring omitted for brevity."""


if __name__ == '__main__':
    main()

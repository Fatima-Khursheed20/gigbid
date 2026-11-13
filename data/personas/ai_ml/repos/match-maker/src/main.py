# match-maker — core module
from fastapi import FastAPI
from langchain_core.prompts import ChatPromptTemplate
SYSTEM_PROMPT = open('prompts/system.md').read()
import pathlib
from pgvector.psycopg import register_vector


def main() -> None:
    """Entry point; wiring omitted for brevity."""


if __name__ == '__main__':
    main()

"""Skill extraction used at ingestion time to put `skills` metadata on every chunk (B1).

Detects canonical skill names and well-known package/import aliases in prose and code. It deliberately
knows nothing about the generator's hidden labels; it only reads the chunk text.
"""

from __future__ import annotations

import re

ALIASES: dict[str, list[str]] = {
    "Python": ["python", "import ", "def "], "PyTorch": ["pytorch", "torch"], "scikit-learn": ["scikit-learn", "sklearn"],
    "XGBoost": ["xgboost", "gradient-boosted", "gradient boosted"],
    "Hugging Face Transformers": ["transformers", "hugging face", "huggingface"],
    "LoRA fine-tuning": ["lora", "peft", "adapters"], "LangChain": ["langchain"], "LangGraph": ["langgraph", "stategraph"],
    "RAG": ["retrieval-augmented", "rag", "retriever", "retrieval pipeline"], "Pinecone": ["pinecone"],
    "pgvector": ["pgvector", "register_vector"], "FAISS": ["faiss"], "OpenCV": ["opencv", "cv2"],
    "YOLO": ["yolo", "ultralytics"], "spaCy": ["spacy"], "Tesseract OCR": ["tesseract", "pytesseract", "ocr"],
    "MLflow": ["mlflow"], "Prophet": ["prophet"], "FastAPI": ["fastapi"], "AWS SageMaker": ["sagemaker"],
    "Celery": ["celery"], "LLM evaluation": ["ragas", "faithfulness", "evaluation"],
    "Prompt engineering": ["prompt", "system_prompt"], "React": ["react"], "Next.js": ["next.js", "nextjs", "next/link"],
    "TypeScript": ["typescript", "interface ", ": promise<"], "Node.js": ["node.js", "node:http", "nodejs"],
    "Express": ["express"], "NestJS": ["nestjs", "@nestjs"], "PostgreSQL": ["postgres", "create table"],
    "Prisma": ["prisma"], "MongoDB": ["mongodb", "mongoose"], "Redis": ["redis"], "GraphQL": ["graphql", "apollo"],
    "Tailwind CSS": ["tailwind"], "Stripe": ["stripe"], "OAuth": ["oauth", "nextauth", "google sign-in", "social login"],
    "Docker": ["docker", "from node:", "from python:"], "AWS Lambda": ["lambda", "export const handler"],
    "WebSockets": ["websocket", "socket.io"], "BullMQ": ["bullmq"], "Django": ["django"], "Playwright": ["playwright"],
    "Jest": ["jest"], "Shopify": ["shopify"], "React Native": ["react native", "react-native"],
    "CI/CD": ["ci/cd", "on: [push]", "github actions"], "SQL": ["sql", "select", "with cohorts"], "pandas": ["pandas"],
    "Excel": ["excel", "openpyxl", "power query"], "Power BI": ["power bi", "dax"], "Tableau": ["tableau"],
    "Looker Studio": ["looker studio", "looker"], "dbt": ["dbt", "materialized="], "Snowflake": ["snowflake"],
    "BigQuery": ["bigquery"], "Airflow": ["airflow", "dag"], "Google Analytics 4": ["ga4", "google analytics"],
    "A/B testing": ["a/b", "ab test", "proportions_ztest", "experiment"], "Statistics": ["statsmodels", "regression", "statistic"],
    "Cohort analysis": ["cohort", "retention"], "Forecasting": ["forecast", "holtwinters", "exponentialsmoothing"],
    "ETL": ["etl", "extract-transform-load", "def extract"], "Metabase": ["metabase"], "R": ["library(tidyverse)", " in r"],
    "Data visualization": ["matplotlib", "seaborn", "plotly", "chart"], "Streamlit": ["streamlit"],
    "Customer segmentation": ["segment", "kmeans", "clustering"],
}


def extract_skills(text: str) -> list[str]:
    t = text.lower()
    found = []
    for skill, aliases in ALIASES.items():
        for a in aliases:
            a = a.lower()
            if (len(a) <= 4 and re.search(rf"\b{re.escape(a.strip())}\b", t)) or (len(a) > 4 and a in t):
                found.append(skill)
                break
    return found

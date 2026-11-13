"""Skill taxonomy used by the synthetic data generator (SYNTHETIC — authored for this project).

Each skill has:
  name      canonical name (what an exact-match job post says, e.g. "Celery")
  cat       job category it belongs to
  desc      descriptive phrasing (a requirement that names the capability, not the tool)
  vague     a client-speak phrasing that only implies the skill
  code      an import / usage line that reveals the skill inside source code
"""

from __future__ import annotations

SKILLS: dict[str, dict[str, str]] = {
    # ---------------- AI / ML ----------------
    "Python": dict(cat="ai_ml", desc="strong Python engineering", vague="someone comfortable writing clean scripts",
                   code="import pathlib"),
    "PyTorch": dict(cat="ai_ml", desc="training deep neural networks", vague="a custom deep learning model trained on our data",
                    code="import torch\nfrom torch import nn"),
    "scikit-learn": dict(cat="ai_ml", desc="classical ML pipelines with cross-validation", vague="a model that predicts which customers will do X",
                         code="from sklearn.pipeline import Pipeline\nfrom sklearn.model_selection import cross_val_score"),
    "XGBoost": dict(cat="ai_ml", desc="gradient-boosted tree models", vague="the most accurate model possible on our tabular data",
                    code="import xgboost as xgb"),
    "Hugging Face Transformers": dict(cat="ai_ml", desc="fine-tuning pretrained transformer models",
                                      vague="adapt an existing language model to our domain",
                                      code="from transformers import AutoModelForSequenceClassification, Trainer"),
    "LoRA fine-tuning": dict(cat="ai_ml", desc="parameter-efficient fine-tuning of LLMs", vague="make an open model speak in our brand voice cheaply",
                             code="from peft import LoraConfig, get_peft_model"),
    "LangChain": dict(cat="ai_ml", desc="LLM application orchestration", vague="a chatbot that answers from our documents",
                      code="from langchain_core.prompts import ChatPromptTemplate"),
    "LangGraph": dict(cat="ai_ml", desc="stateful multi-step LLM agents", vague="an AI assistant that can carry out multi-step tasks",
                      code="from langgraph.graph import StateGraph"),
    "RAG": dict(cat="ai_ml", desc="retrieval-augmented generation over a document corpus",
                vague="answers grounded in our knowledge base, not made up", code="retriever = index.as_retriever(k=5)"),
    "Pinecone": dict(cat="ai_ml", desc="managed vector database for similarity search", vague="fast semantic search over millions of items",
                     code="from pinecone import Pinecone"),
    "pgvector": dict(cat="ai_ml", desc="vector search inside Postgres", vague="semantic search without adding another database",
                     code="from pgvector.psycopg import register_vector"),
    "FAISS": dict(cat="ai_ml", desc="in-memory approximate nearest-neighbour search", vague="find similar items instantly",
                  code="import faiss"),
    "OpenCV": dict(cat="ai_ml", desc="classical image processing", vague="clean up and measure things in camera images",
                   code="import cv2"),
    "YOLO": dict(cat="ai_ml", desc="real-time object detection", vague="spot objects in video feeds automatically",
                 code="from ultralytics import YOLO"),
    "spaCy": dict(cat="ai_ml", desc="named-entity recognition and text pipelines", vague="pull names, dates and amounts out of documents",
                  code="import spacy"),
    "Tesseract OCR": dict(cat="ai_ml", desc="OCR of scanned documents", vague="turn scanned PDFs into searchable text",
                          code="import pytesseract"),
    "MLflow": dict(cat="ai_ml", desc="experiment tracking and model registry", vague="keep track of which model version is in production",
                   code="import mlflow"),
    "Prophet": dict(cat="ai_ml", desc="time-series forecasting with seasonality", vague="predict next quarter's demand",
                    code="from prophet import Prophet"),
    "FastAPI": dict(cat="ai_ml", desc="serving models behind a typed REST API", vague="let our app call the model over the web",
                    code="from fastapi import FastAPI"),
    "AWS SageMaker": dict(cat="ai_ml", desc="managed model training and hosting on AWS", vague="run the model in our AWS account",
                          code="import sagemaker"),
    "Celery": dict(cat="ai_ml", desc="background task queues with retries", vague="long jobs should run in the background and retry if they fail",
                   code="from celery import Celery"),
    "LLM evaluation": dict(cat="ai_ml", desc="systematic evaluation of LLM outputs", vague="know whether the AI answers are actually correct",
                           code="from ragas import evaluate"),
    "Prompt engineering": dict(cat="ai_ml", desc="designing robust prompts and structured outputs", vague="make the AI follow our format reliably",
                               code="SYSTEM_PROMPT = open('prompts/system.md').read()"),
    # ---------------- Full-stack web ----------------
    "React": dict(cat="web", desc="component-based single-page frontends", vague="a snappy, modern web interface",
                  code="import { useState } from 'react';"),
    "Next.js": dict(cat="web", desc="server-rendered React with routing", vague="pages that load fast and rank on Google",
                    code="import Link from 'next/link';"),
    "TypeScript": dict(cat="web", desc="type-safe JavaScript codebases", vague="code that won't break when we change things",
                       code="export interface User { id: string }"),
    "Node.js": dict(cat="web", desc="JavaScript backend services", vague="a backend that handles our users and data",
                    code="import http from 'node:http';"),
    "Express": dict(cat="web", desc="minimal Node REST APIs", vague="a simple API for our mobile app", code="import express from 'express';"),
    "NestJS": dict(cat="web", desc="structured Node backends with dependency injection", vague="an enterprise-grade backend",
                   code="import { Module } from '@nestjs/common';"),
    "PostgreSQL": dict(cat="web", desc="relational schema design and SQL", vague="a reliable database for orders and customers",
                       code="CREATE TABLE orders (id uuid primary key);"),
    "Prisma": dict(cat="web", desc="typed ORM migrations", vague="database changes without downtime", code="import { PrismaClient } from '@prisma/client';"),
    "MongoDB": dict(cat="web", desc="document databases", vague="flexible storage for varied product data", code="import mongoose from 'mongoose';"),
    "Redis": dict(cat="web", desc="caching and pub/sub", vague="make the slow pages fast", code="import { createClient } from 'redis';"),
    "GraphQL": dict(cat="web", desc="GraphQL schemas and resolvers", vague="one endpoint the frontend can query flexibly",
                    code="import { ApolloServer } from '@apollo/server';"),
    "Tailwind CSS": dict(cat="web", desc="utility-first styling", vague="a clean design that matches our Figma", code="@tailwind base;"),
    "Stripe": dict(cat="web", desc="payments and subscriptions integration", vague="customers should be able to pay monthly",
                   code="import Stripe from 'stripe';"),
    "OAuth": dict(cat="web", desc="social login and OAuth flows", vague="sign in with Google", code="import NextAuth from 'next-auth';"),
    "Docker": dict(cat="web", desc="containerised deployments", vague="it should run the same on every server", code="FROM node:20-alpine"),
    "AWS Lambda": dict(cat="web", desc="serverless functions", vague="we don't want to manage servers", code="export const handler = async (event) => {"),
    "WebSockets": dict(cat="web", desc="real-time bidirectional updates", vague="users see changes instantly without refreshing",
                       code="import { Server } from 'socket.io';"),
    "BullMQ": dict(cat="web", desc="Node job queues", vague="emails and exports should happen in the background", code="import { Queue } from 'bullmq';"),
    "Django": dict(cat="web", desc="batteries-included Python web apps", vague="an admin panel our staff can use", code="from django.db import models"),
    "Playwright": dict(cat="web", desc="end-to-end browser testing", vague="be sure checkout never breaks after a release",
                       code="import { test, expect } from '@playwright/test';"),
    "Jest": dict(cat="web", desc="unit testing JavaScript", vague="confidence that the code works", code="import { describe, it } from '@jest/globals';"),
    "Shopify": dict(cat="web", desc="Shopify app and theme development", vague="customise our online store", code="import { shopifyApi } from '@shopify/shopify-api';"),
    "React Native": dict(cat="web", desc="cross-platform mobile apps", vague="an app for both iPhone and Android", code="import { View } from 'react-native';"),
    "CI/CD": dict(cat="web", desc="automated build and deploy pipelines", vague="push a button and it's live", code="on: [push]"),
    # ---------------- Data analytics ----------------
    "SQL": dict(cat="data", desc="complex analytical SQL (window functions, CTEs)", vague="answers from our database", code="WITH cohorts AS (SELECT"),
    "pandas": dict(cat="data", desc="data wrangling in pandas", vague="clean up messy spreadsheets", code="import pandas as pd"),
    "Excel": dict(cat="data", desc="advanced Excel modelling (pivots, Power Query)", vague="a spreadsheet the finance team can use",
                  code="# exported with openpyxl\nimport openpyxl"),
    "Power BI": dict(cat="data", desc="Power BI dashboards and DAX", vague="a dashboard for the leadership team", code="-- DAX: Revenue YoY = DIVIDE([Revenue]-[Revenue LY],[Revenue LY])"),
    "Tableau": dict(cat="data", desc="Tableau visual analytics", vague="interactive charts we can share", code="# extracted with tableauhyperapi\nfrom tableauhyperapi import HyperProcess"),
    "Looker Studio": dict(cat="data", desc="Looker Studio reports", vague="a free live report from Google Sheets", code="# looker studio community connector config"),
    "dbt": dict(cat="data", desc="dbt models, tests and documentation", vague="trustworthy, documented metrics everyone agrees on",
                code="{{ config(materialized='incremental') }}"),
    "Snowflake": dict(cat="data", desc="Snowflake warehousing", vague="a central place for all our company data", code="import snowflake.connector"),
    "BigQuery": dict(cat="data", desc="BigQuery analytics", vague="analyse our Google data at scale", code="from google.cloud import bigquery"),
    "Airflow": dict(cat="data", desc="scheduled data pipelines (DAGs)", vague="reports that refresh every morning automatically",
                    code="from airflow import DAG"),
    "Google Analytics 4": dict(cat="data", desc="GA4 event analysis", vague="understand where our website visitors drop off",
                               code="from google.analytics.data_v1beta import BetaAnalyticsDataClient"),
    "A/B testing": dict(cat="data", desc="experiment design and significance testing", vague="know whether the new design actually helped",
                        code="from statsmodels.stats.proportion import proportions_ztest"),
    "Statistics": dict(cat="data", desc="regression and hypothesis testing", vague="what really drives our sales", code="import statsmodels.api as sm"),
    "Cohort analysis": dict(cat="data", desc="retention and cohort analysis", vague="why customers stop coming back", code="retention = cohort.pivot_table(index='cohort')"),
    "Forecasting": dict(cat="data", desc="demand and revenue forecasting", vague="plan inventory for next season", code="from statsmodels.tsa.holtwinters import ExponentialSmoothing"),
    "ETL": dict(cat="data", desc="extract-transform-load pipelines", vague="combine data from our CRM and shop", code="def extract(): ...\ndef transform(df): ...\ndef load(df): ..."),
    "Metabase": dict(cat="data", desc="self-serve BI with Metabase", vague="let the team build their own charts", code="# metabase question exported as JSON"),
    "R": dict(cat="data", desc="statistical analysis in R", vague="rigorous statistical report", code="library(tidyverse)"),
    "Data visualization": dict(cat="data", desc="clear charts with matplotlib/seaborn/Plotly", vague="charts our board will understand",
                               code="import matplotlib.pyplot as plt\nimport seaborn as sns"),
    "Streamlit": dict(cat="data", desc="internal data apps in Streamlit", vague="a little web tool to explore the numbers", code="import streamlit as st"),
    "Customer segmentation": dict(cat="data", desc="clustering customers into segments", vague="group our customers so marketing can target them",
                                  code="from sklearn.cluster import KMeans"),
}

# Out-of-domain skills: jobs requiring these should be skipped by all three personas.
OUT_OF_DOMAIN = [
    "iOS Swift", "Unity 3D", "Video editing", "Logo design", "SEO copywriting", "Solidity smart contracts",
    "Embedded C firmware", "Salesforce Apex", "PHP Laravel", "Voice-over", "Illustrator vector art",
    "3D modelling in Blender", "Bookkeeping in QuickBooks", "Amazon PPC ads", "TikTok content creation",
]

CATEGORY_LABEL = {"ai_ml": "AI & Machine Learning", "web": "Web Development", "data": "Data Analytics", "other": "Other"}


def skills_in(cat: str) -> list[str]:
    return [k for k, v in SKILLS.items() if v["cat"] == cat]

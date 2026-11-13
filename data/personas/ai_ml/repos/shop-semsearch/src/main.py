# shop-semsearch — core module
from fastapi import FastAPI
from transformers import AutoModelForSequenceClassification, Trainer
from pinecone import Pinecone
import pathlib


def main() -> None:
    """Entry point; wiring omitted for brevity."""


if __name__ == '__main__':
    main()

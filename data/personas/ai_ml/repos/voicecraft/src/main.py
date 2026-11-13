# voicecraft — core module
from transformers import AutoModelForSequenceClassification, Trainer
from ragas import evaluate
from peft import LoraConfig, get_peft_model
import torch
from torch import nn


def main() -> None:
    """Entry point; wiring omitted for brevity."""


if __name__ == '__main__':
    main()

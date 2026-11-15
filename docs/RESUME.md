# Résumé bullet (numbers from evals/results/)

- Built **GigBid**, a LangGraph multi-agent freelancer copilot (10 agents, 3 MCP servers, human-approval interrupts on Postgres) that lifted evidence Recall@5 from **0.45 to 0.70** over naive RAG and cut prompt-injection success from **50% to 0%**.
- Found by measurement that an uncalibrated retrieval-grading threshold was skipping good jobs; calibrating it on dev data raised bid/skip F1 from **0.71 to 0.91** (0.89 on a held-out set), at **$0.0003** per job analysed on open-weight models.

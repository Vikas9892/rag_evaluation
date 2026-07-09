"""
Locust load test for the RAG Evaluation API.

Usage (against a locally running API):
    locust -f load_tests/locustfile.py --host http://localhost:8000

Usage (headless, 10 users, 60 seconds):
    locust -f load_tests/locustfile.py \
           --host http://localhost:8000 \
           --headless -u 10 -r 2 -t 60s \
           --csv reports/load_test

Key metrics to watch:
  - Average latency   — driven mostly by Groq API call (~1–3 s)
  - P95 latency       — should stay < 5 s under 10 concurrent users
  - Requests/sec      — limited by Groq rate limits on free tier
  - Failure rate      — should be 0 % under normal load
"""
import random

from locust import HttpUser, between, task

_QUESTIONS = [
    "What is the Eiffel Tower?",
    "Explain transformer attention mechanisms.",
    "How does FAISS index work?",
    "What are the components of a RAG pipeline?",
    "What is BM25 and how is it different from dense retrieval?",
    "Explain the difference between precision and recall.",
    "What is a cross-encoder and when should you use one?",
    "How does reciprocal rank fusion combine retrieval results?",
    "What are the main evaluation metrics for information retrieval?",
    "What is a sentence transformer?",
]


class RAGAPIUser(HttpUser):
    """Simulates a single concurrent API user.

    Task weight: /query is called 5× more often than /health.
    wait_time simulates realistic think-time between requests.
    """

    wait_time = between(1, 3)

    @task(1)
    def health_check(self) -> None:
        self.client.get("/health")

    @task(5)
    def query(self) -> None:
        question = random.choice(_QUESTIONS)
        self.client.post(
            "/query",
            json={"question": question, "top_k": 5},
            name="/query",
        )

    @task(2)
    def metrics(self) -> None:
        self.client.get("/metrics")

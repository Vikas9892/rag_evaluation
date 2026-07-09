import sys
from pathlib import Path

# Make the project root importable inside the Lambda execution environment.
# Lambda sets the working directory to the function root; this ensures
# absolute imports like `from api.app import app` resolve correctly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mangum import Mangum

from api.app import app  # noqa: E402 — import after sys.path mutation

# Mangum wraps the FastAPI ASGI app as an AWS Lambda handler.
# `lifespan="off"` skips asynccontextmanager startup/shutdown — Lambda
# containers don't support long-lived lifespan events reliably.
# The RAGService singleton is initialised on first request (warm start) and
# reused across subsequent invocations within the same container.
handler = Mangum(app, lifespan="off")

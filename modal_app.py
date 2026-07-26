"""Modal deployment wrapper for the FlowStrix demo API.

Wraps the FastAPI app in ``flowstrix.api.server`` with a Modal ASGI function so
the public demo (https://anjesh.ai/FlowStrix/) has a live backend to talk to.
The React UI is hosted separately on GitHub Pages and calls this backend's
``/api/*`` endpoints cross-origin (the app already sends permissive CORS).

Deploy from the repo root:

    modal deploy modal_app.py

Requires an LLM-key secret, created once from the gitignored .env (values are
never printed):

    set -a; . ./.env; set +a
    modal secret create flowstrix-llm \\
        GROQ_API_KEY="$GROQ_API_KEY" \\
        GEMINI_API_KEY="$GEMINI_API_KEY" \\
        ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \\
        TOGETHER_API_KEY="$TOGETHER_API_KEY" \\
        UPSTASH_REDIS_REST_URL="$UPSTASH_REDIS_REST_URL" \\
        UPSTASH_REDIS_REST_TOKEN="$UPSTASH_REDIS_REST_TOKEN" \\
        --force

The gateway tries Together AI -> Groq -> Gemini -> Anthropic with automatic
failover (Together first = metered paid tier, no free-tier throttling), so
the public demo stays reliable and only falls back to Groq/Gemini/Anthropic
if Together errors. Upstash exact-match response caching is enabled
automatically when UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN are
present in the same secret.
"""

from __future__ import annotations

from pathlib import Path

import modal

REPO_ROOT = "/root/app"
LOCAL_REPO_ROOT = Path(__file__).resolve().parent

# Runtime dependencies mirror pyproject.toml. Installed as their own image layer
# so they cache independently of the (frequently-changing) source copy below.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.115",
        "uvicorn>=0.30",
        "python-multipart>=0.0.9",
        "python-dotenv>=1.0",
        "pydantic>=2.5",
        "pyyaml>=6.0",
        "openai>=1.30",
        "httpx>=0.27",
        "instructor>=1.5",
        "langgraph>=0.2",
        "langchain-core>=0.3",
        "qdrant-client>=1.9",
        "fastembed>=0.3",
        "rich>=13.0",
        "typer>=0.12",
    )
    .add_local_dir(
        str(LOCAL_REPO_ROOT),
        remote_path=REPO_ROOT,
        copy=True,  # copy (not mount) so the run_commands below can act on it
        ignore=[
            ".git",
            ".git/**",
            "__pycache__",
            "**/__pycache__",
            "*.pyc",
            "ui",
            "ui/**",  # UI is hosted on GitHub Pages, not served from Modal
            "docs",
            "docs/**",
            "tests",
            "tests/**",
            ".venv",
            ".venv/**",
            ".env",  # keys arrive via the Modal secret, never the file
        ],
    )
    # Bake the bge-small embedding model into the image so the first
    # knowledge-backed run doesn't pay a cold model download inside the request.
    .run_commands(
        'python -c "from fastembed import TextEmbedding; '
        "TextEmbedding('BAAI/bge-small-en-v1.5')\""
    )
    .workdir(REPO_ROOT)
)

app = modal.App("flowstrix-demo", image=image)


@app.function(
    secrets=[modal.Secret.from_name("flowstrix-llm")],
    min_containers=0,  # scale to zero when idle — no standing cost
    # Keep a warm container for 10 min after a request so a HITL "resume" lands
    # in the same process that holds the paused in-memory session/executor state.
    scaledown_window=600,
)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def web():
    import os
    import sys

    os.chdir(REPO_ROOT)  # CWD-relative "examples/x.yaml" spec paths resolve here
    sys.path.insert(0, f"{REPO_ROOT}/src")  # src-layout import path

    from flowstrix.api.server import app as fastapi_app

    return fastapi_app

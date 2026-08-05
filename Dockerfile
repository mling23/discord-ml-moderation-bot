FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_MODEL=all-MiniLM-L6-v2

WORKDIR /app

# Install CPU-only PyTorch first. The default torch wheel bundles ~2GB of CUDA
# GPU libraries we will never use on a typical VM; the CPU index avoids them.
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install the app and its remaining dependencies.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# Pre-download the embedding model at build time so the container starts fast
# and does not need network access to Hugging Face at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

CMD ["python", "-m", "modbot"]

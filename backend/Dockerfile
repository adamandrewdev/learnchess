# api image: FastAPI app + both chess engines.
# Build context is the repo root:  docker build -f backend/Dockerfile -t learnchess-api .
#
# Layer order is heaviest-and-stablest first so code edits don't re-download PyTorch.
FROM python:3.12-slim

# Stockfish (the judge, D1) from Debian; git is needed to pip-install Maia-3 from GitHub.
RUN apt-get update \
 && apt-get install -y --no-install-recommends stockfish git \
 && rm -rf /var/lib/apt/lists/*
# Debian puts it in /usr/games. Fail the build here rather than at the first move.
ENV STOCKFISH_PATH=/usr/games/stockfish
RUN test -x "$STOCKFISH_PATH" && printf "uci\nquit\n" | "$STOCKFISH_PATH" | grep -m1 "^id name"

# CPU-only PyTorch: Maia-3's dependency, and by far the largest layer.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Maia-3 (the opponent, D2). AGPL-3.0, fine for personal local use.
ARG MAIA3_REF=main
RUN pip install --no-cache-dir "git+https://github.com/CSSLab/maia3@${MAIA3_REF}"
# Bake the 5M checkpoint (CPU-friendly) into the image so runs work offline and don't
# re-download into throwaway containers.
RUN maia3-cache --model 5m

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY pyproject.toml ./
COPY core core
COPY backend backend
RUN pip install --no-cache-dir -e .

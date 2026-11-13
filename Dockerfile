FROM python:3.11-slim-bookworm

# System: Node 22 (Codex CLI, Remotion, 3D prop validation) + Chrome libs for Remotion's headless render.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates gnupg \
      libnss3 libdbus-1-3 libatk1.0-0 libgbm1 libasound2 libxrandr2 libxkbcommon0 libxfixes3 \
      libxcomposite1 libxdamage1 libatk-bridge2.0-0 libpango-1.0-0 libcairo2 libcups2 \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layers first so code edits don't reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN npm i -g @openai/codex

COPY web/package.json web/package-lock.json web/
RUN npm ci --prefix web
RUN cd web && npx remotion browser ensure

# Whisper base model, loaded offline by server.py from models/faster-whisper-base.
RUN mkdir -p models/faster-whisper-base && cd models/faster-whisper-base \
 && for f in config.json tokenizer.json vocabulary.txt model.bin; do \
      curl -fL -o "$f" "https://huggingface.co/Systran/faster-whisper-base/resolve/main/$f"; done

COPY . .

ENV PYTHONUNBUFFERED=1 BLOCKCUT_AI=codex CODEX_HOME=/data/codex REVIEW_DATA_DIR=/data
CMD ["sh", "deploy/start.sh"]

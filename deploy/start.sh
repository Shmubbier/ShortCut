#!/bin/sh
# Railway entrypoint: Codex sign-in and the review log live on the /data volume.
export BLOCKCUT_AI="${BLOCKCUT_AI:-codex}"
export CODEX_HOME="${CODEX_HOME:-/data/codex}"
export REVIEW_DATA_DIR="${REVIEW_DATA_DIR:-/data}"
export REVIEW_HOSTED="${REVIEW_HOSTED:-1}"
mkdir -p "$CODEX_HOME" "$REVIEW_DATA_DIR"
exec python server.py

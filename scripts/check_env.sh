#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
  echo "warning: .env not found" >&2
  exit 0
fi

. ./.env

if [ -z "${VIDEO_TOOLS_THUMBNAIL_PATH:-}" ]; then
  echo "warning: VIDEO_TOOLS_THUMBNAIL_PATH is not set" >&2
  exit 0
fi

if [ ! -f "$VIDEO_TOOLS_THUMBNAIL_PATH" ]; then
  echo "warning: VIDEO_TOOLS_THUMBNAIL_PATH does not exist: $VIDEO_TOOLS_THUMBNAIL_PATH" >&2
fi

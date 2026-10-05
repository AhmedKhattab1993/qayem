#!/usr/bin/env bash
# Encode the explainer video for the website: 1080p and 720p H.264 (fast start, so it plays while
# downloading) and a WebP poster. The master stays outside the repo; the outputs land in web/public/media
# and are copied into the build. Run again whenever the master changes, and bump VERSION so browsers refetch.
#   scripts/encode-explainer.sh ~/Videos/qayem/qayem-pilot-v4.mp4
set -euo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${1:?usage: encode-explainer.sh MASTER.mp4}"
VERSION="${VERSION:-v4}"
OUT="$QAYEM_ROOT/web/public/media"
POSTER_AT="${POSTER_AT:-1}"
mkdir -p "$OUT"
encode() {  # height, crf, max bitrate
  ffmpeg -hide_banner -loglevel error -y -i "$SOURCE" \
    -vf "scale=-2:$1:flags=lanczos,format=yuv420p" -c:v libx264 -preset slow -profile:v high -crf "$2" \
    -maxrate "$3" -bufsize "$(( ${3%k} * 2 ))k" -g 60 -c:a aac -b:a 128k -ac 2 \
    -movflags +faststart "$OUT/explainer-$VERSION-$1.mp4"
}
encode 1080 23 4000k
encode 720 24 2000k
for width in 640 1280; do
  ffmpeg -hide_banner -loglevel error -y -ss "$POSTER_AT" -i "$SOURCE" -frames:v 1 \
    -vf "scale=$width:-2:flags=lanczos" -c:v libwebp -quality 78 "$OUT/explainer-$VERSION-poster-$width.webp"
done
ls -la "$OUT"

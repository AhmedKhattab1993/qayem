"""Native edge-cache byte ranges for the bundled films, without buffering in Python."""
import re
from urllib.parse import urlsplit


def byte_range(header: str | None, size: int) -> tuple[int, int, int]:
    if not header:
        return 0, size - 1, 200
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError("Unsatisfiable range")
    first, last = match.groups()
    if not first:
        length = int(last)
        if length <= 0:
            raise ValueError("Unsatisfiable range")
        return max(0, size - length), size - 1, 206
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError("Unsatisfiable range")
    return start, end, 206


async def serve_film(request, env, films):
    # Runtime-only imports keep the HTTP range rules testable in ordinary Python.
    from js import caches
    from workers import Request, Response

    url = urlsplit(request.url)
    filename = url.path.removeprefix("/media/")
    if filename not in films:
        return Response("Film not found.", status=404)
    if request.method not in {"GET", "HEAD"}:
        return Response("Method not allowed.", status=405, headers={"Allow": "GET, HEAD"})
    size, version = films[filename]["size"], films[filename]["sha256"]
    try:
        start, end, status = byte_range(request.headers.get("Range"), size)
    except ValueError:
        return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(size), "Content-Type": "video/mp4",
               "Cache-Control": "public, max-age=86400", "ETag": f'"{version}"',
               "X-Content-Type-Options": "nosniff"}
    if request.method == "HEAD":
        if status == 206:
            headers.update({"Content-Length": str(end - start + 1), "Content-Range": f"bytes {start}-{end}/{size}"})
        return Response(status=status, headers=headers)
    # Cache keys include the actual build's content hash. Queries and client headers
    # cannot alter this public asset; no cookies or authorization headers are cached.
    key = f"{url.scheme}://{url.netloc}{url.path}?asset={version}"
    wanted = Request(key, headers={"Range": f"bytes={start}-{end}"} if status == 206 else {})
    cached = await caches.default.match(wanted.js_object)
    if cached is None:
        asset = await env.ASSETS.fetch(f"https://assets.local/media/{filename}")
        if asset.status != 200 or not (asset.headers.get("Content-Type") or "").startswith("video/"):
            return Response("Film not found.", status=404)
        response = Response(asset.body, headers=headers)
        await caches.default.put(key, response.js_object)
        cached = await caches.default.match(wanted.js_object)
    if cached is None:
        return Response("Film cache temporarily unavailable.", status=503, headers={"Retry-After": "5"})
    return Response(cached)

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


TILE_FILES = {"egypt.pmtiles"}


async def serve_tiles(request, env):
    """The basemap (one PMTiles archive in the private `qayem-map` R2 bucket), by byte range.

    MapLibre's PMTiles protocol reads the archive's header, directories and tiles as ranges; each is
    answered straight from R2 and cached at the edge. No tile server, no per-view cost.
    """
    from js import Object, caches
    from pyodide.ffi import to_js
    from workers import Request, Response

    url = urlsplit(request.url)
    name = url.path.removeprefix("/tiles/")
    bucket = getattr(env, "TILES", None)
    if name not in TILE_FILES or bucket is None:
        return Response("Not found.", status=404)
    if request.method not in {"GET", "HEAD"}:
        return Response("Method not allowed.", status=405, headers={"Allow": "GET, HEAD"})
    head = await bucket.head(name)
    if head is None:
        return Response("Not found.", status=404)
    size, etag = int(head.size), str(head.httpEtag)
    try:
        start, end, status = byte_range(request.headers.get("Range"), size)
    except ValueError:
        return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
    headers = {"Accept-Ranges": "bytes", "Content-Type": "application/octet-stream", "ETag": etag,
               "Cache-Control": "public, max-age=86400", "Content-Length": str(end - start + 1),
               "Access-Control-Allow-Origin": "*", "X-Content-Type-Options": "nosniff"}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if request.method == "HEAD":
        return Response(status=status, headers=headers)
    key = f"{url.scheme}://{url.netloc}{url.path}?v={etag.strip(chr(34))}&r={start}-{end}"
    cached = await caches.default.match(key)
    if cached is not None:
        return Response(cached.body, status=status, headers=headers)
    options = to_js({"range": {"offset": start, "length": end - start + 1}}, dict_converter=Object.fromEntries)
    body = await bucket.get(name, options)
    if body is None:
        return Response("Not found.", status=404)
    data = bytes(await body.arrayBuffer())  # a memoryview in Python Workers; Response takes bytes
    await caches.default.put(key, Response(data, status=200, headers=headers).js_object)
    return Response(data, status=status, headers=headers)

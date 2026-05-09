from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx


class UnsupportedSourceError(ValueError):
    pass


class DownloadError(RuntimeError):
    pass


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in YOUTUBE_HOSTS


async def download_to_file(url: str, dest: Path, timeout: float = 600.0) -> Path:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsupportedSourceError(f"unsupported scheme: {parsed.scheme}")

    if is_youtube_url(url):
        return await _download_youtube(url, dest)

    return await _download_direct(url, dest, timeout)


async def _download_direct(url: str, dest: Path, timeout: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                raise DownloadError(f"download_failed: HTTP {resp.status_code}")
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
    return dest


async def _download_youtube(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    return await asyncio.to_thread(_yt_dlp_download, url, dest)


def _yt_dlp_download(url: str, dest: Path) -> Path:
    import yt_dlp

    template = str(dest.with_suffix("")) + ".%(ext)s"
    opts = {
        "format": "bestaudio/best",
        "outtmpl": template,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        produced = Path(ydl.prepare_filename(info))
    if produced != dest:
        produced.replace(dest)
    return dest

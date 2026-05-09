from pathlib import Path

import httpx
import pytest
import respx

from transcribe_service.sources.upload import save_upload_stream
from transcribe_service.sources.url import (
    UnsupportedSourceError,
    download_to_file,
    is_youtube_url,
)


@pytest.mark.asyncio
async def test_save_upload_stream(tmp_path: Path):
    async def chunks():
        yield b"abc"
        yield b"def"

    out = tmp_path / "u.bin"
    written = await save_upload_stream(chunks(), out)
    assert written == out
    assert out.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_download_direct_media(tmp_path: Path):
    async with respx.mock(assert_all_called=True) as mock:
        mock.get("https://media.test/x.mp4").mock(
            return_value=httpx.Response(200, content=b"BINARY", headers={"content-type": "video/mp4"})
        )
        out = await download_to_file("https://media.test/x.mp4", tmp_path / "x.mp4")
        assert out.read_bytes() == b"BINARY"


@pytest.mark.asyncio
async def test_download_rejects_ftp():
    with pytest.raises(UnsupportedSourceError):
        await download_to_file("ftp://x.test/a.mp4", Path("/tmp/x"))


def test_is_youtube_url():
    assert is_youtube_url("https://youtu.be/abc")
    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert not is_youtube_url("https://media.test/a.mp4")

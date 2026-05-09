from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator


async def save_upload_stream(stream: AsyncIterator[bytes], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        async for chunk in stream:
            if chunk:
                f.write(chunk)
    return dest

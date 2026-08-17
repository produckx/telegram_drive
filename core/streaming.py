"""
Streaming server logic with 512KB CDN alignment fix for HTTP Range requests.
Mirrors build_media_response & iter_telegram_media_range from Old_Project server.rs.
"""
import os
import math
from typing import Optional, AsyncGenerator
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from telethon import TelegramClient
from telethon.tl.types import Document

CHUNK_SIZE = 65536        # 64 KB
CDN_ALIGNMENT = 524288    # 512 KB


def parse_range_header(header_val: str, total_size: int) -> Optional[tuple[int, int]]:
    """Parse HTTP Range header: 'bytes=start-end' -> (start, end)."""
    if not header_val or not header_val.startswith("bytes="):
        return None
    range_val = header_val.replace("bytes=", "").strip()
    parts = range_val.split("-")
    try:
        start = int(parts[0]) if parts[0] else 0
        if len(parts) > 1 and parts[1]:
            end = min(int(parts[1]), total_size - 1)
        else:
            end = total_size - 1
        if start <= end and start < total_size:
            return start, end
    except ValueError:
        pass
    return None


async def iter_telegram_media_range(
    client: TelegramClient,
    location,
    total_size: int,
    start_byte: int,
    content_length: int,
) -> AsyncGenerator[bytes, None]:
    """
    Implements 512 KB CDN boundary alignment and leading byte discard.
    This fixes the Telegram CDN offset bug when streaming video with arbitrary seeks.
    """
    # 1. Round requested start down to 512 KB boundary
    cdn_aligned_start = (start_byte // CDN_ALIGNMENT) * CDN_ALIGNMENT
    bytes_to_skip = start_byte - cdn_aligned_start

    skipped = 0
    total_yielded = 0

    async for chunk in client.iter_download(
        location,
        offset=cdn_aligned_start,
        chunk_size=CHUNK_SIZE,
    ):
        data = chunk
        if skipped < bytes_to_skip:
            to_skip = bytes_to_skip - skipped
            if len(data) <= to_skip:
                skipped += len(data)
                continue
            else:
                data = data[to_skip:]
                skipped = bytes_to_skip

        if total_yielded + len(data) > content_length:
            allowed = content_length - total_yielded
            if allowed > 0:
                yield data[:allowed]
                total_yielded += allowed
            break
        else:
            yield data
            total_yielded += len(data)
            if total_yielded >= content_length:
                break


def build_media_response(
    request: Request,
    client: TelegramClient,
    document,
    mime_type: str = "application/octet-stream",
    filename: Optional[str] = None,
) -> Response:
    """Build a StreamingResponse supporting HTTP 206 Range requests."""
    total_size = getattr(document, "size", 0)
    range_header = request.headers.get("Range")

    start_byte = 0
    end_byte = total_size - 1 if total_size > 0 else 0
    is_range = False

    if total_size > 0 and range_header:
        parsed = parse_range_header(range_header, total_size)
        if parsed:
            start_byte, end_byte = parsed
            is_range = True

    content_length = (end_byte - start_byte + 1) if is_range else total_size

    generator = iter_telegram_media_range(
        client=client,
        location=document,
        total_size=total_size,
        start_byte=start_byte,
        content_length=content_length,
    )

    headers = {
        "Content-Type": mime_type,
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Cache-Control": "private, max-age=120",
    }

    if is_range:
        headers["Content-Range"] = f"bytes {start_byte}-{end_byte}/{total_size}"
        status_code = 206
    else:
        status_code = 200

    if filename:
        import urllib.parse
        encoded_fn = urllib.parse.quote(filename)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_fn}'

    return StreamingResponse(
        generator,
        status_code=status_code,
        headers=headers,
        media_type=mime_type,
    )
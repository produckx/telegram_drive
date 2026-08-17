from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse
from web.templates import templates
from core.telegram_client import telegram_manager
from core.palette import color_for, ext_for_name
from api.folders.catalog import clean_folder_name
from telethon.tl.types import Channel

router = APIRouter(prefix="/storage", tags=["Web Storage"])


def _doc_filename(msg) -> str:
    doc = msg.document
    if not doc:
        return "Photo.jpg" if msg.photo else "unknown"
    name = "unknown"
    if doc.attributes:
        for attr in doc.attributes:
            fn = getattr(attr, "file_name", None)
            if fn:
                name = fn
                break
    return msg.text.strip() if msg.text and msg.text.strip() else name


@router.get("", response_class=_TemplateResponse)
async def index(request: Request):
    current_user = request.state.current_user
    if not current_user or not current_user.is_active:
        return RedirectResponse(url="/auth/login")

    uid = current_user.id
    await telegram_manager.ensure_connected(uid)
    if not telegram_manager.is_connected(uid):
        return RedirectResponse(url="/auth/tg-connect")

    client = telegram_manager._get_session(uid).client
    stats = {"total_storage_used_bytes": 0, "total_file_count": 0, "folders": [], "mime_types": []}
    duplicates = []

    try:
        me = await client.get_me()
        peers = [(None, "Saved Messages", me)]
        async for dialog in client.iter_dialogs():
            e = dialog.entity
            if isinstance(e, Channel) and "[td]" in getattr(e, "title", "").lower():
                peers.append((e.id, clean_folder_name(e.title), e))

        folder_stats = []
        ext_map = {}
        total_size = 0
        total_count = 0
        dup_map = {}

        for fid, name, peer in peers:
            folder_size = 0
            folder_count = 0
            async for msg in client.iter_messages(peer, limit=200):
                if not msg.media:
                    continue
                doc = msg.document
                if doc:
                    size = doc.size
                    mime = doc.mime_type or "application/octet-stream"
                    fname = _doc_filename(msg)
                elif msg.photo:
                    size = 0
                    mime = "image/jpeg"
                    fname = "Photo.jpg"
                else:
                    continue

                folder_size += size
                folder_count += 1
                total_size += size
                total_count += 1

                ext = ext_for_name(fname)
                if ext not in ext_map:
                    ext_map[ext] = {
                        "ext": ext, "label": ext.upper(), "mime_type": mime,
                        "file_count": 0, "size_bytes": 0, "color": color_for(fname, mime),
                        "percent": 0,
                    }
                ext_map[ext]["file_count"] += 1
                ext_map[ext]["size_bytes"] += size

                # duplicates: group by (name, size)
                if doc:
                    key = (fname, size)
                    dup_map.setdefault(key, []).append({
                        "message_id": msg.id, "folder_name": name, "created_at": msg.date,
                    })

            folder_stats.append({"id": fid, "name": name, "file_count": folder_count, "size_bytes": folder_size})

        for item in ext_map.values():
            item["percent"] = round(item["size_bytes"] / total_size * 100, 1) if total_size else 0
        ext_types = sorted(ext_map.values(), key=lambda x: x["size_bytes"], reverse=True)

        duplicates = [
            {"name": k[0], "size": k[1], "files": v}
            for k, v in dup_map.items() if len(v) > 1
        ]

        stats = {
            "total_storage_used_bytes": total_size,
            "total_file_count": total_count,
            "folders": folder_stats,
            "mime_types": ext_types,
        }
    except Exception as e:
        pass

    donut_percent = 25
    if stats["total_storage_used_bytes"] and stats.get("mime_types"):
        donut_percent = min(100, sum(i["percent"] for i in stats["mime_types"]))

    context = {
        "request": request,
        "title": "Phân tích Lưu trữ",
        "stats": stats,
        "duplicates": duplicates,
        "donut_percent": donut_percent,
    }
    return templates.TemplateResponse("storage/index.html", context)
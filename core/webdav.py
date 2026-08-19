"""
WebDAV server implementation mapped to Telegram Drive (Saved Messages + [TD] channels).
Mirrors Old_Project webdav.rs.

Path mapping:
  /webdav/{token}/                 -> root (lists Saved Messages + folders)
  /webdav/{token}/Saved Messages/  -> Saved Messages files
  /webdav/{token}/{folder}/        -> channel folder files
  /webdav/{token}/{folder}/{file}  -> file download
  /webdav/{token}/{folder}/{file}  -> PUT to upload
"""
import hashlib
import secrets
import time
from typing import Optional, Dict, List
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse

from core.telegram_client import telegram_manager
from core.streaming import build_media_response
from api.folders.catalog import clean_folder_name
from telethon.tl.types import Channel, MessageMediaDocument, MessageMediaPhoto

router = APIRouter(prefix="/webdav", tags=["WebDAV"])

WEBDAV_TOKEN = secrets.token_hex(32) if False else "telegram-drive-webdav"  # default token


def verify_token(token: str) -> bool:
    """Constant-time token check. Token passed in URL path."""
    return secrets.compare_digest(token, WEBDAV_TOKEN)


async def dav_client(request: Request):
    """Resolve the current user's Telegram client for WebDAV. Raises HTTP on failure."""
    user = getattr(request.state, "current_user", None)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    uid = user.id
    ok = await telegram_manager.ensure_connected(uid)
    if not ok or not telegram_manager.is_connected(uid):
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")
    client = telegram_manager._get_session(uid).client
    if not client:
        raise HTTPException(status_code=503, detail="Telegram client không khả dụng")
    return client


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def propfind_response(depth: int, path: str, children: List[Dict]) -> str:
    """Generate a minimal WebDAV multistatus PROPFIND response."""
    items = []

    # Self item
    if path.startswith("/"):
        p = path
    else:
        p = f"/{path}"
    items.append({
        "href": p,
        "is_dir": True,
        "size": 0,
        "modified": time.time(),
    })

    for child in children:
        items.append(child)

    xml = ['<?xml version="1.0" encoding="utf-8"?>', '<D:multistatus xmlns:D="DAV:">']
    for item in items:
        href = xml_escape(item["href"])
        is_dir = "true" if item.get("is_dir") else "false"
        size = item.get("size", 0)
        modified = item.get("modified", 0)
        xml.append(f"""<D:response>
  <D:href>{href}</D:href>
  <D:propstat>
    <D:prop>
      <D:displayname>{xml_escape(item.get('displayname', href.split('/')[-1]))}</D:displayname>
      <D:resourcetype>{'<D:collection/>' if item.get('is_dir') else ''}</D:resourcetype>
      <D:getcontentlength>{size}</D:getcontentlength>
      <D:getlastmodified>{time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(modified))}</D:getlastmodified>
    </D:prop>
    <D:status>HTTP/1.1 200 OK</D:status>
  </D:propstat>
</D:response>""")
    xml.append("</D:multistatus>")
    return "\n".join(xml)


async def list_peer_files(client, peer) -> List[Dict]:
    """List files in a peer, returning WebDAV-style entries."""
    entries = []
    async for msg in client.iter_messages(peer):
        if not msg.media:
            continue

        doc = msg.document
        if doc:
            filename = "Unknown"
            if doc.attributes:
                for attr in doc.attributes:
                    fn = getattr(attr, "file_name", None)
                    if fn:
                        filename = fn
                        break
            display_name = msg.text.strip() if msg.text and msg.text.strip() else filename
            entries.append({
                "href": f"{display_name}",
                "is_dir": False,
                "size": doc.size,
                "modified": msg.date.timestamp() if msg.date else 0,
                "displayname": display_name,
                "message_id": msg.id,
                "document": doc,
                "msg": msg,
            })
        elif msg.photo:
            entries.append({
                "href": f"Photo_{msg.id}.jpg",
                "is_dir": False,
                "size": 0,
                "modified": msg.date.timestamp() if msg.date else 0,
                "displayname": f"Photo_{msg.id}.jpg",
                "message_id": msg.id,
                "document": None,
                "msg": msg,
            })
    return entries


@router.api_route("/{token}", methods=["OPTIONS"])
async def dav_options(token: str, request: Request):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return Response(
        status_code=200,
        headers={
            "DAV": "1,2",
            "Allow": "OPTIONS, PROPFIND, GET, MKCOL, PUT, DELETE, MOVE, COPY",
            "MS-Author-Via": "DAV",
        },
    )


@router.api_route("/{token}/", methods=["PROPFIND"])
@router.api_route("/{token}/{path:path}", methods=["PROPFIND"])
async def dav_propfind(token: str, request: Request, path: str = ""):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    client = await dav_client(request)
    depth = request.headers.get("Depth", "1")

    # Path = "" -> root; "Saved Messages" -> home; "{folder}" -> channel
    segments = [s for s in path.split("/") if s]
    children = []

    if not segments:
        # Root: Saved Messages + [TD] channels
        if depth != "0":
            me = await client.get_me()
            if me:
                children.append({
                    "href": "Saved Messages/",
                    "is_dir": True,
                    "size": 0,
                    "modified": 0,
                    "displayname": "Saved Messages",
                })
            async for dialog in client.iter_dialogs():
                e = dialog.entity
                if isinstance(e, Channel) and "[td]" in getattr(e, "title", "").lower():
                    children.append({
                        "href": f"{clean_folder_name(e.title)}/",
                        "is_dir": True,
                        "size": 0,
                        "modified": 0,
                        "displayname": clean_folder_name(e.title),
                    })
    elif len(segments) == 1:
        # Single folder (Saved Messages or a channel name)
        folder_name = segments[0]
        peer = None
        if folder_name.lower() == "saved messages":
            peer = await client.get_me()
        else:
            # Find channel by clean name
            async for dialog in client.iter_dialogs():
                e = dialog.entity
                if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == folder_name.lower():
                    peer = e
                    break
        if peer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")

        if depth != "0":
            entries = await list_peer_files(client, peer)
            for entry in entries:
                children.append({
                    "href": f"{folder_name}/{entry['href']}",
                    "is_dir": False,
                    "size": entry["size"],
                    "modified": entry["modified"],
                    "displayname": entry["displayname"],
                    "message_id": entry["message_id"],
                    "document": entry["document"],
                    "msg": entry["msg"],
                })
    else:
        # file path: /{folder}/{filename}
        folder_name = segments[0]
        file_name = segments[1]
        peer = None
        if folder_name.lower() == "saved messages":
            peer = await client.get_me()
        else:
            async for dialog in client.iter_dialogs():
                e = dialog.entity
                if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == folder_name.lower():
                    peer = e
                    break
        if peer is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")
        entries = await list_peer_files(client, peer)
        for entry in entries:
            if entry["displayname"] == file_name:
                children.append({
                    "href": f"{folder_name}/{file_name}",
                    "is_dir": False,
                    "size": entry["size"],
                    "modified": entry["modified"],
                    "displayname": entry["displayname"],
                    "message_id": entry["message_id"],
                    "document": entry["document"],
                    "msg": entry["msg"],
                })

    xml = propfind_response(depth, "/".join(segments), children)
    return Response(
        content=xml,
        status_code=207,
        media_type="application/xml; charset=utf-8",
        headers={"DAV": "1,2"},
    )


@router.api_route("/{token}/{path:path}", methods=["GET"])
async def dav_get(token: str, request: Request, path: str = ""):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    client = await dav_client(request)
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2:
        raise HTTPException(status_code=400, detail="Phải chỉ định thư mục và tên file")

    folder_name = segments[0]
    file_name = segments[1]

    peer = None
    if folder_name.lower() == "saved messages":
        peer = await client.get_me()
    else:
        async for dialog in client.iter_dialogs():
            e = dialog.entity
            if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == folder_name.lower():
                peer = e
                break
    if peer is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")

    entries = await list_peer_files(client, peer)
    for entry in entries:
        if entry["displayname"] == file_name:
            doc = entry.get("document")
            msg = entry.get("msg")
            if doc:
                mime = doc.mime_type or "application/octet-stream"
                return build_media_response(request, client, doc, mime_type=mime, filename=file_name)
            if msg and msg.photo:
                # Stream photo
                import io
                data = await client.download_media(msg.photo, file=bytes)
                return Response(content=data, media_type="image/jpeg")

    raise HTTPException(status_code=404, detail="Không tìm thấy file")


@router.api_route("/{token}/{path:path}", methods=["MKCOL"])
async def dav_mkcol(token: str, request: Request, path: str = ""):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")

    segments = [s for s in path.split("/") if s]
    if len(segments) == 0:
        raise HTTPException(status_code=400, detail="Phải chỉ định tên thư mục")

    folder_name = segments[0]
    client = await dav_client(request)
    from telethon.tl.functions.channels import CreateChannelRequest
    from telethon.tl.functions.messages import SetHistoryTTLRequest

    try:
        result = await client(CreateChannelRequest(
            title=f"{folder_name} [TD]",
            about="Telegram Drive Storage Folder\n[telegram-drive-folder]",
            broadcast=True,
            megagroup=False,
        ))
        channel = result.chats[0]
        try:
            await client(SetHistoryTTLRequest(peer=channel, period=0))
        except Exception:
            pass
        return Response(status_code=201)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo thư mục: {e}")


@router.api_route("/{token}/{path:path}", methods=["PUT"])
async def dav_put(token: str, request: Request, path: str = ""):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")

    segments = [s for s in path.split("/") if s]
    if len(segments) < 2:
        raise HTTPException(status_code=400, detail="Phải chỉ định thư mục và tên file")

    folder_name = segments[0]
    file_name = segments[-1]

    client = await dav_client(request)
    peer = None
    if folder_name.lower() == "saved messages":
        peer = await client.get_me()
    else:
        async for dialog in client.iter_dialogs():
            e = dialog.entity
            if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == folder_name.lower():
                peer = e
                break
    if peer is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")

    # Read body and upload
    import tempfile
    import os
    body = await request.body()
    temp_path = os.path.join(tempfile.gettempdir(), f"webdav_{file_name}")
    try:
        with open(temp_path, "wb") as f:
            f.write(body)
        uploaded = await client.upload_file(temp_path, file_name=file_name)
        await client.send_file(peer, uploaded, caption="", force_document=True)
        return Response(status_code=201)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi upload: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.api_route("/{token}/{path:path}", methods=["DELETE"])
async def dav_delete(token: str, request: Request, path: str = ""):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")

    segments = [s for s in path.split("/") if s]
    if not segments:
        raise HTTPException(status_code=400, detail="Phải chỉ định nội dung cần xóa")

    client = await dav_client(request)

    if len(segments) == 1:
        # Delete folder (channel)
        folder_name = segments[0]
        from telethon.tl.functions.channels import DeleteChannelRequest
        async for dialog in client.iter_dialogs():
            e = dialog.entity
            if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == folder_name.lower():
                await client(DeleteChannelRequest(channel=e))
                return Response(status_code=204)
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")

    # Delete file
    folder_name = segments[0]
    file_name = segments[1]
    peer = None
    if folder_name.lower() == "saved messages":
        peer = await client.get_me()
    else:
        async for dialog in client.iter_dialogs():
            e = dialog.entity
            if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == folder_name.lower():
                peer = e
                break
    if peer is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")

    entries = await list_peer_files(client, peer)
    for entry in entries:
        if entry["displayname"] == file_name:
            await client.delete_messages(peer, [entry["message_id"]])
            return Response(status_code=204)

    raise HTTPException(status_code=404, detail="Không tìm thấy file")


@router.api_route("/{token}/{path:path}", methods=["MOVE"])
async def dav_move(token: str, request: Request, path: str = ""):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")

    dest_header = request.headers.get("Destination", "")
    # Extract path after /webdav/{token}/
    if "/webdav/" in dest_header:
        dest = dest_header.split("/webdav/")[1]
        # Remove token
        dest_parts = dest.split("/", 1)
        if len(dest_parts) > 1:
            dest = dest_parts[1]
        else:
            dest = ""
    else:
        dest = ""

    segments_src = [s for s in path.split("/") if s]
    segments_dst = [s for s in dest.split("/") if s]

    if len(segments_src) < 1:
        raise HTTPException(status_code=400, detail="Phải chỉ định nội dung di chuyển")

    client = await dav_client(request)

    # Rename folder
    if len(segments_src) == 1:
        old_name = segments_src[0]
        new_name = segments_dst[-1] if segments_dst else old_name
        from telethon.tl.functions.channels import EditTitleRequest
        async for dialog in client.iter_dialogs():
            e = dialog.entity
            if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == old_name.lower():
                await client(EditTitleRequest(channel=e, title=f"{new_name} [TD]"))
                return Response(status_code=201)
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")

    # Move/rename file
    src_folder = segments_src[0]
    src_file = segments_src[1]
    dst_folder = segments_dst[0] if segments_dst else src_folder
    dst_file = segments_dst[-1] if len(segments_dst) >= 2 else src_file

    src_peer = await _resolve_peer_by_name(client, src_folder)
    if src_peer is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục nguồn")

    # Find message id
    entries = await list_peer_files(client, src_peer)
    target_msg = None
    for entry in entries:
        if entry["displayname"] == src_file:
            target_msg = entry["msg"]
            break
    if target_msg is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")

    # If same folder -> rename (edit caption)
    if dst_folder.lower() == src_folder.lower():
        await client.edit_message(src_peer, target_msg.id, text=dst_file)
        return Response(status_code=201)

    # Different folder -> forward + delete + rename
    dst_peer = await _resolve_peer_by_name(client, dst_folder)
    if dst_peer is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục đích")

    fwd = await client.forward_messages(dst_peer, target_msg.id, from_peer=src_peer)
    await client.delete_messages(src_peer, [target_msg.id])
    if fwd and (isinstance(fwd, list) and fwd) or not isinstance(fwd, list):
        new_id = fwd[0].id if isinstance(fwd, list) else fwd.id
        if dst_file != src_file:
            await client.edit_message(dst_peer, new_id, text=dst_file)
    return Response(status_code=201)


async def _resolve_peer_by_name(client, folder_name: str):
    """Resolve a peer by folder name (Saved Messages or channel)."""
    if folder_name.lower() == "saved messages":
        return await client.get_me()
    async for dialog in client.iter_dialogs():
        e = dialog.entity
        if isinstance(e, Channel) and clean_folder_name(getattr(e, "title", "")).lower() == folder_name.lower():
            return e
    return None
"""Socket.IO server for real-time notifications.

Clients connect with {auth: {token: <access token>}} and join a per-user room.
Sync code (routes/services running in the threadpool) emits via emit_to_user,
which schedules the coroutine on the main event loop captured at startup.
"""

import asyncio
import logging

import socketio

from app.core.config import settings
from app.core.security import decode_token

log = logging.getLogger("weta.socket")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=settings.cors_origin_list or "*")

_loop: asyncio.AbstractEventLoop | None = None


def capture_loop() -> None:
    global _loop
    _loop = asyncio.get_running_loop()


@sio.event
async def connect(sid, environ, auth):
    token = (auth or {}).get("token", "")
    payload = decode_token(token, "access")
    if not payload:
        raise socketio.exceptions.ConnectionRefusedError("authentication failed")
    await sio.enter_room(sid, f"user:{payload['sub']}")


def emit_to_user(user_id: str, event: str, data: dict) -> None:
    if _loop is None or _loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(sio.emit(event, data, room=f"user:{user_id}"), _loop)
    except RuntimeError:
        log.debug("Socket emit skipped; event loop unavailable")

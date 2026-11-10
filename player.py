import platform
import subprocess
import asyncio
from datetime import datetime, timezone


def _playerctl(*args):
    try:
        result = subprocess.run(
            ["playerctl", *args],
            capture_output=True,
            text=True,
            timeout=2
        )
        return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_linux_song():
    status = _playerctl("status")

    if status not in ("Playing", "Paused"):
        return None

    title = _playerctl("metadata", "--format", "{{title}}")
    artist = _playerctl("metadata", "--format", "{{artist}}")

    if not title or not artist:
        return None

    try:
        position = float(_playerctl("position") or 0)
    except ValueError:
        position = 0.0

    return {
        "title": title,
        "artist": artist,
        "album": _playerctl("metadata", "--format", "{{album}}"),
        "status": status,
        "paused": status == "Paused",
        "position": position,
    }

def _windows_position(session, playing):
    """Current position in seconds for an SMTC session."""
    timeline = session.get_timeline_properties()
    position = timeline.position.total_seconds()

    if playing:
        updated = timeline.last_updated_time
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - updated).total_seconds()
        if elapsed > 0:
            position += elapsed
            
    end = timeline.end_time.total_seconds()
    if end > 0:
        position = min(position, end)

    return max(0.0, position)


async def get_windows_song_async():
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager
    )

    manager = await Manager.request_async()
    sessions = manager.get_sessions()

    paused_candidate = None

    for session in sessions:
        info = session.get_playback_info()
        status = str(info.playback_status).split(".")[-1]

        if status not in ("PLAYING", "PAUSED"):
            continue

        media = await session.try_get_media_properties_async()

        if not media.title:
            continue

        playing = status == "PLAYING"

        song = {
            "title": media.title,
            "artist": media.artist,
            "album": media.album_title,
            "status": "Playing" if playing else "Paused",
            "paused": not playing,
            "position": _windows_position(session, playing),
        }

        if playing:
            return song
        if paused_candidate is None:
            paused_candidate = song

    return paused_candidate


def get_current_song():
    system = platform.system()

    if system == "Linux":
        return get_linux_song()

    elif system == "Windows":
        try:
            return asyncio.run(get_windows_song_async())
        except Exception as e:
            print("Windows media error:", e)
            return None

    return None
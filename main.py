import re
import time

import requests
from flask import Flask, jsonify, render_template

from player import get_current_song

app = Flask(__name__)

last_track = None
last_lyrics = None

HEADERS = {"User-Agent": "MusicLyricsApp/1.0"}


# ---------- lyrics ----------

def get_lyrics(artist, title):
    global last_track, last_lyrics

    track = (artist, title)

    if track == last_track:
        return last_lyrics

    clean_title = re.sub(
        r'\s*[\(\[].*?(sped up|nightcore|slowed|remix|edit|version).*?[\)\]]',
        '',
        title,
        flags=re.IGNORECASE
    ).strip()

    clean_title = re.sub(
        r'\s*[-–]\s*(sped up|nightcore|slowed|remix).*?$',
        '',
        clean_title,
        flags=re.IGNORECASE
    ).strip()

    candidates = list(dict.fromkeys([
        (artist, title),
        (artist, clean_title),
        ("girl in red", clean_title)
        if artist.lower() == "marie ulven"
        else (artist, clean_title)
    ]))

    synced = None
    plain = None

    for search_artist, search_title in candidates:
        try:
            # First try exact lookup
            response = requests.get(
                "https://lrclib.net/api/get",
                params={
                    "artist_name": search_artist,
                    "track_name": search_title
                },
                headers=HEADERS,
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                synced = synced or data.get("syncedLyrics")
                plain = plain or data.get("plainLyrics")

            # Fallback to search (only if we still have no synced lyrics)
            if not synced:
                response = requests.get(
                    "https://lrclib.net/api/search",
                    params={
                        "artist_name": search_artist,
                        "track_name": search_title
                    },
                    headers=HEADERS,
                    timeout=5
                )

                if response.status_code == 200:
                    for result in response.json():
                        if (
                            result.get("trackName", "").strip().lower()
                            == search_title.strip().lower()
                        ):
                            if result.get("syncedLyrics"):
                                synced = result["syncedLyrics"]
                                break
                            plain = plain or result.get("plainLyrics")

            if synced:
                break

        except requests.RequestException as e:
            print("Lyrics API error:", e)

    lyrics = synced or plain

    last_track = track
    last_lyrics = lyrics

    return lyrics


# ---------- playback position ----------

clock = {"track": None, "pos": 0.0, "wall": 0.0, "paused": False}


def synced_position(song):
    """Use the player's position if it looks real, otherwise run our own clock."""
    now = time.time()
    track = (song["artist"], song["title"])
    reported = song.get("position") or 0.0

    if clock["track"] != track:
        # new song: start from the reported position (~0 if the player lies)
        clock.update(track=track, pos=reported, wall=now)
    else:
        if not clock["paused"]:
            clock["pos"] += now - clock["wall"]   # advance by real elapsed time
        clock["wall"] = now
        if reported > 1.0:                        # player gave a believable value
            clock["pos"] = reported               # trust it (handles seeking)

    clock["paused"] = bool(song.get("paused"))
    return clock["pos"]


# ---------- routes ----------

@app.route("/")
def index():
    return render_template("home.html")


@app.route("/api/current")
def current():
    song = get_current_song()

    if not song:
        clock["track"] = None   # so the next play starts the clock fresh
        return jsonify({"playing": False})

    lyrics = get_lyrics(song["artist"], song["title"])

    song["position"] = synced_position(song)

    return jsonify({
        "playing": True,
        **song,
        "lyrics": lyrics
    })


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
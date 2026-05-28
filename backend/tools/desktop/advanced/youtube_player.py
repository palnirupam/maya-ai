"""
Maya AI — Background YouTube Audio Player
Plays YouTube audio in the background using VLC Media Player and yt-dlp.
No browser is opened, no advertisements are played.
"""
import os
import subprocess
import logging
import psutil

logger = logging.getLogger(__name__)

VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
PID_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "youtube_player.pid"))


def _kill_existing_player() -> None:
    """Kills any previously spawned background VLC player if one is running."""
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            # Only kill VLC processes — safety check
            if "vlc" in proc.name().lower():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
                logger.info(f"Killed existing VLC player (PID {pid})")
    except Exception as e:
        logger.warning(f"Could not kill existing player: {e}")
    finally:
        try:
            os.remove(PID_FILE)
        except Exception:
            pass


def _save_pid(pid: int) -> None:
    """Saves the VLC process PID to a file so it can be stopped later."""
    try:
        os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(pid))
    except Exception as e:
        logger.warning(f"Could not save VLC PID: {e}")


def play_youtube_background(query: str) -> str:
    """
    Plays a YouTube song or audio in the background without opening a web browser.
    No advertisements are played. Uses VLC Media Player as the audio engine.
    Args:
        query (str): Song name, artist, or YouTube URL to search and play (e.g. 'Arijit Singh tum hi ho' or 'lofi hip hop').
    """
    import yt_dlp

    if not os.path.exists(VLC_PATH):
        return (
            "ERROR: VLC Media Player is not found at the expected path. "
            "Please ensure VLC is installed."
        )

    # Stop any song that is currently playing
    _kill_existing_player()

    # Determine if the query is a direct URL or a search query
    if query.startswith("http://") or query.startswith("https://"):
        search_query = query
    else:
        search_query = f"ytsearch:{query}"

    logger.info(f"Searching YouTube for: {query}")

    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": False,
        "default_search": "ytsearch",
        "skip_download": True,
    }

    stream_url = None
    video_title = query

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)

            # If it's a search result, get the first item
            if "entries" in info and info["entries"]:
                info = info["entries"][0]

            video_title = info.get("title", query)

            # Get the best audio URL from formats
            formats = info.get("formats", [])

            # Try to get audio-only format first
            audio_formats = [
                f for f in formats
                if f.get("acodec") not in (None, "none")
                and f.get("vcodec") in (None, "none", "")
                and f.get("url")
            ]

            if audio_formats:
                # Pick best bitrate audio-only
                audio_formats.sort(key=lambda x: x.get("abr") or 0, reverse=True)
                stream_url = audio_formats[0]["url"]
            else:
                # Fallback: use the best overall format's URL
                best_formats = [f for f in formats if f.get("url")]
                if best_formats:
                    stream_url = best_formats[-1]["url"]

            if not stream_url:
                stream_url = info.get("url")

    except Exception as e:
        logger.error(f"yt-dlp extraction failed: {e}")
        return f"ERROR: Could not find '{query}' on YouTube. {e}"

    if not stream_url:
        return f"ERROR: Could not extract audio stream for '{query}'."

    # Launch VLC in dummy (headless) interface — no window, no video
    try:
        vlc_cmd = [
            VLC_PATH,
            "--intf", "dummy",        # No GUI
            "--no-video",             # Audio only
            "--no-loop",              # Don't loop
            "--no-repeat",            # Don't repeat
            "--play-and-exit",        # Exit VLC when done
            stream_url,
        ]
        proc = subprocess.Popen(
            vlc_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,  # Completely hidden on Windows
        )
        _save_pid(proc.pid)
        logger.info(f"VLC started (PID {proc.pid}), playing: {video_title}")
        return f"SUCCESS: Now playing '{video_title}' in the background. No browser opened, no ads."
    except Exception as e:
        logger.error(f"Failed to start VLC: {e}")
        return f"ERROR: VLC could not start. {e}"


def stop_youtube_background() -> str:
    """
    Stops the currently playing background YouTube audio that was started by play_youtube_background.
    """
    if not os.path.exists(PID_FILE):
        return "No background audio is currently playing."

    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())

        if not psutil.pid_exists(pid):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
            return "No background audio is currently playing (player had already stopped)."

        proc = psutil.Process(pid)
        if "vlc" not in proc.name().lower():
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
            return "No VLC background player was found."

        proc.terminate()
        try:
            proc.wait(timeout=3)
        except psutil.TimeoutExpired:
            proc.kill()

        try:
            os.remove(PID_FILE)
        except Exception:
            pass

        logger.info(f"Stopped background VLC player (PID {pid})")
        return "SUCCESS: Background audio stopped."

    except Exception as e:
        logger.error(f"Could not stop background player: {e}")
        return f"ERROR: Could not stop background audio. {e}"

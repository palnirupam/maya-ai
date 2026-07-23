"""
benchmark_embeddings.py — backend/scripts/benchmark_embeddings.py

Benchmarks embedding model quality for tool routing using near-miss top-k
evaluation. Unlike binary pairwise testing, near-miss tests check that the
correct intent ranks HIGHER than a similar (but wrong) intent — the real
failure mode in production.

Architecture spec (NEXUS Definitive Architecture):
  - Minimum 100 test cases (covers all OS_PATTERN categories)
  - Each case: (query, correct_intent, near_miss_intent)
  - Pass condition: correct ranks higher than near_miss in cosine similarity
  - Deployment thresholds:
      accuracy      >= 90%    (near-miss top-k)
      p50_latency   <= 20ms
      p95_latency   <= 50ms

Usage:
  python backend/scripts/benchmark_embeddings.py
  python backend/scripts/benchmark_embeddings.py --model nomic-embed-text
  python backend/scripts/benchmark_embeddings.py --verbose --top 20
"""

import sys
import time
import argparse
import math
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── Near-miss test cases ──────────────────────────────────────────────────────
# Format: (query, correct_intent, near_miss_intent)
# Near-miss = same domain, different action — the hard cases that production hits.
BANGLISH_TEST_CASES = [
    # WiFi
    ("wifi on koro",          "wifi_enable",        "wifi_disable"),
    ("wifi off koro",         "wifi_disable",       "wifi_enable"),
    ("wifi list dekhao",      "wifi_scan",          "wifi_enable"),
    ("wifi connect koro",     "wifi_connect",       "wifi_scan"),
    ("wifi disconnect koro",  "wifi_disconnect",    "wifi_connect"),
    ("wifi status",           "wifi_status",        "wifi_scan"),
    # Volume
    ("volume 50 koro",        "volume_set",         "volume_mute"),
    ("volume mute koro",      "volume_mute",        "volume_set"),
    ("volume unmute koro",    "volume_unmute",      "volume_mute"),
    ("volume baro",           "volume_increase",    "volume_decrease"),
    ("volume komo",           "volume_decrease",    "volume_increase"),
    # Brightness
    ("brightness baro",       "brightness_increase","brightness_decrease"),
    ("brightness komo",       "brightness_decrease","brightness_increase"),
    ("brightness 70 percent", "brightness_set",     "brightness_increase"),
    # Bluetooth
    ("bluetooth on koro",     "bt_enable",          "bt_disable"),
    ("bluetooth off koro",    "bt_disable",         "bt_enable"),
    ("bluetooth er list dao", "bt_list",            "bt_enable"),
    ("bluetooth connect koro","bt_connect",         "bt_list"),
    ("bluetooth remove koro", "bt_remove",          "bt_connect"),
    ("bluetooth status",      "bt_status",          "bt_list"),
    # Apps
    ("chrome kholo",          "open_app",           "close_app"),
    ("chrome bondho koro",    "close_app",          "open_app"),
    ("notepad open koro",     "open_app",           "focus_app"),
    ("vscode focus koro",     "focus_app",          "open_app"),
    # System
    ("screenshot nao",        "screenshot",         "screen_reader"),
    ("battery koto ache",     "battery_status",     "system_stats"),
    ("ram usage dekhao",      "system_stats",       "battery_status"),
    ("cpu usage dekhao",      "system_stats",       "process_list"),
    ("process list dekhao",   "process_list",       "system_stats"),
    ("notepad kill koro",     "process_kill",       "close_app"),
    # Clipboard
    ("clipboard ta dekhao",   "clipboard_read",     "clipboard_write"),
    ("clipboard e likho",     "clipboard_write",    "clipboard_read"),
    # Network
    ("network status",        "network_status",     "wifi_status"),
    ("ip address dekhao",     "network_status",     "wifi_status"),
    # Power
    ("sleep mode e jao",      "sleep",              "shutdown"),
    ("hibernate koro",        "hibernate",          "sleep"),
    ("lock screen koro",      "lock",               "sleep"),
    # File operations
    ("file ta copy koro",     "file_copy",          "file_move"),
    ("file ta move koro",     "file_move",          "file_copy"),
    ("file ta delete koro",   "file_delete",        "file_move"),
    ("file ta rename koro",   "file_rename",        "file_move"),
    ("folder banao",          "mkdir",              "file_copy"),
    ("file search koro",      "file_search",        "file_copy"),
    ("file open koro",        "file_open",          "file_search"),
    # PC control
    ("pc stats dekhao",       "system_stats",       "battery_status"),
    ("taskbar dekhao",        "process_list",       "system_stats"),
    # Email (basic)
    ("email pathao",          "send_email",         "draft_email"),
    ("email draft koro",      "draft_email",        "send_email"),
    # Calendar
    ("meeting add koro",      "calendar_add",       "calendar_list"),
    ("meetings dekhao",       "calendar_list",      "calendar_add"),
    # Voice
    ("speak koro",            "tts_speak",          "tts_stop"),
    ("bolা bondho koro",      "tts_stop",           "tts_speak"),
    # Search
    ("google search koro",    "web_search",         "news_search"),
    ("news search koro",      "news_search",        "web_search"),
    # Additional Banglish variants
    ("wifi ta on kore dao",   "wifi_enable",        "wifi_disable"),
    ("volume ta mute kore dao","volume_mute",       "volume_set"),
    ("brightness ta kora",    "brightness_decrease","brightness_increase"),
    ("chrome ta khola",       "open_app",           "close_app"),
    ("screenshot ta nao",     "screenshot",         "screen_reader"),
    ("bt on koro",            "bt_enable",          "bt_list"),
    ("bt list dao",           "bt_list",            "bt_enable"),
    ("ram ta dekhao",         "system_stats",       "battery_status"),
    ("clipboard read koro",   "clipboard_read",     "clipboard_write"),
    ("network check koro",    "network_status",     "wifi_status"),
    ("file move kore dao",    "file_move",          "file_copy"),
    ("folder create koro",    "mkdir",              "file_search"),
    ("email send koro",       "send_email",         "draft_email"),
    ("calendar add koro",     "calendar_add",       "calendar_list"),
    ("tts bolao",             "tts_speak",          "tts_stop"),
    ("web search dao",        "web_search",         "news_search"),
    ("wifi er status",        "wifi_status",        "network_status"),
    ("volume level set koro", "volume_set",         "volume_mute"),
    ("screen lock koro",      "lock",               "sleep"),
    ("file rename kore dao",  "file_rename",        "file_copy"),
    # Hard near-misses (same words, different intent direction)
    ("bluetooth ta on koro",  "bt_enable",          "bt_disable"),
    ("wifi ta off koro",      "wifi_disable",       "wifi_enable"),
    ("brightness ta baro",    "brightness_increase","brightness_decrease"),
    ("volume ta koma",        "volume_decrease",    "volume_increase"),
    ("sleep e jao",           "sleep",              "hibernate"),
    ("file copy kore dao",    "file_copy",          "file_move"),
    ("google e search koro",  "web_search",         "news_search"),
    ("process ta kill koro",  "process_kill",       "close_app"),
    ("mail draft banao",      "draft_email",        "send_email"),
    ("events dekhao",         "calendar_list",      "calendar_add"),
    ("pc lock koro",          "lock",               "sleep"),
    ("music play koro",       "media_play",         "media_pause"),
    ("music pause koro",      "media_pause",        "media_play"),
    ("music stop koro",       "media_stop",         "media_pause"),
    ("next song jao",         "media_next",         "media_previous"),
    ("previous song jao",     "media_previous",     "media_next"),
    ("window maximize koro",  "window_maximize",    "window_minimize"),
    ("window minimize koro",  "window_minimize",    "window_maximize"),
    ("desktop dekhao",        "show_desktop",       "window_maximize"),
    ("taskbar hide koro",     "taskbar_hide",       "taskbar_show"),
    ("taskbar show koro",     "taskbar_show",       "taskbar_hide"),
    ("dark mode on koro",     "theme_dark",         "theme_light"),
    ("light mode on koro",    "theme_light",        "theme_dark"),
    ("notification off koro", "notif_disable",      "notif_enable"),
    ("notification on koro",  "notif_enable",       "notif_disable"),
    ("do not disturb on",     "dnd_enable",         "dnd_disable"),
    ("do not disturb off",    "dnd_disable",        "dnd_enable"),
]

# ── Deployment thresholds ────────────────────────────────────────────────────
THRESHOLDS = {
    "accuracy":       0.90,
    "p50_latency_ms": 20.0,
    "p95_latency_ms": 50.0,
}


def _cosine(a: list, b: list) -> float:
    """Fast cosine similarity for two equal-length float lists."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _try_sentence_transformers(model_name: str):
    """Try to load a local SentenceTransformer model."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        def encode(text: str) -> list:
            return model.encode(text).tolist()
        return encode
    except ImportError:
        return None
    except Exception as e:
        print(f"[WARN] Could not load SentenceTransformer model '{model_name}': {e}")
        return None


def _try_gemini_embeddings():
    """Try to use the Gemini embedding API as fallback."""
    try:
        from backend.brain.memory.long_term_memory import _get_embedding
        def encode(text: str) -> list:
            result = _get_embedding(text)
            if result is None:
                raise RuntimeError("Gemini embedding returned None")
            return result
        return encode
    except Exception as e:
        print(f"[WARN] Could not load Gemini embeddings: {e}")
        return None


def benchmark(encoder_fn, cases: list, verbose: bool = False, top: int = None) -> dict:
    """Run the near-miss benchmark and return results."""
    if top:
        cases = cases[:top]

    correct = 0
    latencies = []

    for query, correct_intent, near_miss in cases:
        t0 = time.perf_counter()
        q_vec  = encoder_fn(query)
        c_vec  = encoder_fn(correct_intent)
        nm_vec = encoder_fn(near_miss)
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        score_c  = _cosine(q_vec, c_vec)
        score_nm = _cosine(q_vec, nm_vec)
        ok = score_c > score_nm
        if ok:
            correct += 1

        if verbose:
            sym = "PASS" if ok else "FAIL"
            print(
                f"  [{sym}] {query:<30} "
                f"correct={score_c:.3f}  near_miss={score_nm:.3f}  "
                f"({latency_ms:.1f}ms)"
            )

    total = len(cases)
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[total // 2]
    p95 = latencies_sorted[int(total * 0.95)]
    accuracy = correct / total

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
    }


def main():
    parser = argparse.ArgumentParser(description="Embedding model near-miss benchmark.")
    parser.add_argument("--model", default="all-MiniLM-L6-v2",
                        help="SentenceTransformer model name (default: all-MiniLM-L6-v2)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--top", type=int, default=None,
                        help="Limit to first N test cases (default: all)")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  Embedding Benchmark - {args.model}")
    print(f"  Test cases: {args.top or len(BANGLISH_TEST_CASES)}")
    print(f"{'='*65}\n")

    # Try SentenceTransformers first, fall back to Gemini API
    encoder = _try_sentence_transformers(args.model)
    if encoder is None:
        print(f"[INFO] SentenceTransformers not available. Trying Gemini embedding API...")
        encoder = _try_gemini_embeddings()

    if encoder is None:
        print(
            "[ERROR] No encoder available.\n"
            "  Install sentence-transformers:  pip install sentence-transformers\n"
            "  Or ensure Gemini API key is configured."
        )
        sys.exit(1)

    if args.verbose:
        print(f"  {'Query':<30} {'Correct':>8}  {'Near-Miss':>10}  Latency\n  {'-'*65}")

    results = benchmark(encoder, BANGLISH_TEST_CASES, verbose=args.verbose, top=args.top)

    if args.verbose:
        print()

    acc_pass = results["accuracy"]        >= THRESHOLDS["accuracy"]
    p50_pass = results["p50_latency_ms"]  <= THRESHOLDS["p50_latency_ms"]
    p95_pass = results["p95_latency_ms"]  <= THRESHOLDS["p95_latency_ms"]

    acc_sym  = "[PASS]" if acc_pass  else "[FAIL]"
    p50_sym  = "[PASS]" if p50_pass  else "[FAIL]"
    p95_sym  = "[PASS]" if p95_pass  else "[FAIL]"

    print(f"  {acc_sym}  Accuracy     : {results['accuracy']*100:.1f}%  "
          f"(threshold: {THRESHOLDS['accuracy']*100:.0f}%)")
    print(f"  {p50_sym}  p50 Latency  : {results['p50_latency_ms']:.1f}ms  "
          f"(threshold: {THRESHOLDS['p50_latency_ms']:.0f}ms)")
    print(f"  {p95_sym}  p95 Latency  : {results['p95_latency_ms']:.1f}ms  "
          f"(threshold: {THRESHOLDS['p95_latency_ms']:.0f}ms)")
    print()

    all_pass = acc_pass and p50_pass and p95_pass
    status = "[PASS] Model cleared for deployment." if all_pass else "[FAIL] Do NOT ship this model."
    print(f"  {status}")
    print(f"{'='*65}\n")

    sys.exit(0 if all_pass else 1)



if __name__ == "__main__":
    main()

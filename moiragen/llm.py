"""The one shared brain: a thin client for the local Ollama server.

All minds (Moiragen and the three nanites) use the same gemma3:4b model.
A 6 GB GPU can only think one thought at a time, so a lock makes the
minds take turns: whoever holds the lock is "using the brain".
"""

import threading
import time

import requests

from .config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_REPEAT_LAST_N, OLLAMA_REPEAT_PENALTY

# Only one mind may use the model at a time.
_brain_lock = threading.Lock()

# Seconds to rest before each thought. The body (body.py) raises this when
# the GPU is hot or the battery is low, so the hardware gets a breather.
_cooldown_seconds = 0.0


def set_cooldown(seconds: float) -> None:
    """Called by the body to slow thinking down (0 = full speed)."""
    global _cooldown_seconds
    _cooldown_seconds = max(0.0, float(seconds))


class BrainError(RuntimeError):
    """Raised when Ollama cannot be reached or returns an error."""


def is_awake() -> bool:
    """True if the Ollama server answers."""
    try:
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).ok
    except requests.RequestException:
        return False


def think(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 300,
    system: str | None = None,
    repeat_penalty: float | None = None,
) -> dict:
    """Send a conversation to the model and return its reply.

    messages: a list like [{"role": "user", "content": "Hello"}]
              (roles are "system", "user" or "assistant")
    temperature: 0 = calm and predictable, 1+ = wild and creative.
                 Each nanite gets its own, which is part of its temperament.
    max_tokens: rough cap on reply length.
    system: optional instructions placed before the conversation.
    repeat_penalty: how strongly to avoid words already in the conversation
                    (None = the setting from .env, 1.0 = off). Moiragen's JSON
                    choice uses 1.0, because it must repeat names exactly.

    Note: Ollama has a "format": "json" option, but with gemma3:4b it can
    get stuck repeating tokens, so we ask for JSON in the prompt instead
    and read it carefully (see mother.parse_choice).

    Returns {"text": reply, "seconds": time taken, "waited": time spent
    waiting for another mind to finish}.
    """
    if system:
        messages = [{"role": "system", "content": system}] + messages

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,  # wait for the whole reply (simpler for now)
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "repeat_penalty": OLLAMA_REPEAT_PENALTY if repeat_penalty is None else repeat_penalty,
            "repeat_last_n": OLLAMA_REPEAT_LAST_N,
            "num_ctx": OLLAMA_NUM_CTX,          # v3.6: room for long lessons; nothing is cut
        },
        "keep_alive": "30m",  # keep the model loaded in VRAM between turns
    }

    queued_at = time.time()
    with _brain_lock:  # wait our turn
        if _cooldown_seconds:
            time.sleep(_cooldown_seconds)  # let the GPU cool a little first
        started_at = time.time()
        r = None
        for attempt in (1, 2):  # a hiccup in Ollama gets one retry
            try:
                r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=180)
            except requests.RequestException as e:
                raise BrainError(f"Could not reach Ollama at {OLLAMA_HOST}: {e}") from e
            if r.ok:
                break
            if attempt == 2:
                # Show Ollama's own error message, it says what went wrong.
                raise BrainError(f"Ollama error {r.status_code}: {r.text[:300]}")
            time.sleep(1)
        finished_at = time.time()

    text = r.json()["message"]["content"].strip()
    return {
        "text": text,
        "seconds": round(finished_at - started_at, 2),
        "waited": round(started_at - queued_at, 2),
    }

"""The one shared brain: a thin client for the local Ollama server.

All minds (Moiragen and the three nanites) use the same gemma3:4b model.
A 6 GB GPU can only think one thought at a time, so a lock makes the
minds take turns: whoever holds the lock is "using the brain".
"""

import threading
import time

import requests

from .config import OLLAMA_HOST, OLLAMA_MODEL

# Only one mind may use the model at a time.
_brain_lock = threading.Lock()


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
) -> dict:
    """Send a conversation to the model and return its reply.

    messages: a list like [{"role": "user", "content": "Hello"}]
              (roles are "system", "user" or "assistant")
    temperature: 0 = calm and predictable, 1+ = wild and creative.
                 Each nanite gets its own, which is part of its temperament.
    max_tokens: rough cap on reply length.
    system: optional instructions placed before the conversation.

    Returns {"text": reply, "seconds": time taken, "waited": time spent
    waiting for another mind to finish}.
    """
    if system:
        messages = [{"role": "system", "content": system}] + messages

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,  # wait for the whole reply (simpler for now)
        "options": {"temperature": temperature, "num_predict": max_tokens},
        "keep_alive": "30m",  # keep the model loaded in VRAM between turns
    }

    queued_at = time.time()
    with _brain_lock:  # wait our turn
        started_at = time.time()
        try:
            r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=180)
            r.raise_for_status()
        except requests.RequestException as e:
            raise BrainError(f"Could not reach Ollama at {OLLAMA_HOST}: {e}") from e
        finished_at = time.time()

    text = r.json()["message"]["content"].strip()
    return {
        "text": text,
        "seconds": round(finished_at - started_at, 2),
        "waited": round(started_at - queued_at, 2),
    }

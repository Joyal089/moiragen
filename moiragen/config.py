"""Settings for Moiragen, read once from the .env file.

Every other module imports values from here, so there is one place to
change a setting.
"""

from pathlib import Path
import os

from dotenv import load_dotenv

# The project folder is the parent of this "moiragen" package folder.
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project folder (does nothing if the file is missing).
load_dotenv(PROJECT_DIR / ".env")

# Where Ollama is listening, and which model all minds share.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")

# Keeping the words fresh (see echo.py for the echo loop these help prevent):
#   NANITE_TEMPERATURE_BOOST  added to every nanite's own temperature, so they
#                             are a little more adventurous than at birth
#   OLLAMA_REPEAT_PENALTY     above 1.0 the model avoids words it has already
#                             seen; 1.0 switches it off
#   OLLAMA_REPEAT_LAST_N      how far back it looks for those words
#                             (-1 = the whole prompt, memories included)
NANITE_TEMPERATURE_BOOST = float(os.getenv("NANITE_TEMPERATURE_BOOST", "0.1"))
OLLAMA_REPEAT_PENALTY = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.15"))
OLLAMA_REPEAT_LAST_N = int(os.getenv("OLLAMA_REPEAT_LAST_N", "-1"))

# v3.6: how much text the model may read at once (tokens). Ollama's default (4096) was too
# small for lessons; prompts are never cut. 16384 stays fully on a 6 GB GPU with flash
# attention and a q8_0 KV cache (OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0).
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))

# Memory folder. A relative path like "./memory" is taken relative to the
# project folder, so it works no matter where you start Python from.
_memory = Path(os.getenv("MEMORY_DIR", "./memory"))
MEMORY_DIR = _memory if _memory.is_absolute() else (PROJECT_DIR / _memory).resolve()
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# v3.6: the creator's name, used only in what the minds hear (lessons, prompts). It is
# private, so it lives in the git-ignored .env, never in the code or the docs.
CREATOR = os.getenv("CREATOR_NAME", "").strip() or "the creator"

# The Moiragen folder in Google Drive, for copies of finished backups (see drive.py).
# Not set = no copies.
_drive = os.getenv("DRIVE_DIR", "").strip()
DRIVE_DIR = Path(_drive) if _drive else None

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

# Memory folder. A relative path like "./memory" is taken relative to the
# project folder, so it works no matter where you start Python from.
_memory = Path(os.getenv("MEMORY_DIR", "./memory"))
MEMORY_DIR = _memory if _memory.is_absolute() else (PROJECT_DIR / _memory).resolve()
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

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

# Memory folder. A relative path like "./memory" is taken relative to the
# project folder, so it works no matter where you start Python from.
_memory = Path(os.getenv("MEMORY_DIR", "./memory"))
MEMORY_DIR = _memory if _memory.is_absolute() else (PROJECT_DIR / _memory).resolve()
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

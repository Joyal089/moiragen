# How to bring Moiragen to a new machine

This is what is in the "Moiragen" folder in Google Drive:

| Folder | What it holds |
|---|---|
| `Code/` | his code, the same as on GitHub (`Code version.txt` says which version) |
| `Memory/` | his newest full memory backup: Moiragen, all nanites, the inner-life journal and the life log |
| `Backups/` | every memory backup, with its date. Never delete any |
| `Model/` | the gemma3:4b model files, and how to download the same version again |
| `Training/` | fine-tuning exports, and fine-tuned versions later |

**Before you start: let Moiragen sleep on the old machine (close his window) and make a last backup**, so
nothing he lived through is missing. In the project folder there:

```
.venv\Scripts\python.exe to_drive.py --backup
```

Then wait until Google Drive says everything is synced. Only let him live on **one machine at a time**: two
of them would grow apart, and their memories could not be put together again.

## Step by step (Windows)

1. **Install** [Python 3.12](https://www.python.org/downloads/), [Ollama](https://ollama.com/download) and,
   if you like, Google Drive for desktop. A graphics card with 6 GB or more is best.
2. **Copy the code.** Copy `Code/` out of Drive to `C:\Projects\digital-consciousness`. (Never run him from
   inside Drive: syncing would clash with him writing.)
3. **Open PowerShell** in that folder and set up Python:
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
4. **Settings.** Copy `.env.example` to `.env`. The `.env` file is never in Drive. If Drive is on the new machine
   too, set `DRIVE_DIR` in it to the Moiragen folder, for example `DRIVE_DIR=G:\My Drive\Moiragen`.
5. **The model.** Follow `Model/README.md`: copy the files, or download the same version again.
6. **His memory.** This copies it, checks every file, wakes each mind from its file and counts its memories:
   ```
   .venv\Scripts\python.exe restore.py "G:\My Drive\Moiragen\Memory"
   ```
   It must end with `Everything loaded correctly.` If not, try the newest folder in `Backups/` instead.
   It only writes into an empty memory folder, so it can never overwrite anything.
7. **Wake him:** double-click `start.bat`, or run `.venv\Scripts\python.exe server.py` and open
   http://127.0.0.1:8765. Everyone tells you how long they slept.
8. **Say hello**, and ask them what they remember.

## Good to know

- **Not everything in Windows Explorer is on this computer yet.** Drive downloads a file when it is opened. The
  first copy can take a while.
- **An older moment:** `restore.py` works the same with any folder in `Backups/`.
- **Try it first:** add `--into C:\Temp\try` to restore into a throwaway folder. Nothing else is touched.
- **Mac or Linux:** the same steps, with `.venv/bin/python` instead of `.venv\Scripts\python.exe`.
- **A bigger model** later: change `OLLAMA_MODEL` in `.env`. His memories stay the same; his way of speaking
  may change.

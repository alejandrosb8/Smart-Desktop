# Smart Desktop

A friendly Tkinter app that uses Google Gemini to organize your desktop (or any folder) into smart categories. Includes safe preview, one-click apply, revert, exclusions by extension or filename/pattern, secure in‑app API key storage, and an optional “thinking” mode for better results.

## Highlights

- Simple and safe: preview planned moves before applying, and revert the last run.
- AI-powered: Google Gemini classifies files by name or by inspecting content.
- Your rules matter: add custom categories, give AI extra context, and exclude extensions or specific files.
- In‑app key storage: save your Gemini API key securely via the system keyring.
- Clean-up: one click to remove empty folders and the previous movement log file.

## Screenshots

- Organize tab: Select folder, choose mode (By Name / By Content), add optional AI context, enable thinking, and run Preview or Organize.
- Categories tab: Add or remove your own categories.
- Settings tab: Manage Gemini API key, exclude extensions, and exclude specific files (names or patterns).
- Log tab: See activity, Revert last organization, and Clean artifacts.

## Requirements

- Python 3.11+ (tested) — works with standard Tkinter install
- Packages (see `requirements.txt`):
  - python-dotenv
  - google-genai
  - PyPDF2
  - python-docx
  - keyring

## Install

1. Clone the repo
2. Create and activate a virtual environment
3. Install dependencies

```powershell
# from the repo folder
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
. .venv\Scripts\Activate.ps1
python main.py
```

## First-time setup

1. Open the app and go to the Settings tab (Gemini API Key).
2. Paste your Google Gemini API key and click Save. Optionally click Test.
3. Go to the Organize tab and pick the folder you want to organize (e.g., your Desktop).

## How it works

Smart Desktop classifies files into categories you define. You can work in two modes:

- By Name (simple): Uses file name and metadata; it’s fast and often enough.
- By Content (complete): May read file contents (PDF, DOCX, TXT, etc.) to improve accuracy.

Before moving anything, use Preview to see exactly what will happen. You can Apply the plan from the Preview window or run Organize directly. Every run writes a movement log so you can Revert from the Log tab.

## Features and options

- Categories
  - Add/remove categories in the Categories tab.
  - Categories are stored in `config.json`.

- AI context
  - Provide extra instructions to the model (e.g., “Work documents go to ‘Work’, personal forms go to ‘Personal’”).
  - Stored in `config.json`.

- Organization modes
  - By Name (simple)
  - By Content (complete)
  - Tooltips explain the trade-offs.

- Allow AI "SKIP"
  - When enabled, the AI may mark a file as SKIP (do not move) if unsure.

- Thinking mode
  - A single checkbox controls the thinking budget:
    - Enabled → budget = -1 (dynamic)
    - Disabled → budget = 0 (off)
  - Stored in `config.json` as `thinking_budget`.

- Exclusions
  - Exclude extensions (e.g., `.lnk`, `.exe`, `.tmp`), so those files are never moved.
  - Exclude specific files or name patterns (e.g., `README*`, `do_not_move.txt`).
  - Add exclusions in Settings; exclusions are applied in both Preview and Organize.

- Preview and Apply
  - Preview shows a table of planned actions: move / skip, target category and destination.
  - Apply executes only the planned moves.

- Revert
  - Reverts the last organization by reading `movement_log.json`.
  - Runs in reverse order to restore files to their original locations.

- Clean
  - Removes empty category folders and deletes `movement_log.json`.

## Configuration file

The app manages a `config.json` in the repo (same folder as `main.py`). Keys used:

- `categories`: string[]
- `ai_context`: string
- `exclude_extensions`: string[] (e.g., [".lnk", ".exe"]) — case-insensitive
- `exclude_files`: string[] of file names or patterns (supports wildcards via fnmatch)
- `allow_ai_skip`: boolean
- `thinking_budget`: number (only 0 or -1 are used by the app)

## Privacy and security

- API keys are stored securely using the OS keyring via the `keyring` library. They are not written to disk in plain text.
- Only file excerpts (for supported types) and lightweight metadata are sent to the AI when using By Content mode. Content length is limited for safety and performance.

## Troubleshooting

- I can’t click Preview/Organize
  - Ensure you selected a folder and saved a valid API key in Settings.

- Some files aren’t moving
  - Check the Log tab. Files can be excluded by extension/name, or the AI may SKIP them when uncertain if SKIP is enabled.

- The model is too slow or not accurate enough
  - Try disabling thinking for speed, or enabling it for potentially better quality.
  - By Name mode is faster; By Content can be more accurate for documents.

- Revert didn’t change anything
  - Ensure you’re in the same folder where the organization was performed. Revert only applies to the last run.

## Development notes

- Main UI: `main.py` (Tkinter + ttk Notebook with tabs: Organize, Categories, Settings, Log)
- Backend logic: `intelligent_utils.py` (classification, planning, moves, revert, clean)
- Model client: `google-genai` via `genai.Client`
- Movement log: `movement_log.json` in the selected folder
- Plan preview: uses `preview_classification_and_plan` and `apply_plan`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

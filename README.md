# Broken Arrow Deck Manager

Broken Arrow Deck Manager is a Windows desktop tool for backing up, organizing, and switching `Broken Arrow` deck sets.

Author: `YauS`  
Made with `Codex`

## What it does

- backs up the current active `Broken Arrow` deck folder into named saved sets
- restores a saved set back into the active game deck folder
- stores a note for each saved set
- stamps each saved set with the detected Steam branch and game version
- blocks switching when the saved set branch does not match the current game branch
- shows whether a saved set matches the current active decks exactly
- lets you change the saved-set folder and active deck folder from the app
- supports 10 UI languages loaded from external locale files
- opens the active deck folder and saved-set folder in File Explorer

## Requirements

- Windows
- Python `3.14`

## Source dependencies

Runtime dependency for the source code:

- `PySide6>=6.8`

These modules are used from the Python standard library and do not need separate installation:

- `argparse`
- `dataclasses`
- `datetime`
- `hashlib`
- `json`
- `logging`
- `pathlib`
- `re`
- `shutil`
- `subprocess`
- `sys`
- `winreg`

Optional dependency sets:

- build: `pyinstaller>=6.0`
- dev: `pylint>=3.3`

Install the project dependencies:

```powershell
python -m pip install -e .
```

## Run from source

```powershell
cd <project-root>
python .\src\broken_arrow_deck_manager.py
```

You can also launch the installed console entry point:

```powershell
broken-arrow-deck-manager
```

Useful CLI options:

```powershell
python .\src\broken_arrow_deck_manager.py --debug
python .\src\broken_arrow_deck_manager.py --cli-verify
broken-arrow-deck-manager --debug
broken-arrow-deck-manager --cli-verify
```

What they do:

- `--debug`: enables debug-level logging
- `--cli-verify`: prints deck-manager status in the terminal and exits without opening the GUI

Terminal-free launch:

- double-click `src\broken_arrow_deck_manager.pyw`

## Packaged app

The packaged Windows app is built into:

```text
dist\BrokenArrowDeckManager\BrokenArrowDeckManager.exe
```

The packaged app is portable as a folder-based build. Keep the whole `BrokenArrowDeckManager` folder together.

The repo does not track generated release bundles. Local packaged output should stay in ignored folders such as:

```text
dist\
release_downloads\
```

## Build the exe

Install the build dependency set if needed:

```powershell
python -m pip install -e .[build]
```

Build:

```powershell
cd <project-root>
python -m PyInstaller --noconfirm --clean .\packaging\BrokenArrowDeckManager.spec
```

After a rebuild, if you want the visible relative saved-set folder beside the exe to match the current source data:

```powershell
Copy-Item -Recurse -Force .\deck_sets .\dist\BrokenArrowDeckManager\deck_sets
```

## Main folders

Default active game deck folder:

```text
%USERPROFILE%\AppData\LocalLow\SteelBalalaikaStudio\BrokenArrow\Decks
```

Default saved-set folder when running from source:

```text
deck_tools\deck_sets
```

Default saved-set folder when running the packaged app:

```text
dist\BrokenArrowDeckManager\deck_sets
```

## Project metadata

The project now uses `pyproject.toml` and targets Python `3.14+`.

Useful install variants:

```powershell
python -m pip install -e .
python -m pip install -e .[dev]
python -m pip install -e .[build]
```

Quick dependency check:

```powershell
python -c "import PySide6, broken_arrow_deck_manager, deck_manager_logic, deck_manager_i18n, deck_manager_ui; print('dependencies ok')"
```

## Relative folder behavior

The tool now stores saved deck sets relative to the app location:

- source run: in the project root
- packaged run: next to `BrokenArrowDeckManager.exe`

For packaged builds, the app can seed the relative `deck_sets` folder from bundled data on first run.

The source code is split into separate modules for:

- entrypoint/bootstrap
- locale loading
- deck/storage/game logic
- Qt UI

## Settings and persistence

The app stores user settings in:

```text
deck_manager_settings.json
```

This file is created beside the app and saves:

- saved deck sets folder
- active game deck folder
- selected language

The app also writes logs beside the app as:

```text
deck_manager.log
```

By default the app logs at `INFO` level. Use `--debug` for more detailed output.

## Language support

Supported languages:

- `English`
- `繁體中文`
- `简体中文`
- `日本語`
- `한국어`
- `Русский`
- `Deutsch`
- `Français`
- `Español`
- `Português (Brasil)`

Change language from the menu:

`Language` -> choose any installed locale from `locales\`

Languages are loaded from:

```text
locales\*.json
```

Each locale file uses this structure:

```json
{
  "code": "en",
  "label": "English",
  "strings": {
    "app_title": "Broken Arrow Deck Manager"
  }
}
```

The app discovers these files automatically at startup.

To add another language, add a new JSON file in `locales\` with a unique `code`, a menu `label`, and the translated `strings`.

## How to use the app

### Main screen

The table shows:

- `Deck set`: saved set name
- `Branch`: Steam branch recorded when the set was backed up
- `Same branch`: whether that branch matches the currently detected game branch
- `Same as active`: whether the saved set `.dek` files exactly match the active game deck folder

The top section shows:

- active deck folder
- active deck count
- saved set count
- detected game install path
- detected game version

### Main actions

- `Back Up Current Decks`: saves the current active decks into a named set
- `Use Selected Deck Set`: switches the active game decks to the selected saved set
- `Switch without making a safety backup`: skips the automatic pre-switch backup
- `Refresh`: reloads the saved-set list and current game state
- `Open Saved Deck Sets`: opens the saved-set folder
- `Open Active Decks`: opens the active game deck folder
- `Save Note`: saves the note for the selected deck set

### Options menu

Open:

`File` -> `Options`

You can change:

- saved deck sets folder
- active game deck folder
- language

These settings are saved automatically after pressing `OK`.

### Help menu

Open:

`Help` -> `About`

## Switching behavior

When switching to a saved set:

- the app checks that the saved set branch matches the current detected game branch
- by default, the current active deck folder is auto-backed up first
- automatic backups are stored under:

```text
deck_sets\_auto\active_before_<timestamp>_to_<set-name>
```

If switching fails, the tool tries to restore the previous active decks.

## Saved set metadata

Each saved set stores metadata in `_backup.json`, including:

- set name
- note/message
- creation time
- deck count
- backup path
- SHA-256 hash of `.dek` contents
- stamped game version

## Steam and game detection

The tool detects:

- Steam install path
- Steam library folders
- `Broken Arrow` install directory
- current game branch/version from Steam `appmanifest_1604270.acf`

The current version and branch are read from Steam metadata, not from `Player.log`.

## Project files

```text
deck_tools/
├─ assets/
│  └─ icons/
│     ├─ broken_arrow_deck_manager_icon.ico
│     ├─ broken_arrow_deck_manager_icon.png
├─ deck_sets/
├─ locales/
│  ├─ en.json
│  ├─ de.json
│  ├─ es.json
│  ├─ fr.json
│  ├─ ja.json
│  ├─ ko.json
│  ├─ pt-BR.json
│  ├─ ru.json
│  ├─ zh-Hans.json
│  └─ zh-Hant.json
├─ packaging/
│  └─ BrokenArrowDeckManager.spec
├─ src/
│  ├─ broken_arrow_deck_manager.py
│  ├─ broken_arrow_deck_manager.pyw
│  ├─ deck_manager_i18n.py
│  ├─ deck_manager_logic.py
│  └─ deck_manager_ui.py
├─ .gitignore
├─ LICENSE
├─ pyproject.toml
└─ README.md
```

Key files:

- `pyproject.toml`: project metadata, dependencies, and Python version target
- `src\broken_arrow_deck_manager.py`: startup/bootstrap entrypoint
- `src\broken_arrow_deck_manager.pyw`: terminal-free source launcher
- `src\deck_manager_i18n.py`: locale loading and translation lookup
- `src\deck_manager_logic.py`: deck management, storage, settings, and game detection logic
- `src\deck_manager_ui.py`: `PySide6` dialogs and main window
- `locales\*.json`: runtime language files
- `packaging\BrokenArrowDeckManager.spec`: `PyInstaller` build spec
- `assets\icons\...`: app icons
- `deck_sets\...`: local saved deck sets used by the tool when present

## Git

This folder is initialized as a git repository.

Ignored files:

- `build/`
- `dist/`
- `release_downloads/`
- `__pycache__/`
- `deck_sets/`
- `deck_manager_settings.json`

## License

This project is licensed under the `MIT` license. See `LICENSE`.

## Notes

- Close `Broken Arrow` before backing up or switching.
- The backup includes everything inside the active deck folder, including nested folders and support files.
- The packaged app should be moved or copied as a whole folder, not as a standalone `.exe`.

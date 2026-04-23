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
- supports `English` and `Traditional Chinese`
- opens the active deck folder and saved-set folder in File Explorer

## Requirements

- Windows
- Python `3.12`
- `PySide6`

If you need to install the UI dependency:

```powershell
python -m pip install PySide6
```

## Run from source

```powershell
cd <project-root>
python .\src\broken_arrow_deck_manager.py
```

Terminal-free launch:

- double-click `src\broken_arrow_deck_manager.pyw`

## Packaged app

The packaged Windows app is built into:

```text
dist\BrokenArrowDeckManager\BrokenArrowDeckManager.exe
```

The packaged app is portable as a folder-based build. Keep the whole `BrokenArrowDeckManager` folder together.

## Build the exe

Install `PyInstaller` if needed:

```powershell
python -m pip install pyinstaller
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

## Relative folder behavior

The tool now stores saved deck sets relative to the app location:

- source run: in the project root
- packaged run: next to `BrokenArrowDeckManager.exe`

For packaged builds, the app can seed the relative `deck_sets` folder from bundled data on first run.

## Settings and persistence

The app stores user settings in:

```text
deck_manager_settings.json
```

This file is created beside the app and saves:

- saved deck sets folder
- active game deck folder
- selected language

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
│  └─ broken_arrow_deck_manager.pyw
├─ .gitignore
└─ README.md
```

Key files:

- `src\broken_arrow_deck_manager.py`: main `PySide6` application
- `src\broken_arrow_deck_manager.pyw`: terminal-free source launcher
- `locales\*.json`: runtime language files
- `packaging\BrokenArrowDeckManager.spec`: `PyInstaller` build spec
- `assets\icons\...`: app icons
- `deck_sets\...`: saved deck sets used by the tool

## Git

This folder is initialized as a git repository.

Ignored files:

- `build/`
- `dist/`
- `__pycache__/`
- `deck_manager_settings.json`

## Notes

- Close `Broken Arrow` before backing up or switching.
- The backup includes everything inside the active deck folder, including nested folders and support files.
- The packaged app should be moved or copied as a whole folder, not as a standalone `.exe`.

import json
import os
import shutil
import subprocess
import sys
import hashlib
import re
import winreg
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk


SCRIPT_ROOT = Path(__file__).resolve().parent
STORAGE_ROOT = SCRIPT_ROOT / "deck_sets"
ACTIVE_DECKS_PATH = Path.home() / "AppData" / "LocalLow" / "SteelBalalaikaStudio" / "BrokenArrow" / "Decks"
AUTO_ROOT = STORAGE_ROOT / "_auto"
BROKEN_ARROW_APP_ID = "1604270"
SET_COLUMN_WIDTH = 30
BRANCH_COLUMN_WIDTH = 18
CHECKBOX_COLUMN_WIDTH = 12


@dataclass
class SetMetadata:
    set_name: str
    message: str
    created_at: str
    backup_path: str
    deck_count: int
    content_hash: str
    game_version: str


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window: tk.Toplevel | None = None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, _event: tk.Event | None = None) -> None:
        if self.tip_window or not self.text:
            return

        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            bg="#fff8dc",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=4,
        )
        label.pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


def is_game_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq BrokenArrow*.exe"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False

    output = (result.stdout or "") + (result.stderr or "")
    return "BrokenArrow" in output.replace(" ", "")


def get_steam_root() -> Path | None:
    registry_candidates = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]

    for hive, subkey, value_name in registry_candidates:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                steam_root = Path(value)
                if steam_root.exists():
                    return steam_root
        except OSError:
            continue

    path_candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Steam",
        Path(os.environ.get("ProgramFiles", "")) / "Steam",
    ]
    for candidate in path_candidates:
        if str(candidate) and candidate.exists():
            return candidate

    return None


def get_steam_library_paths() -> list[Path]:
    steam_root = get_steam_root()
    libraries: list[Path] = []

    if steam_root:
        libraries.append(steam_root)
        library_vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if library_vdf.exists():
            try:
                content = library_vdf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                content = ""

            for match in re.finditer(r'"path"\s+"([^"]+)"', content, re.IGNORECASE):
                library_path = Path(match.group(1).replace("\\\\", "\\"))
                if library_path.exists() and library_path not in libraries:
                    libraries.append(library_path)

    return libraries


def get_manifest_path() -> Path | None:
    for library in get_steam_library_paths():
        manifest = library / "steamapps" / f"appmanifest_{BROKEN_ARROW_APP_ID}.acf"
        if manifest.exists():
            return manifest
    return None


def get_manifest_content() -> str:
    manifest_path = get_manifest_path()
    if not manifest_path:
        return ""
    try:
        return manifest_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def get_game_install_dir() -> Path | None:
    content = get_manifest_content()
    manifest_path = get_manifest_path()
    if not content or not manifest_path:
        return None

    install_match = re.search(r'"installdir"\s+"([^"]+)"', content)
    if not install_match:
        return None

    install_dir = install_match.group(1)
    steamapps_dir = manifest_path.parent
    candidate = steamapps_dir / "common" / install_dir
    if candidate.exists():
        return candidate
    return None


def get_game_exe_path() -> Path | None:
    install_dir = get_game_install_dir()
    if not install_dir:
        return None
    exe_path = install_dir / "BrokenArrow.exe"
    if exe_path.exists():
        return exe_path
    return None


def detect_game_version() -> str:
    steam_version = detect_version_from_steam_manifest()
    if steam_version:
        return steam_version

    exe_version = detect_version_from_exe()
    if exe_version:
        return exe_version

    return "Version: not detected"


def detect_version_from_steam_manifest() -> str:
    content = get_manifest_content()
    if not content:
        return ""

    branch_match = re.search(
        r'"(?:UserConfig|MountedConfig)"\s*\{.*?"BetaKey"\s+"([^"]*)"',
        content,
        re.DOTALL | re.IGNORECASE,
    )
    build_match = re.search(r'"buildid"\s+"([^"]+)"', content)
    updated_match = re.search(r'"LastUpdated"\s+"([^"]+)"', content)

    if not build_match:
        return ""

    branch = "default"
    if branch_match:
        branch = branch_match.group(1).strip() or "default"

    details = f"Branch {branch}"
    details += f" | Build {build_match.group(1)}"
    if updated_match:
        try:
            updated = datetime.fromtimestamp(int(updated_match.group(1))).strftime("%Y-%m-%d %H:%M:%S")
            details += f" | Updated {updated}"
        except ValueError:
            pass

    return f"Version: {details} (Steam)"


def extract_branch_name(version_text: str) -> str:
    match = re.search(r"Branch\s+([^|]+)", version_text)
    if not match:
        return ""
    return match.group(1).strip()


def detect_version_from_exe() -> str:
    game_exe_path = get_game_exe_path()
    if not game_exe_path:
        return ""

    escaped_path = str(game_exe_path).replace("'", "''")
    command = (
        f"$item = Get-Item '{escaped_path}'; "
        "$pv = $item.VersionInfo.ProductVersion; "
        "$fv = $item.VersionInfo.FileVersion; "
        "if ($pv) { Write-Output $pv } elseif ($fv) { Write-Output $fv }"
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""

    version = (result.stdout or "").strip()
    if version:
        return f"Version: {version} (EXE)"

    return ""


def ensure_storage_root() -> None:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def default_set_name() -> str:
    return f"decks_{timestamp()}"


def validate_set_name(set_name: str) -> None:
    invalid = set('<>:"/\\|?*')
    if not set_name.strip():
        raise ValueError("Backup name is required.")
    if any(char in invalid for char in set_name):
        raise ValueError(f"Set name contains invalid path characters: {set_name}")


def copy_directory_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def remove_directory_contents(path: Path) -> None:
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def compute_set_hash(set_path: Path) -> str:
    digest = hashlib.sha256()
    deck_files = sorted(set_path.rglob("*.dek"), key=lambda p: str(p.relative_to(set_path)).lower())

    for item in deck_files:
        with item.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)

    return digest.hexdigest()


def compute_active_decks_hash() -> str:
    if not ACTIVE_DECKS_PATH.exists():
        return ""
    return compute_set_hash(ACTIVE_DECKS_PATH)


def write_metadata(
    set_path: Path,
    set_name: str,
    message: str,
    created_at: str | None = None,
    game_version: str | None = None,
) -> None:
    content_hash = compute_set_hash(set_path)
    metadata = {
        "SetName": set_name,
        "Message": message,
        "SourcePath": str(ACTIVE_DECKS_PATH),
        "BackupPath": str(set_path),
        "CreatedAt": created_at or datetime.now().isoformat(),
        "ContentHash": content_hash,
        "GameVersion": game_version or detect_game_version(),
        "Computer": os.environ.get("COMPUTERNAME", ""),
        "User": os.environ.get("USERNAME", ""),
    }
    metadata_path = set_path / "_backup.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def get_saved_set_names() -> list[str]:
    ensure_storage_root()
    names = []
    for item in STORAGE_ROOT.iterdir():
        if not item.is_dir():
            continue
        if item.name.startswith("_auto") or item.name.startswith("_switch_"):
            continue
        names.append(item.name)
    return sorted(names, key=str.lower)


def read_metadata(set_name: str) -> SetMetadata:
    set_path = STORAGE_ROOT / set_name
    message = ""
    created_at = ""
    content_hash = ""
    game_version = ""

    metadata_path = set_path / "_backup.json"
    if metadata_path.exists():
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            message = str(data.get("Message", "") or "")
            created_at = str(data.get("CreatedAt", "") or "")
            content_hash = str(data.get("ContentHash", "") or "")
            game_version = str(data.get("GameVersion", "") or "")
        except (OSError, json.JSONDecodeError):
            pass

    deck_count = len(list(set_path.glob("*.dek"))) if set_path.exists() else 0
    if set_path.exists() and not content_hash:
        content_hash = compute_set_hash(set_path)
    if not game_version:
        game_version = detect_game_version()
    return SetMetadata(
        set_name=set_name,
        message=message,
        created_at=created_at,
        backup_path=str(set_path),
        deck_count=deck_count,
        content_hash=content_hash,
        game_version=game_version,
    )


def backup_current_decks(set_name: str, message: str) -> Path:
    validate_set_name(set_name)
    if not ACTIVE_DECKS_PATH.exists():
        raise FileNotFoundError(f"Decks folder not found: {ACTIVE_DECKS_PATH}")
    if is_game_running():
        raise RuntimeError("Broken Arrow appears to be running. Close the game before backing up decks.")

    ensure_storage_root()
    destination = STORAGE_ROOT / set_name
    if destination.exists():
        raise FileExistsError(f"Destination set already exists: {destination}")

    destination.mkdir(parents=True, exist_ok=False)
    copy_directory_contents(ACTIVE_DECKS_PATH, destination)
    write_metadata(destination, set_name, message)
    return destination


def switch_to_set(set_name: str, skip_auto_backup: bool) -> None:
    if not ACTIVE_DECKS_PATH.exists():
        raise FileNotFoundError(f"Decks folder not found: {ACTIVE_DECKS_PATH}")
    if is_game_running():
        raise RuntimeError("Broken Arrow appears to be running. Close the game before switching deck sets.")

    source_set = STORAGE_ROOT / set_name
    if not source_set.exists():
        raise FileNotFoundError(f"Saved deck set not found: {source_set}")

    current_version = detect_game_version()
    current_branch = extract_branch_name(current_version)
    target_metadata = read_metadata(set_name)
    target_branch = extract_branch_name(target_metadata.game_version)

    if not current_branch:
        raise RuntimeError("Current game branch could not be detected from Steam appmanifest.")
    if not target_branch:
        raise RuntimeError(f'Saved set "{set_name}" does not have a valid branch stamp.')
    if current_branch.lower() != target_branch.lower():
        raise RuntimeError(
            f'Cannot restore "{set_name}" on branch "{current_branch}". '
            f'This set was stamped for branch "{target_branch}".'
        )

    ensure_storage_root()
    work_root = STORAGE_ROOT / f"_switch_{timestamp()}"
    current_snapshot = work_root / "current"
    current_snapshot.mkdir(parents=True, exist_ok=True)

    try:
        move_source = list(ACTIVE_DECKS_PATH.iterdir())
        for item in move_source:
            shutil.move(str(item), str(current_snapshot / item.name))

        copy_directory_contents(source_set, ACTIVE_DECKS_PATH)

        if skip_auto_backup:
            shutil.rmtree(work_root, ignore_errors=True)
        else:
            AUTO_ROOT.mkdir(parents=True, exist_ok=True)
            auto_name = f"active_before_{timestamp()}_to_{set_name}"
            shutil.move(str(current_snapshot), str(AUTO_ROOT / auto_name))
            shutil.rmtree(work_root, ignore_errors=True)
    except Exception:
        try:
            remove_directory_contents(ACTIVE_DECKS_PATH)
            if current_snapshot.exists():
                copy_directory_contents(current_snapshot, ACTIVE_DECKS_PATH)
        except Exception as restore_error:
            raise RuntimeError(
                f"Switch failed and restore also failed. Previous active decks remain in: {current_snapshot}"
            ) from restore_error
        raise


def save_set_message(set_name: str, message: str) -> None:
    set_path = STORAGE_ROOT / set_name
    if not set_path.exists():
        raise FileNotFoundError(f"Saved deck set not found: {set_path}")

    current = read_metadata(set_name)
    write_metadata(
        set_path,
        current.set_name,
        message,
        current.created_at or datetime.now().isoformat(),
        current.game_version,
    )


def stamp_missing_set_versions() -> None:
    current_version = detect_game_version()
    for set_name in get_saved_set_names():
        set_path = STORAGE_ROOT / set_name
        current = read_metadata(set_name)
        if current.game_version:
            continue
        write_metadata(
            set_path,
            current.set_name,
            current.message,
            current.created_at or datetime.now().isoformat(),
            current_version,
        )


def open_in_explorer(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(path)  # type: ignore[attr-defined]


class DeckManagerApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Broken Arrow Deck Manager")
        self.root.geometry("900x760")
        self.root.minsize(820, 680)
        self.root.resizable(True, True)
        self.style = ttk.Style(self.root)

        self.set_name_var = tk.StringVar(value=default_set_name())
        self.status_var = tk.StringVar(value="")
        self.active_summary_var = tk.StringVar(value="")
        self.saved_summary_var = tk.StringVar(value="")
        self.game_version_var = tk.StringVar(value="")
        self.game_path_var = tk.StringVar(value="")
        self.set_details_var = tk.StringVar(value="Select a saved set to view details.")
        self.skip_auto_backup_var = tk.BooleanVar(value=False)
        self.selected_set: str | None = None
        self.table_row_widgets: dict[str, dict[str, object]] = {}
        self.tooltips: list[ToolTip] = []

        self._build_ui()
        self.refresh_set_list()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        self.root.rowconfigure(4, weight=1)

        main_frame = ttk.Frame(self.root, padding=16)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(4, weight=1)

        title = ttk.Label(main_frame, text="Broken Arrow Deck Manager", font=("Segoe UI", 14, "bold"))
        title.grid(row=0, column=0, sticky="w")

        info_frame = ttk.Frame(main_frame)
        info_frame.grid(row=1, column=0, sticky="ew", pady=(10, 12))
        info_frame.columnconfigure(0, weight=1)

        path_label = ttk.Label(
            info_frame,
            text=f"Active Decks Folder: {ACTIVE_DECKS_PATH}",
            anchor="w",
            justify="left",
        )
        path_label.grid(row=0, column=0, sticky="ew")

        summary_frame = ttk.Frame(info_frame)
        summary_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.columnconfigure(1, weight=1)

        active_summary = ttk.Label(summary_frame, textvariable=self.active_summary_var, anchor="w")
        active_summary.grid(row=0, column=0, sticky="w")

        saved_summary = ttk.Label(summary_frame, textvariable=self.saved_summary_var, anchor="w")
        saved_summary.grid(row=0, column=1, sticky="w", padx=(12, 0))

        game_version_frame = ttk.Frame(info_frame)
        game_version_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        game_version_frame.columnconfigure(0, weight=1)

        game_path_title = ttk.Label(game_version_frame, text="Detected game path", anchor="w", justify="left")
        game_path_title.grid(row=0, column=0, sticky="w")

        game_path = ttk.Label(game_version_frame, textvariable=self.game_path_var, anchor="w", justify="left")
        game_path.grid(row=1, column=0, sticky="w", pady=(4, 0))

        game_version_title = ttk.Label(game_version_frame, text="Detected game version", anchor="w", justify="left")
        game_version_title.grid(row=2, column=0, sticky="w", pady=(8, 0))

        game_version = ttk.Label(game_version_frame, textvariable=self.game_version_var, anchor="w", justify="left")
        game_version.grid(row=3, column=0, sticky="w", pady=(4, 0))

        content_frame = ttk.Frame(main_frame)
        content_frame.grid(row=2, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=3)
        content_frame.columnconfigure(1, weight=2)
        content_frame.rowconfigure(0, weight=1)

        table_frame = ttk.Frame(content_frame)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(1, weight=1)

        header_frame = tk.Frame(table_frame, bg=self.root.cget("bg"))
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=5, uniform="table")
        header_frame.grid_columnconfigure(1, weight=3, uniform="table")
        header_frame.grid_columnconfigure(2, weight=2, uniform="table")
        header_frame.grid_columnconfigure(3, weight=2, uniform="table")
        header_font = ("Segoe UI", 9, "bold")
        set_header = tk.Label(header_frame, text="Set", anchor="w", bg=self.root.cget("bg"), font=header_font)
        set_header.grid(row=0, column=0, sticky="ew")
        branch_header = tk.Label(header_frame, text="Branch", anchor="w", bg=self.root.cget("bg"), font=header_font)
        branch_header.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        version_header = tk.Label(
            header_frame,
            text="Version Match",
            anchor="center",
            bg=self.root.cget("bg"),
            font=header_font,
        )
        version_header.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        identical_header = tk.Label(
            header_frame,
            text="Identical",
            anchor="center",
            bg=self.root.cget("bg"),
            font=header_font,
        )
        identical_header.grid(row=0, column=3, sticky="ew", padx=(8, 0))

        self.tooltips.extend(
            [
                ToolTip(set_header, "Saved deck set name."),
                ToolTip(branch_header, "Steam branch stamped into this saved set when it was backed up."),
                ToolTip(version_header, "Checked if this saved set's stamped branch matches the currently detected game branch."),
                ToolTip(identical_header, "Checked if this saved set's .dek contents exactly match the current active Decks folder."),
            ]
        )

        list_container = ttk.Frame(table_frame)
        list_container.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)

        self.table_canvas = tk.Canvas(list_container, highlightthickness=0, borderwidth=0)
        self.table_canvas.grid(row=0, column=0, sticky="nsew")

        self.table_scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.table_canvas.yview)
        self.table_scrollbar.grid(row=0, column=1, sticky="ns")
        self.table_canvas.configure(yscrollcommand=self.table_scrollbar.set)

        self.table_inner = tk.Frame(self.table_canvas, bd=0, highlightthickness=0)
        self.table_window = self.table_canvas.create_window((0, 0), window=self.table_inner, anchor="nw")
        self.table_inner.bind("<Configure>", self._on_table_frame_configure)
        self.table_canvas.bind("<Configure>", self._on_table_canvas_configure)

        controls_frame = ttk.Frame(content_frame)
        controls_frame.grid(row=0, column=1, sticky="nsew")
        controls_frame.columnconfigure(0, weight=1)

        label_new_set = ttk.Label(controls_frame, text="Backup name", anchor="w")
        label_new_set.grid(row=0, column=0, sticky="w")

        self.entry_new_set = ttk.Entry(controls_frame, textvariable=self.set_name_var)
        self.entry_new_set.grid(row=1, column=0, sticky="ew", pady=(4, 10))

        self.button_backup = ttk.Button(controls_frame, text="Backup Current Decks", command=self.backup_current)
        self.button_backup.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        self.button_switch = ttk.Button(
            controls_frame,
            text="Switch To Selected Set",
            command=self.switch_selected,
            state="disabled",
        )
        self.button_switch.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        skip_checkbox = ttk.Checkbutton(
            controls_frame,
            text="Skip auto-backup before switch",
            variable=self.skip_auto_backup_var,
        )
        skip_checkbox.grid(row=4, column=0, sticky="w", pady=(0, 12))

        actions_frame = ttk.Frame(controls_frame)
        actions_frame.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        actions_frame.columnconfigure(0, weight=1)
        actions_frame.columnconfigure(1, weight=1)
        actions_frame.columnconfigure(2, weight=1)

        button_refresh = ttk.Button(actions_frame, text="Refresh", command=self.refresh_clicked)
        button_refresh.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        button_open_sets = ttk.Button(
            actions_frame,
            text="Open Saved Sets",
            command=lambda: open_in_explorer(STORAGE_ROOT),
        )
        button_open_sets.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        button_help = ttk.Button(actions_frame, text="Help", command=self.show_help)
        button_help.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        button_open_active = ttk.Button(controls_frame, text="Open Active Decks", command=self.open_active_decks)
        button_open_active.grid(row=6, column=0, sticky="ew")

        details = ttk.Label(
            main_frame,
            textvariable=self.set_details_var,
            anchor="nw",
            justify="left",
            wraplength=690,
        )
        details.grid(row=3, column=0, sticky="ew", pady=(12, 8))

        message_frame = ttk.Frame(main_frame)
        message_frame.grid(row=4, column=0, sticky="nsew")
        message_frame.columnconfigure(0, weight=1)
        message_frame.rowconfigure(1, weight=1)

        label_message = ttk.Label(message_frame, text="Message for backup", anchor="w")
        label_message.grid(row=0, column=0, sticky="w")

        self.text_message = tk.Text(message_frame, wrap="word", height=7)
        self.text_message.grid(row=1, column=0, sticky="nsew", pady=(6, 8))

        self.button_save_message = ttk.Button(
            message_frame,
            text="Save Message",
            command=self.save_message,
            state="disabled",
        )
        self.button_save_message.grid(row=2, column=0, sticky="e")

        status = ttk.Entry(main_frame, textvariable=self.status_var, state="readonly")
        status.grid(row=5, column=0, sticky="ew", pady=(12, 0))

    def run(self) -> None:
        self.root.mainloop()

    def _on_table_frame_configure(self, _event: tk.Event) -> None:
        self.table_canvas.configure(scrollregion=self.table_canvas.bbox("all"))

    def _on_table_canvas_configure(self, event: tk.Event) -> None:
        self.table_canvas.itemconfigure(self.table_window, width=event.width)

    def active_deck_count(self) -> int:
        if not ACTIVE_DECKS_PATH.exists():
            return 0
        return len(list(ACTIVE_DECKS_PATH.glob("*.dek")))

    def selected_set_name(self) -> str | None:
        return self.selected_set

    def select_set(self, set_name: str | None) -> None:
        self.selected_set = set_name
        for row_name, widgets in self.table_row_widgets.items():
            row_frame = widgets["frame"]
            bg = "#dbeafe" if row_name == set_name else "white"
            row_frame.configure(bg=bg)
            for widget in widgets["bg_targets"]:
                widget.configure(bg=bg)
        self.update_selected_details()

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def refresh_set_list(self) -> None:
        selected = self.selected_set_name()
        names = get_saved_set_names()
        current_branch = extract_branch_name(detect_game_version())
        active_hash = compute_active_decks_hash()

        for child in self.table_inner.winfo_children():
            child.destroy()
        self.table_row_widgets.clear()

        for name in names:
            metadata = read_metadata(name)
            target_branch = extract_branch_name(metadata.game_version) or "-"
            branch_matches = bool(
                current_branch
                and target_branch != "-"
                and current_branch.lower() == target_branch.lower()
            )
            identical = bool(active_hash and metadata.content_hash and active_hash == metadata.content_hash)
            row_frame = tk.Frame(self.table_inner, bg="white", bd=0, highlightthickness=0, padx=4, pady=2)
            row_frame.grid_columnconfigure(0, weight=5, uniform="table")
            row_frame.grid_columnconfigure(1, weight=3, uniform="table")
            row_frame.grid_columnconfigure(2, weight=2, uniform="table")
            row_frame.grid_columnconfigure(3, weight=2, uniform="table")
            row_frame.pack(fill="x", expand=True)

            version_var = tk.BooleanVar(value=branch_matches)
            identical_var = tk.BooleanVar(value=identical)

            name_label = tk.Label(row_frame, text=name, anchor="w", bg="white")
            branch_label = tk.Label(row_frame, text=target_branch, anchor="w", bg="white")
            version_cell = tk.Frame(row_frame, bg="white")
            version_cell.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
            version_cell.grid_columnconfigure(0, weight=1)
            identical_cell = tk.Frame(row_frame, bg="white")
            identical_cell.grid(row=0, column=3, sticky="nsew", padx=(8, 0))
            identical_cell.grid_columnconfigure(0, weight=1)
            version_check = tk.Checkbutton(
                version_cell,
                variable=version_var,
                onvalue=True,
                offvalue=False,
                takefocus=0,
                text="",
                indicatoron=True,
                bd=0,
                highlightthickness=0,
                bg="white",
                activebackground="white",
                selectcolor="white",
                disabledforeground="black",
                width=1,
            )
            identical_check = tk.Checkbutton(
                identical_cell,
                variable=identical_var,
                onvalue=True,
                offvalue=False,
                takefocus=0,
                text="",
                indicatoron=True,
                bd=0,
                highlightthickness=0,
                bg="white",
                activebackground="white",
                selectcolor="white",
                disabledforeground="black",
                width=1,
            )
            name_label.grid(row=0, column=0, sticky="ew")
            branch_label.grid(row=0, column=1, sticky="ew", padx=(8, 0))
            version_check.grid(row=0, column=0)
            identical_check.grid(row=0, column=0)

            version_check.configure(state="normal")
            identical_check.configure(state="normal")

            clickable_widgets = [row_frame, name_label, branch_label]
            for widget in clickable_widgets:
                widget.bind("<Button-1>", lambda _event, selected_name=name: self.select_set(selected_name) or "break")

            version_check.bind("<Button-1>", lambda _event, selected_name=name: self.select_set(selected_name) or "break")
            identical_check.bind("<Button-1>", lambda _event, selected_name=name: self.select_set(selected_name) or "break")
            version_check.bind("<Key>", lambda _event: "break")
            identical_check.bind("<Key>", lambda _event: "break")

            self.table_row_widgets[name] = {
                "frame": row_frame,
                "bg_targets": [row_frame, name_label, branch_label, version_cell, identical_cell, version_check, identical_check],
                "version_var": version_var,
                "identical_var": identical_var,
            }

        self.active_summary_var.set(f"Active decks: {self.active_deck_count()} file(s)")
        self.saved_summary_var.set(f"Saved sets: {len(names)}")
        game_install_dir = get_game_install_dir()
        self.game_path_var.set(str(game_install_dir) if game_install_dir else "Path: not detected")
        self.game_version_var.set(detect_game_version())
        if selected and selected in self.table_row_widgets:
            self.select_set(selected)
        elif names:
            self.select_set(names[0])
        else:
            self.select_set(None)

    def update_selected_details(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            self.button_switch.config(state="disabled")
            self.button_save_message.config(state="disabled")
            self.set_details_var.set("Select a saved set to view details.")
            self.text_message.delete("1.0", tk.END)
            return

        metadata = read_metadata(selected)
        created_text = "Unknown"
        if metadata.created_at:
            try:
                created_text = datetime.fromisoformat(metadata.created_at).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                created_text = metadata.created_at

        self.button_switch.config(state="normal")
        self.button_save_message.config(state="normal")
        self.set_details_var.set(
            "Selected: {0}\nDecks: {1} | Created: {2}\nVersion: {3}\nHash: {4}".format(
                metadata.set_name,
                metadata.deck_count,
                created_text,
                metadata.game_version,
                metadata.content_hash,
            )
        )
        self.text_message.delete("1.0", tk.END)
        self.text_message.insert("1.0", metadata.message)

        current_branch = extract_branch_name(detect_game_version())
        target_branch = extract_branch_name(metadata.game_version)
        branch_matches = bool(current_branch and target_branch and current_branch.lower() == target_branch.lower())
        if not branch_matches:
            self.button_switch.config(state="disabled")

    def refresh_clicked(self) -> None:
        self.refresh_set_list()
        self.set_status("Saved set list refreshed.")

    def show_help(self) -> None:
        messagebox.showinfo(
            "About Broken Arrow Deck Manager",
            "Broken Arrow Deck Manager\n\n"
            "Purpose: manage Broken Arrow deck backups, switching, and branch/version checks.\n\n"
            "Author/Editor: OpenAI Codex\n"
            "Workspace owner and operator: current Windows user",
        )

    def open_active_decks(self) -> None:
        if not ACTIVE_DECKS_PATH.exists():
            messagebox.showwarning("Broken Arrow Deck Manager", "The active decks folder does not exist.")
            return
        open_in_explorer(ACTIVE_DECKS_PATH)

    def backup_current(self) -> None:
        set_name = self.set_name_var.get().strip()
        message = self.text_message.get("1.0", tk.END).strip()
        try:
            destination = backup_current_decks(set_name, message)
        except Exception as exc:
            messagebox.showerror("Backup Failed", str(exc))
            self.set_status(str(exc))
            return

        self.refresh_set_list()
        names = get_saved_set_names()
        if set_name in names:
            self.select_set(set_name)

        self.set_name_var.set(default_set_name())
        self.set_status(f"Backup created: {destination}")

    def switch_selected(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            messagebox.showwarning("Broken Arrow Deck Manager", "Select a saved set first.")
            return

        prompt = f'Switch active decks to "{selected}"?'
        if not self.skip_auto_backup_var.get():
            prompt += "\n\nThe current active decks will be auto-backed up first."

        if not messagebox.askokcancel("Confirm Switch", prompt):
            return

        try:
            switch_to_set(selected, self.skip_auto_backup_var.get())
        except Exception as exc:
            messagebox.showerror("Switch Failed", str(exc))
            self.set_status(str(exc))
            return

        self.refresh_set_list()
        self.set_status(f"Active deck set switched to: {selected}")

    def save_message(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            return

        message = self.text_message.get("1.0", tk.END).strip()
        try:
            save_set_message(selected, message)
        except Exception as exc:
            messagebox.showerror("Save Message Failed", str(exc))
            self.set_status(str(exc))
            return

        self.update_selected_details()
        self.set_status(f"Saved message for set: {selected}")


def main() -> int:
    ensure_storage_root()
    stamp_missing_set_versions()
    app = DeckManagerApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

import json
import os
import re
import shutil
import subprocess
import sys
import hashlib
import winreg
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QAbstractItemView,
)


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = get_app_root()
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT)).resolve()
SETTINGS_PATH = APP_ROOT / "deck_manager_settings.json"
LOCALES_ROOT = APP_ROOT / "locales"
DEFAULT_STORAGE_ROOT = APP_ROOT / "deck_sets"
DEFAULT_ACTIVE_DECKS_PATH = (
    Path.home() / "AppData" / "LocalLow" / "SteelBalalaikaStudio" / "BrokenArrow" / "Decks"
)
STORAGE_ROOT = DEFAULT_STORAGE_ROOT
ACTIVE_DECKS_PATH = DEFAULT_ACTIVE_DECKS_PATH
AUTO_ROOT = STORAGE_ROOT / "_auto"
BROKEN_ARROW_APP_ID = "1604270"
APP_ICON_PATH = APP_ROOT / "assets" / "icons" / "broken_arrow_deck_manager_icon.ico"
if not APP_ICON_PATH.exists():
    APP_ICON_PATH = RESOURCE_ROOT / "broken_arrow_deck_manager_icon.ico"
APP_LANGUAGE = "en"
LANGUAGES: dict[str, str] = {}
TEXT: dict[str, dict[str, str]] = {}


def load_locales() -> None:
    global LANGUAGES, TEXT

    locales_root = LOCALES_ROOT
    if not locales_root.exists():
        bundled_locales_root = RESOURCE_ROOT / "locales"
        if bundled_locales_root.exists():
            locales_root = bundled_locales_root

    loaded_languages: dict[str, str] = {}
    loaded_text: dict[str, dict[str, str]] = {}

    for path in sorted(locales_root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        code = payload.get("code")
        label = payload.get("label")
        strings = payload.get("strings")
        if not isinstance(code, str) or not code:
            continue
        if not isinstance(label, str) or not label:
            continue
        if not isinstance(strings, dict):
            continue

        normalized_strings = {str(key): str(value) for key, value in strings.items()}
        loaded_languages[code] = label
        loaded_text[code] = normalized_strings

    if "en" not in loaded_text:
        raise RuntimeError("Missing required locale file: en.json")

    LANGUAGES = loaded_languages
    TEXT = loaded_text


def t(key: str, **values: object) -> str:
    text = TEXT.get(APP_LANGUAGE, TEXT["en"]).get(key, TEXT["en"].get(key, key))
    return text.format(**values) if values else text


def load_settings() -> None:
    global ACTIVE_DECKS_PATH, APP_LANGUAGE, AUTO_ROOT, STORAGE_ROOT
    if not SETTINGS_PATH.exists():
        return

    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    storage_root = data.get("storage_root")
    active_decks_path = data.get("active_decks_path")
    language = data.get("language")

    if isinstance(storage_root, str) and storage_root.strip():
        STORAGE_ROOT = Path(storage_root).expanduser()
    if isinstance(active_decks_path, str) and active_decks_path.strip():
        ACTIVE_DECKS_PATH = Path(active_decks_path).expanduser()
    if language in LANGUAGES:
        APP_LANGUAGE = language
    AUTO_ROOT = STORAGE_ROOT / "_auto"


def save_settings() -> None:
    data = {
        "storage_root": str(STORAGE_ROOT),
        "active_decks_path": str(ACTIVE_DECKS_PATH),
        "language": APP_LANGUAGE,
    }
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class SetMetadata:
    set_name: str
    message: str
    created_at: str
    backup_path: str
    deck_count: int
    content_hash: str
    game_version: str


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

    candidate = manifest_path.parent / "common" / install_match.group(1)
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

    details = f"Branch {branch} | Build {build_match.group(1)}"
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
    bundled_storage_root = RESOURCE_ROOT / "deck_sets"
    if (
        not STORAGE_ROOT.exists()
        and bundled_storage_root.exists()
        and bundled_storage_root.resolve() != STORAGE_ROOT.resolve()
    ):
        shutil.copytree(bundled_storage_root, STORAGE_ROOT)
        return

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
    metadata = {
        "SetName": set_name,
        "Message": message,
        "SourcePath": str(ACTIVE_DECKS_PATH),
        "BackupPath": str(set_path),
        "CreatedAt": created_at or datetime.now().isoformat(),
        "ContentHash": compute_set_hash(set_path),
        "GameVersion": game_version or detect_game_version(),
        "Computer": os.environ.get("COMPUTERNAME", ""),
        "User": os.environ.get("USERNAME", ""),
    }
    (set_path / "_backup.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


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
        for item in list(ACTIVE_DECKS_PATH.iterdir()):
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
        current = read_metadata(set_name)
        if current.game_version:
            continue
        write_metadata(
            STORAGE_ROOT / set_name,
            current.set_name,
            current.message,
            current.created_at or datetime.now().isoformat(),
            current_version,
        )


def open_in_explorer(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(path)  # type: ignore[attr-defined]


class OptionsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("options_title"))
        self.resize(640, 170)

        layout = QFormLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.storage_edit = QLineEdit(str(STORAGE_ROOT))
        self.active_edit = QLineEdit(str(ACTIVE_DECKS_PATH))
        self.language_combo = QComboBox()
        for code, label in LANGUAGES.items():
            self.language_combo.addItem(label, code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(APP_LANGUAGE)))

        layout.addRow(t("saved_folder"), self._folder_row(self.storage_edit))
        layout.addRow(t("active_decks_folder"), self._folder_row(self.active_edit))
        layout.addRow(t("language"), self.language_combo)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def _folder_row(self, edit: QLineEdit) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        button = QPushButton(t("browse"))
        button.clicked.connect(lambda: self._browse_folder(edit))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    def _browse_folder(self, edit: QLineEdit) -> None:
        start = edit.text().strip() or str(APP_ROOT)
        selected = QFileDialog.getExistingDirectory(self, t("options_title"), start)
        if selected:
            edit.setText(selected)

    def values(self) -> tuple[Path, Path, str]:
        return (
            Path(self.storage_edit.text().strip()).expanduser(),
            Path(self.active_edit.text().strip()).expanduser(),
            str(self.language_combo.currentData()),
        )


class DeckManagerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(980, 760)
        self.selected_set: str | None = None
        self.checkbox_widgets: list[QCheckBox] = []
        self.language_actions: dict[str, QAction] = {}
        self._build_menu()
        self._build_ui()
        self.retranslate_ui()
        self.refresh_set_list()

    def _build_menu(self) -> None:
        self.file_menu = self.menuBar().addMenu("")
        self.options_action = QAction(self)
        self.options_action.triggered.connect(self.show_options)
        self.exit_action = QAction(self)
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.options_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)

        self.language_menu = self.menuBar().addMenu("")
        for code in LANGUAGES:
            action = QAction(self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, language=code: self.set_language(language))
            self.language_menu.addAction(action)
            self.language_actions[code] = action

        self.help_menu = self.menuBar().addMenu("")
        self.about_action = QAction(self)
        self.about_action.triggered.connect(self.show_help)
        self.help_menu.addAction(self.about_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        root.addWidget(self.title_label)

        self.info_box = QGroupBox()
        info_layout = QVBoxLayout(self.info_box)
        info_layout.setSpacing(6)
        self.active_path_label = QLabel()
        self.active_summary_label = QLabel()
        self.saved_summary_label = QLabel()
        self.game_path_label = QLabel()
        self.game_version_label = QLabel()
        for label in [
            self.active_path_label,
            self.active_summary_label,
            self.saved_summary_label,
            self.game_path_label,
            self.game_version_label,
        ]:
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            info_layout.addWidget(label)
        root.addWidget(self.info_box)

        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(12)
        root.addLayout(middle_layout, 1)

        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self._set_header_tooltips()
        middle_layout.addWidget(self.table, 3)

        self.controls_box = QGroupBox()
        controls_layout = QVBoxLayout(self.controls_box)
        controls_layout.setSpacing(8)

        self.backup_name_label = QLabel()
        controls_layout.addWidget(self.backup_name_label)
        self.backup_name_edit = QLineEdit()
        self.backup_name_edit.setText(default_set_name())
        controls_layout.addWidget(self.backup_name_edit)

        self.backup_button = QPushButton()
        self.backup_button.clicked.connect(self.backup_current)
        controls_layout.addWidget(self.backup_button)

        self.switch_button = QPushButton()
        self.switch_button.setEnabled(False)
        self.switch_button.clicked.connect(self.switch_selected)
        controls_layout.addWidget(self.switch_button)

        self.skip_auto_backup_checkbox = QCheckBox()
        controls_layout.addWidget(self.skip_auto_backup_checkbox)

        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh_clicked)
        controls_layout.addWidget(self.refresh_button)

        self.open_sets_button = QPushButton()
        self.open_sets_button.clicked.connect(lambda: open_in_explorer(STORAGE_ROOT))
        controls_layout.addWidget(self.open_sets_button)

        self.open_active_button = QPushButton()
        self.open_active_button.clicked.connect(self.open_active_decks)
        controls_layout.addWidget(self.open_active_button)

        self.help_button = QPushButton()
        self.help_button.clicked.connect(self.show_help)
        controls_layout.addWidget(self.help_button)
        controls_layout.addStretch(1)

        middle_layout.addWidget(self.controls_box, 2)

        self.details_box = QGroupBox()
        details_layout = QVBoxLayout(self.details_box)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_layout.addWidget(self.details_label)
        root.addWidget(self.details_box)

        self.message_box = QGroupBox()
        message_layout = QVBoxLayout(self.message_box)
        self.message_edit = QTextEdit()
        self.message_edit.setAcceptRichText(False)
        message_layout.addWidget(self.message_edit)
        self.save_message_button = QPushButton()
        self.save_message_button.setEnabled(False)
        self.save_message_button.clicked.connect(self.save_message)
        message_layout.addWidget(self.save_message_button, alignment=Qt.AlignmentFlag.AlignRight)
        root.addWidget(self.message_box, 1)

        self.status_line = QLineEdit()
        self.status_line.setReadOnly(True)
        root.addWidget(self.status_line)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(t("app_title"))
        self.file_menu.setTitle(t("menu_file"))
        self.language_menu.setTitle(t("menu_language"))
        self.help_menu.setTitle(t("menu_help"))
        self.options_action.setText(t("options"))
        self.exit_action.setText(t("exit"))
        self.about_action.setText(t("about"))
        for code, action in self.language_actions.items():
            action.setText(LANGUAGES[code])
            action.setChecked(code == APP_LANGUAGE)

        self.title_label.setText(t("app_title"))
        self.info_box.setTitle(t("environment"))
        self.table.setHorizontalHeaderLabels(
            [t("col_set"), t("col_branch"), t("col_version_match"), t("col_active_match")]
        )
        self._set_header_tooltips()
        self.controls_box.setTitle(t("actions"))
        self.backup_name_label.setText(t("backup_name"))
        self.backup_button.setText(t("backup_current"))
        self.switch_button.setText(t("switch_selected"))
        self.skip_auto_backup_checkbox.setText(t("skip_backup"))
        self.refresh_button.setText(t("refresh"))
        self.open_sets_button.setText(t("open_saved"))
        self.open_active_button.setText(t("open_active"))
        self.help_button.setText(t("menu_help"))
        self.details_box.setTitle(t("selected_set"))
        self.message_box.setTitle(t("backup_note"))
        self.save_message_button.setText(t("save_note"))

    def _set_header_tooltips(self) -> None:
        tooltips = [
            t("tip_set"),
            t("tip_branch"),
            t("tip_version_match"),
            t("tip_active_match"),
        ]
        for idx, tip in enumerate(tooltips):
            item = self.table.horizontalHeaderItem(idx)
            if item:
                item.setToolTip(tip)

    def _make_checkbox_widget(self, checked: bool) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setEnabled(False)
        layout.addWidget(checkbox)
        self.checkbox_widgets.append(checkbox)
        return container

    def active_deck_count(self) -> int:
        if not ACTIVE_DECKS_PATH.exists():
            return 0
        return len(list(ACTIVE_DECKS_PATH.glob("*.dek")))

    def selected_set_name(self) -> str | None:
        return self.selected_set

    def set_status(self, message: str) -> None:
        self.status_line.setText(message)

    def refresh_set_list(self) -> None:
        names = get_saved_set_names()
        current_branch = extract_branch_name(detect_game_version())
        active_hash = compute_active_decks_hash()
        previous_selection = self.selected_set

        self.table.setRowCount(0)
        self.checkbox_widgets.clear()

        for name in names:
            metadata = read_metadata(name)
            target_branch = extract_branch_name(metadata.game_version) or "-"
            branch_matches = bool(
                current_branch and target_branch != "-" and current_branch.lower() == target_branch.lower()
            )
            identical = bool(active_hash and metadata.content_hash and active_hash == metadata.content_hash)

            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(name)
            branch_item = QTableWidgetItem(target_branch)
            if branch_matches:
                tint = QColor(31, 122, 31)
            else:
                tint = QColor(178, 34, 34)
            name_item.setForeground(tint)
            branch_item.setForeground(tint)

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, branch_item)
            self.table.setCellWidget(row, 2, self._make_checkbox_widget(branch_matches))
            self.table.setCellWidget(row, 3, self._make_checkbox_widget(identical))
            self.table.setRowHeight(row, 28)

        self.active_path_label.setText(t("active_folder", path=ACTIVE_DECKS_PATH))
        self.active_summary_label.setText(t("active_count", count=self.active_deck_count()))
        self.saved_summary_label.setText(t("saved_count", count=len(names)))
        game_install_dir = get_game_install_dir()
        self.game_path_label.setText(
            t("game_path", path=game_install_dir) if game_install_dir else t("game_path_missing")
        )
        self.game_version_label.setText(t("game_version", version=detect_game_version()))

        if previous_selection and previous_selection in names:
            self.select_set(previous_selection)
        elif names:
            self.select_set(names[0])
        else:
            self.select_set(None)

    def select_set(self, set_name: str | None) -> None:
        self.selected_set = set_name
        if set_name is None:
            self.table.clearSelection()
            self.update_selected_details()
            return

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == set_name:
                self.table.selectRow(row)
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                break
        self.update_selected_details()

    def on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.selected_set = None
        else:
            self.selected_set = selected_items[0].text()
        self.update_selected_details()

    def update_selected_details(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            self.switch_button.setEnabled(False)
            self.save_message_button.setEnabled(False)
            self.details_label.setText(t("select_set"))
            self.message_edit.clear()
            return

        metadata = read_metadata(selected)
        created_text = t("unknown")
        if metadata.created_at:
            try:
                created_text = datetime.fromisoformat(metadata.created_at).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                created_text = metadata.created_at

        self.details_label.setText(
            t(
                "details",
                name=metadata.set_name,
                count=metadata.deck_count,
                created=created_text,
                version=metadata.game_version,
                hash=metadata.content_hash,
            )
        )
        self.message_edit.setPlainText(metadata.message)
        self.save_message_button.setEnabled(True)

        current_branch = extract_branch_name(detect_game_version())
        target_branch = extract_branch_name(metadata.game_version)
        branch_matches = bool(current_branch and target_branch and current_branch.lower() == target_branch.lower())
        self.switch_button.setEnabled(branch_matches)

    def refresh_clicked(self) -> None:
        self.refresh_set_list()
        self.set_status(t("refreshed"))

    def show_help(self) -> None:
        QMessageBox.information(
            self,
            t("about_title"),
            t("about_body"),
        )

    def set_language(self, language: str) -> None:
        global APP_LANGUAGE
        if language not in LANGUAGES or language == APP_LANGUAGE:
            return
        APP_LANGUAGE = language
        save_settings()
        self.retranslate_ui()
        self.refresh_set_list()
        self.update_selected_details()

    def show_options(self) -> None:
        global ACTIVE_DECKS_PATH, APP_LANGUAGE, AUTO_ROOT, STORAGE_ROOT
        dialog = OptionsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if not dialog.storage_edit.text().strip() or not dialog.active_edit.text().strip():
            QMessageBox.warning(self, t("invalid_folder_title"), t("folder_required"))
            return

        storage_root, active_decks_path, language = dialog.values()
        STORAGE_ROOT = storage_root
        ACTIVE_DECKS_PATH = active_decks_path
        AUTO_ROOT = STORAGE_ROOT / "_auto"
        APP_LANGUAGE = language if language in LANGUAGES else APP_LANGUAGE
        ensure_storage_root()
        save_settings()
        self.retranslate_ui()
        self.refresh_set_list()
        self.set_status(t("options_saved"))

    def open_active_decks(self) -> None:
        if not ACTIVE_DECKS_PATH.exists():
            QMessageBox.warning(self, t("app_title"), t("active_missing"))
            return
        open_in_explorer(ACTIVE_DECKS_PATH)

    def backup_current(self) -> None:
        set_name = self.backup_name_edit.text().strip()
        message = self.message_edit.toPlainText().strip()
        try:
            destination = backup_current_decks(set_name, message)
        except Exception as exc:
            QMessageBox.critical(self, t("backup_failed"), str(exc))
            self.set_status(str(exc))
            return

        self.refresh_set_list()
        self.select_set(set_name)
        self.backup_name_edit.setText(default_set_name())
        self.set_status(t("backup_created", path=destination))

    def switch_selected(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            QMessageBox.warning(self, t("app_title"), t("select_first"))
            return

        prompt = t("confirm_switch", name=selected)
        if not self.skip_auto_backup_checkbox.isChecked():
            prompt += t("confirm_auto_backup")

        if QMessageBox.question(self, t("confirm_switch_title"), prompt) != QMessageBox.StandardButton.Yes:
            return

        try:
            switch_to_set(selected, self.skip_auto_backup_checkbox.isChecked())
        except Exception as exc:
            QMessageBox.critical(self, t("switch_failed"), str(exc))
            self.set_status(str(exc))
            return

        self.refresh_set_list()
        self.select_set(selected)
        self.set_status(t("switch_done", name=selected))

    def save_message(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            return

        try:
            save_set_message(selected, self.message_edit.toPlainText().strip())
        except Exception as exc:
            QMessageBox.critical(self, t("save_note_failed"), str(exc))
            self.set_status(str(exc))
            return

        self.update_selected_details()
        self.set_status(t("save_note_done", name=selected))


def main() -> int:
    load_locales()
    load_settings()
    ensure_storage_root()
    stamp_missing_set_versions()
    app = QApplication.instance() or QApplication(sys.argv)
    window = DeckManagerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

import json
import os
import re
import shutil
import subprocess
import hashlib
import logging
import winreg
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from deck_manager_i18n import LocaleManager


BROKEN_ARROW_APP_ID = "1604270"

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, int, int], None]


@dataclass
class AppPaths:
    app_root: Path
    resource_root: Path
    settings_path: Path
    locales_root: Path
    default_storage_root: Path
    default_active_decks_path: Path
    app_icon_path: Path


@dataclass
class SetMetadata:
    set_name: str
    message: str
    created_at: str
    backup_path: str
    deck_count: int
    content_hash: str
    game_version: str


@dataclass
class DeckSetStatus:
    name: str
    metadata: SetMetadata
    target_branch: str
    branch_matches: bool
    identical_to_active: bool


class DeckManagerService:
    def __init__(self, paths: AppPaths, locale_manager: LocaleManager) -> None:
        self.paths = paths
        self.locale_manager = locale_manager
        self.storage_root = paths.default_storage_root
        self.active_decks_path = paths.default_active_decks_path
        self.auto_root = self.storage_root / "_auto"
        logger.debug("DeckManagerService initialized.")

    def load_settings(self) -> None:
        if not self.paths.settings_path.exists():
            return

        try:
            data = json.loads(self.paths.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        storage_root = data.get("storage_root")
        active_decks_path = data.get("active_decks_path")
        language = data.get("language")

        if isinstance(storage_root, str) and storage_root.strip():
            self.storage_root = Path(storage_root).expanduser()
        if isinstance(active_decks_path, str) and active_decks_path.strip():
            self.active_decks_path = Path(active_decks_path).expanduser()
        if language in self.locale_manager.languages:
            self.locale_manager.set_language(language)
        self.auto_root = self.storage_root / "_auto"

    def save_settings(self) -> None:
        data = {
            "storage_root": str(self.storage_root),
            "active_decks_path": str(self.active_decks_path),
            "language": self.locale_manager.current_language,
        }
        self.paths.settings_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def ensure_storage_root(self) -> None:
        bundled_storage_root = self.paths.resource_root / "deck_sets"
        if (
            not self.storage_root.exists()
            and bundled_storage_root.exists()
            and bundled_storage_root.resolve() != self.storage_root.resolve()
        ):
            shutil.copytree(bundled_storage_root, self.storage_root)
            return

        self.storage_root.mkdir(parents=True, exist_ok=True)

    def active_deck_count(self) -> int:
        if not self.active_decks_path.exists():
            return 0
        return len(list(self.active_decks_path.glob("*.dek")))

    def compute_active_decks_hash(self) -> str:
        if not self.active_decks_path.exists():
            return ""
        return self.compute_set_hash(self.active_decks_path)

    def get_saved_set_names(self) -> list[str]:
        self.ensure_storage_root()
        names = []
        for item in self.storage_root.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith("_auto") or item.name.startswith("_switch_"):
                continue
            names.append(item.name)
        return sorted(names, key=str.lower)

    def read_metadata(self, set_name: str) -> SetMetadata:
        set_path = self.storage_root / set_name
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
            content_hash = self.compute_set_hash(set_path)
        if not game_version:
            game_version = self.detect_game_version()

        return SetMetadata(
            set_name=set_name,
            message=message,
            created_at=created_at,
            backup_path=str(set_path),
            deck_count=deck_count,
            content_hash=content_hash,
            game_version=game_version,
        )

    def backup_current_decks(
        self,
        set_name: str,
        message: str,
        progress_callback: ProgressCallback | None = None,
        overwrite: bool = False,
    ) -> Path:
        self.validate_set_name(set_name)
        if not self.active_decks_path.exists():
            raise FileNotFoundError(f"Decks folder not found: {self.active_decks_path}")
        if self.is_game_running():
            raise RuntimeError(
                "Broken Arrow appears to be running. "
                "Close the game before backing up decks."
            )

        self.ensure_storage_root()
        destination = self.storage_root / set_name
        if destination.exists():
            if not overwrite:
                raise FileExistsError(f"Destination set already exists: {destination}")
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()

        destination.mkdir(parents=True, exist_ok=False)
        self.copy_directory_contents(
            self.active_decks_path,
            destination,
            progress_callback,
            "Copying deck files",
        )
        self.write_metadata(destination, set_name, message)
        return destination

    def switch_to_set(
        self,
        set_name: str,
        skip_auto_backup: bool,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        if not self.active_decks_path.exists():
            raise FileNotFoundError(f"Decks folder not found: {self.active_decks_path}")
        if self.is_game_running():
            raise RuntimeError(
                "Broken Arrow appears to be running. "
                "Close the game before switching deck sets."
            )

        source_set = self.storage_root / set_name
        if not source_set.exists():
            raise FileNotFoundError(f"Saved deck set not found: {source_set}")

        current_version = self.detect_game_version()
        current_branch = self.extract_branch_name(current_version)
        target_metadata = self.read_metadata(set_name)
        target_branch = self.extract_branch_name(target_metadata.game_version)

        if not current_branch:
            raise RuntimeError("Current game branch could not be detected from Steam appmanifest.")
        if not target_branch:
            raise RuntimeError(f'Saved set "{set_name}" does not have a valid branch stamp.')
        if current_branch.lower() != target_branch.lower():
            raise RuntimeError(
                f'Cannot restore "{set_name}" on branch "{current_branch}". '
                f'This set was stamped for branch "{target_branch}".'
            )

        self.ensure_storage_root()
        work_root = self.storage_root / f"_switch_{self.timestamp()}"
        current_snapshot = work_root / "current"
        current_snapshot.mkdir(parents=True, exist_ok=True)

        try:
            for item in list(self.active_decks_path.iterdir()):
                shutil.move(str(item), str(current_snapshot / item.name))

            self.copy_directory_contents(
                source_set,
                self.active_decks_path,
                progress_callback,
                "Restoring deck files",
            )

            if skip_auto_backup:
                shutil.rmtree(work_root, ignore_errors=True)
            else:
                self.auto_root.mkdir(parents=True, exist_ok=True)
                auto_name = f"active_before_{self.timestamp()}_to_{set_name}"
                shutil.move(str(current_snapshot), str(self.auto_root / auto_name))
                shutil.rmtree(work_root, ignore_errors=True)
        except Exception:
            try:
                self.remove_directory_contents(self.active_decks_path)
                if current_snapshot.exists():
                    self.copy_directory_contents(
                        current_snapshot,
                        self.active_decks_path,
                        progress_callback,
                        "Rolling back deck files",
                    )
            except Exception as restore_error:
                raise RuntimeError(
                    "Switch failed and restore also failed. "
                    f"Previous active decks remain in: {current_snapshot}"
                ) from restore_error
            raise

    def save_set_message(self, set_name: str, message: str) -> None:
        set_path = self.storage_root / set_name
        if not set_path.exists():
            raise FileNotFoundError(f"Saved deck set not found: {set_path}")

        current = self.read_metadata(set_name)
        self.write_metadata(
            set_path,
            current.set_name,
            message,
            current.created_at or datetime.now().isoformat(),
            current.game_version,
        )

    def stamp_missing_set_versions(self) -> None:
        current_version = self.detect_game_version()
        for set_name in self.get_saved_set_names():
            current = self.read_metadata(set_name)
            if current.game_version:
                continue
            self.write_metadata(
                self.storage_root / set_name,
                current.set_name,
                current.message,
                current.created_at or datetime.now().isoformat(),
                current_version,
            )

    def get_saved_set_statuses(self) -> list[DeckSetStatus]:
        current_branch = self.extract_branch_name(self.detect_game_version())
        active_hash = self.compute_active_decks_hash()
        statuses: list[DeckSetStatus] = []

        for name in self.get_saved_set_names():
            metadata = self.read_metadata(name)
            target_branch = self.extract_branch_name(metadata.game_version) or "-"
            branch_matches = bool(
                current_branch
                and target_branch != "-"
                and current_branch.lower() == target_branch.lower()
            )
            identical = bool(
                active_hash
                and metadata.content_hash
                and active_hash == metadata.content_hash
            )
            statuses.append(
                DeckSetStatus(
                    name=name,
                    metadata=metadata,
                    target_branch=target_branch,
                    branch_matches=branch_matches,
                    identical_to_active=identical,
                )
            )

        return statuses

    def open_in_explorer(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def default_set_name(self) -> str:
        return f"decks_{self.timestamp()}"

    def get_game_install_dir(self) -> Path | None:
        content = self.get_manifest_content()
        manifest_path = self.get_manifest_path()
        if not content or not manifest_path:
            return None

        install_match = re.search(r'"installdir"\s+"([^"]+)"', content)
        if not install_match:
            return None

        candidate = manifest_path.parent / "common" / install_match.group(1)
        if candidate.exists():
            return candidate
        return None

    def detect_game_version(self) -> str:
        steam_version = self.detect_version_from_steam_manifest()
        if steam_version:
            return steam_version

        exe_version = self.detect_version_from_exe()
        if exe_version:
            return exe_version

        return "Version: not detected"

    @staticmethod
    def extract_branch_name(version_text: str) -> str:
        match = re.search(r"Branch\s+([^|]+)", version_text)
        if not match:
            return ""
        return match.group(1).strip()

    @staticmethod
    def timestamp() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    @staticmethod
    def validate_set_name(set_name: str) -> None:
        invalid = set('<>:"/\\|?*')
        if not set_name.strip():
            raise ValueError("Backup name is required.")
        if any(char in invalid for char in set_name):
            raise ValueError(f"Set name contains invalid path characters: {set_name}")

    @staticmethod
    def copy_directory_contents(
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        progress_label: str = "Copying files",
    ) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        copy_items = [item for item in source.rglob("*") if item.is_file()]
        total = max(1, len(copy_items))

        if progress_callback:
            progress_callback(progress_label, 0, total)

        copied = 0
        for item in source.iterdir():
            target = destination / item.name
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                for nested in item.rglob("*"):
                    nested_target = target / nested.relative_to(item)
                    if nested.is_dir():
                        nested_target.mkdir(parents=True, exist_ok=True)
                        continue
                    nested_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(nested, nested_target)
                    copied += 1
                    if progress_callback:
                        progress_callback(progress_label, copied, total)
            else:
                shutil.copy2(item, target)
                copied += 1
                if progress_callback:
                    progress_callback(progress_label, copied, total)

    @staticmethod
    def remove_directory_contents(path: Path) -> None:
        if not path.exists():
            return
        for item in path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    @staticmethod
    def compute_set_hash(set_path: Path) -> str:
        digest = hashlib.sha256()
        deck_files = sorted(
            set_path.rglob("*.dek"),
            key=lambda path: str(path.relative_to(set_path)).lower(),
        )

        for item in deck_files:
            with item.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)

        return digest.hexdigest()

    def write_metadata(
        self,
        set_path: Path,
        set_name: str,
        message: str,
        created_at: str | None = None,
        game_version: str | None = None,
    ) -> None:
        metadata = {
            "SetName": set_name,
            "Message": message,
            "SourcePath": str(self.active_decks_path),
            "BackupPath": str(set_path),
            "CreatedAt": created_at or datetime.now().isoformat(),
            "ContentHash": self.compute_set_hash(set_path),
            "GameVersion": game_version or self.detect_game_version(),
            "Computer": os.environ.get("COMPUTERNAME", ""),
            "User": os.environ.get("USERNAME", ""),
        }
        (set_path / "_backup.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

    @staticmethod
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

    @staticmethod
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

    def get_steam_library_paths(self) -> list[Path]:
        steam_root = self.get_steam_root()
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

    def get_manifest_path(self) -> Path | None:
        for library in self.get_steam_library_paths():
            manifest = library / "steamapps" / f"appmanifest_{BROKEN_ARROW_APP_ID}.acf"
            if manifest.exists():
                return manifest
        return None

    def get_manifest_content(self) -> str:
        manifest_path = self.get_manifest_path()
        if not manifest_path:
            return ""
        try:
            return manifest_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def get_game_exe_path(self) -> Path | None:
        install_dir = self.get_game_install_dir()
        if not install_dir:
            return None
        exe_path = install_dir / "BrokenArrow.exe"
        if exe_path.exists():
            return exe_path
        return None

    def detect_version_from_steam_manifest(self) -> str:
        content = self.get_manifest_content()
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
                updated = datetime.fromtimestamp(
                    int(updated_match.group(1))
                ).strftime("%Y-%m-%d %H:%M:%S")
                details += f" | Updated {updated}"
            except ValueError:
                pass

        return f"Version: {details} (Steam)"

    def detect_version_from_exe(self) -> str:
        game_exe_path = self.get_game_exe_path()
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

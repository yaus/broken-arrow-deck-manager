import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from deck_manager_i18n import LocaleManager
from deck_manager_logic import AppPaths, DeckManagerService
from deck_manager_ui import DeckManagerWindow


APP_VERSION = "1.0.1"


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def build_paths() -> AppPaths:
    app_root = get_app_root()
    resource_root = Path(getattr(sys, "_MEIPASS", app_root)).resolve()
    app_icon_path = app_root / "assets" / "icons" / "broken_arrow_deck_manager_icon.ico"
    if not app_icon_path.exists():
        app_icon_path = resource_root / "broken_arrow_deck_manager_icon.ico"

    return AppPaths(
        app_root=app_root,
        resource_root=resource_root,
        settings_path=app_root / "deck_manager_settings.json",
        locales_root=app_root / "locales",
        default_storage_root=app_root / "deck_sets",
        default_active_decks_path=(
            Path.home()
            / "AppData"
            / "LocalLow"
            / "SteelBalalaikaStudio"
            / "BrokenArrow"
            / "Decks"
        ),
        app_icon_path=app_icon_path,
    )


def main() -> int:
    paths = build_paths()
    locale_manager = LocaleManager(paths.locales_root, paths.resource_root)
    locale_manager.load()

    service = DeckManagerService(paths, locale_manager)
    service.load_settings()
    service.ensure_storage_root()
    service.stamp_missing_set_versions()

    app = QApplication.instance() or QApplication(sys.argv)
    window = DeckManagerWindow(service, locale_manager, APP_VERSION)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

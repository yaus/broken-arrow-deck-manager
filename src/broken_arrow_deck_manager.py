import sys
import argparse
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from deck_manager_i18n import LocaleManager
from deck_manager_logic import AppPaths, DeckManagerService
from deck_manager_ui import DeckManagerWindow


APP_VERSION = "1.0.4"

logger = logging.getLogger(__name__)


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


def setup_logging(app_root: Path, debug_mode: bool) -> None:
    log_path = app_root / "deck_manager.log"
    level = logging.DEBUG if debug_mode else logging.INFO

    # Configure logging to both file and console (if console is available)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.info("Logging initialized. Version: %s", APP_VERSION)


def cli_verify(service: DeckManagerService) -> int:
    """Non-GUI verification of the manager state."""
    logger.info("--- Broken Arrow Deck Manager CLI Verify ---")
    logger.info("App Root: %s", service.paths.app_root)
    logger.info(
        "Storage Root: %s (Exists: %s)",
        service.storage_root,
        service.storage_root.exists(),
    )
    logger.info(
        "Active Decks: %s (Exists: %s)",
        service.active_decks_path,
        service.active_decks_path.exists(),
    )

    game_dir = service.get_game_install_dir()
    logger.info(
        "Game Install: %s",
        game_dir if game_dir else "NOT DETECTED",
    )
    logger.info("Game Version: %s", service.detect_game_version())

    statuses = service.get_saved_set_statuses()
    logger.info("Saved Sets Count: %s", len(statuses))
    for status in statuses:
        match_str = "[MATCH]" if status.identical_to_active else "       "
        branch_str = (
            "[SAME BRANCH]" if status.branch_matches else "[DIFF BRANCH]"
        )
        logger.info(
            "  %s %s | %s | %s",
            match_str,
            status.name.ljust(20),
            status.target_branch.ljust(15),
            branch_str,
        )

    logger.info("--- Verification Complete ---")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Broken Arrow Deck Manager")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to file",
    )
    parser.add_argument(
        "--cli-verify",
        action="store_true",
        help="Print status and exit without GUI",
    )
    args = parser.parse_args()

    paths = build_paths()
    setup_logging(paths.app_root, args.debug)

    locale_manager = LocaleManager(paths.locales_root, paths.resource_root)
    locale_manager.load()

    service = DeckManagerService(paths, locale_manager)
    service.load_settings()
    service.ensure_storage_root()
    service.stamp_missing_set_versions()

    if args.cli_verify:
        return cli_verify(service)

    app = QApplication.instance() or QApplication(sys.argv)
    window = DeckManagerWindow(service, locale_manager, APP_VERSION)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

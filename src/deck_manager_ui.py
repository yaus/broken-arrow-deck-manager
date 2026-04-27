from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from deck_manager_i18n import LocaleManager
from deck_manager_logic import DeckManagerService


class OptionsDialog(QDialog):
    def __init__(
        self,
        service: DeckManagerService,
        locale_manager: LocaleManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.locale_manager = locale_manager
        self.setWindowTitle(self.t("options_title"))
        self.resize(640, 170)

        layout = QFormLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.storage_edit = QLineEdit(str(self.service.storage_root))
        self.active_edit = QLineEdit(str(self.service.active_decks_path))
        self.language_combo = QComboBox()
        for code, label in self.locale_manager.languages.items():
            self.language_combo.addItem(label, code)
        current_index = max(0, self.language_combo.findData(self.locale_manager.current_language))
        self.language_combo.setCurrentIndex(current_index)

        layout.addRow(self.t("saved_folder"), self._folder_row(self.storage_edit))
        layout.addRow(self.t("active_decks_folder"), self._folder_row(self.active_edit))
        layout.addRow(self.t("language"), self.language_combo)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def t(self, key: str, **values: object) -> str:
        return self.locale_manager.translate(key, **values)

    def _folder_row(self, edit: QLineEdit) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        button = QPushButton(self.t("browse"))
        button.clicked.connect(lambda: self._browse_folder(edit))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    def _browse_folder(self, edit: QLineEdit) -> None:
        start = edit.text().strip() or str(self.service.paths.app_root)
        selected = QFileDialog.getExistingDirectory(self, self.t("options_title"), start)
        if selected:
            edit.setText(selected)

    def values(self) -> tuple[Path, Path, str]:
        return (
            Path(self.storage_edit.text().strip()).expanduser(),
            Path(self.active_edit.text().strip()).expanduser(),
            str(self.language_combo.currentData()),
        )


class DeckManagerWindow(QMainWindow):
    def __init__(
        self,
        service: DeckManagerService,
        locale_manager: LocaleManager,
        app_version: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.locale_manager = locale_manager
        self.app_version = app_version
        self.selected_set: str | None = None
        self.checkbox_widgets: list[QCheckBox] = []
        self.language_actions: dict[str, QAction] = {}
        if self.service.paths.app_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.service.paths.app_icon_path)))
        self.resize(980, 760)
        self._build_menu()
        self._build_ui()
        self.retranslate_ui()
        self.refresh_set_list()

    def t(self, key: str, **values: object) -> str:
        return self.locale_manager.translate(key, **values)

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
        for code in self.locale_manager.languages:
            action = QAction(self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, language=code: self.set_language(language)
            )
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
        self.storage_path_label = QLabel()
        self.active_summary_label = QLabel()
        self.saved_summary_label = QLabel()
        self.game_path_label = QLabel()
        self.game_version_label = QLabel()
        for label in [
            self.active_path_label,
            self.storage_path_label,
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
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self._set_header_tooltips()
        middle_layout.addWidget(self.table, 3)

        self.controls_box = QGroupBox()
        controls_layout = QVBoxLayout(self.controls_box)
        controls_layout.setSpacing(8)

        self.backup_name_label = QLabel()
        controls_layout.addWidget(self.backup_name_label)
        self.backup_name_edit = QLineEdit()
        self.backup_name_edit.setText(self.service.default_set_name())
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

        self.refresh_game_button = QPushButton()
        self.refresh_game_button.clicked.connect(self.refresh_game_status_clicked)
        controls_layout.addWidget(self.refresh_game_button)

        self.set_storage_button = QPushButton()
        self.set_storage_button.clicked.connect(self.set_backup_storage_path)
        controls_layout.addWidget(self.set_storage_button)

        self.open_sets_button = QPushButton()
        self.open_sets_button.clicked.connect(
            lambda: self.service.open_in_explorer(self.service.storage_root)
        )
        controls_layout.addWidget(self.open_sets_button)

        self.open_active_button = QPushButton()
        self.open_active_button.clicked.connect(self.open_active_decks)
        controls_layout.addWidget(self.open_active_button)
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
        message_layout.addWidget(
            self.save_message_button,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        root.addWidget(self.message_box, 1)

        self.status_line = QLineEdit()
        self.status_line.setReadOnly(True)
        root.addWidget(self.status_line)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.t("app_title"))
        self.file_menu.setTitle(self.t("menu_file"))
        self.language_menu.setTitle(self.t("menu_language"))
        self.help_menu.setTitle(self.t("menu_help"))
        self.options_action.setText(self.t("options"))
        self.exit_action.setText(self.t("exit"))
        self.about_action.setText(self.t("about"))
        for code, action in self.language_actions.items():
            action.setText(self.locale_manager.languages[code])
            action.setChecked(code == self.locale_manager.current_language)

        self.title_label.setText(self.t("app_title"))
        self.info_box.setTitle(self.t("environment"))
        self.table.setHorizontalHeaderLabels(
            [
                self.t("col_set"),
                self.t("col_branch"),
                self.t("col_version_match"),
                self.t("col_active_match"),
            ]
        )
        self._set_header_tooltips()
        self.controls_box.setTitle(self.t("actions"))
        self.backup_name_label.setText(self.t("backup_name"))
        self.backup_button.setText(self.t("backup_current"))
        self.switch_button.setText(self.t("switch_selected"))
        self.skip_auto_backup_checkbox.setText(self.t("skip_backup"))
        self.refresh_button.setText(self.t("refresh"))
        self.refresh_game_button.setText(self.t("refresh_game_status"))
        self.set_storage_button.setText(self.t("set_backup_storage"))
        self.open_sets_button.setText(self.t("open_saved"))
        self.open_active_button.setText(self.t("open_active"))
        self.details_box.setTitle(self.t("selected_set"))
        self.message_box.setTitle(self.t("backup_note"))
        self.save_message_button.setText(self.t("save_note"))

    def _set_header_tooltips(self) -> None:
        tooltips = [
            self.t("tip_set"),
            self.t("tip_branch"),
            self.t("tip_version_match"),
            self.t("tip_active_match"),
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

    def selected_set_name(self) -> str | None:
        return self.selected_set

    def set_status(self, message: str) -> None:
        self.status_line.setText(message)

    def update_game_status_labels(self) -> None:
        game_install_dir = self.service.get_game_install_dir()
        self.game_path_label.setText(
            self.t("game_path", path=game_install_dir)
            if game_install_dir
            else self.t("game_path_missing")
        )
        self.game_version_label.setText(
            self.t("game_version", version=self.service.detect_game_version())
        )

    def refresh_set_list(self) -> None:
        statuses = self.service.get_saved_set_statuses()
        names = [status.name for status in statuses]
        previous_selection = self.selected_set

        self.table.setRowCount(0)
        self.checkbox_widgets.clear()

        for status in statuses:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(status.name)
            branch_item = QTableWidgetItem(status.target_branch)
            tint = QColor(31, 122, 31) if status.branch_matches else QColor(178, 34, 34)
            name_item.setForeground(tint)
            branch_item.setForeground(tint)

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, branch_item)
            self.table.setCellWidget(row, 2, self._make_checkbox_widget(status.branch_matches))
            self.table.setCellWidget(row, 3, self._make_checkbox_widget(status.identical_to_active))
            self.table.setRowHeight(row, 28)

        self.active_path_label.setText(
            self.t("active_folder", path=self.service.active_decks_path)
        )
        self.storage_path_label.setText(
            self.t("backup_storage_folder", path=self.service.storage_root)
        )
        self.active_summary_label.setText(
            self.t("active_count", count=self.service.active_deck_count())
        )
        self.saved_summary_label.setText(self.t("saved_count", count=len(statuses)))
        self.update_game_status_labels()

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
            self.details_label.setText(self.t("select_set"))
            self.message_edit.clear()
            return

        metadata = self.service.read_metadata(selected)
        created_text = self.t("unknown")
        if metadata.created_at:
            try:
                created_text = datetime.fromisoformat(
                    metadata.created_at
                ).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                created_text = metadata.created_at

        self.details_label.setText(
            self.t(
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

        current_branch = self.service.extract_branch_name(self.service.detect_game_version())
        target_branch = self.service.extract_branch_name(metadata.game_version)
        branch_matches = bool(
            current_branch
            and target_branch
            and current_branch.lower() == target_branch.lower()
        )
        self.switch_button.setEnabled(branch_matches)

    def refresh_clicked(self) -> None:
        self.refresh_set_list()
        self.set_status(self.t("refreshed"))

    def refresh_game_status_clicked(self) -> None:
        self.refresh_set_list()
        self.set_status(self.t("game_status_refreshed"))

    def show_help(self) -> None:
        QMessageBox.information(
            self,
            self.t("about_title"),
            self.t("about_body", version=self.app_version),
        )

    def set_language(self, language: str) -> None:
        if language not in self.locale_manager.languages:
            return
        if language == self.locale_manager.current_language:
            return
        self.locale_manager.set_language(language)
        self.service.save_settings()
        self.retranslate_ui()
        self.refresh_set_list()
        self.update_selected_details()

    def show_options(self) -> None:
        dialog = OptionsDialog(self.service, self.locale_manager, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if not dialog.storage_edit.text().strip() or not dialog.active_edit.text().strip():
            QMessageBox.warning(self, self.t("invalid_folder_title"), self.t("folder_required"))
            return

        storage_root, active_decks_path, language = dialog.values()
        self.service.storage_root = storage_root
        self.service.active_decks_path = active_decks_path
        self.service.auto_root = self.service.storage_root / "_auto"
        if language in self.locale_manager.languages:
            self.locale_manager.set_language(language)
        self.service.ensure_storage_root()
        self.service.save_settings()
        self.retranslate_ui()
        self.refresh_set_list()
        self.set_status(self.t("options_saved"))

    def set_backup_storage_path(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.t("set_backup_storage_title"),
            str(self.service.storage_root),
        )
        if not selected:
            return

        self.service.storage_root = Path(selected).expanduser()
        self.service.auto_root = self.service.storage_root / "_auto"
        self.service.ensure_storage_root()
        self.service.save_settings()
        self.refresh_set_list()
        self.set_status(self.t("backup_storage_saved", path=self.service.storage_root))

    def open_active_decks(self) -> None:
        if not self.service.active_decks_path.exists():
            QMessageBox.warning(self, self.t("app_title"), self.t("active_missing"))
            return
        self.service.open_in_explorer(self.service.active_decks_path)

    def create_progress_callback(self, title: str):
        progress = QProgressDialog(self)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setMinimum(0)
        progress.setMaximum(1)
        progress.setValue(0)

        def update(label: str, value: int, maximum: int) -> None:
            progress.setLabelText(label)
            progress.setMaximum(max(1, maximum))
            progress.setValue(min(value, progress.maximum()))
            QApplication.processEvents()

        return progress, update

    def backup_current(self) -> None:
        set_name = self.backup_name_edit.text().strip()
        message = self.message_edit.toPlainText().strip()
        progress, progress_callback = self.create_progress_callback(
            self.t("backup_progress_title")
        )
        try:
            destination = self.service.backup_current_decks(
                set_name,
                message,
                progress_callback,
            )
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, self.t("backup_failed"), str(exc))
            self.set_status(str(exc))
            return

        progress.close()

        self.refresh_set_list()
        self.select_set(set_name)
        self.backup_name_edit.setText(self.service.default_set_name())
        self.set_status(self.t("backup_created", path=destination))

    def switch_selected(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            QMessageBox.warning(self, self.t("app_title"), self.t("select_first"))
            return

        prompt = self.t("confirm_switch", name=selected)
        if not self.skip_auto_backup_checkbox.isChecked():
            prompt += self.t("confirm_auto_backup")

        result = QMessageBox.question(self, self.t("confirm_switch_title"), prompt)
        if result != QMessageBox.StandardButton.Yes:
            return

        progress, progress_callback = self.create_progress_callback(
            self.t("restore_progress_title")
        )
        try:
            self.service.switch_to_set(
                selected,
                self.skip_auto_backup_checkbox.isChecked(),
                progress_callback,
            )
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, self.t("switch_failed"), str(exc))
            self.set_status(str(exc))
            return

        progress.close()

        self.refresh_set_list()
        self.select_set(selected)
        self.set_status(self.t("switch_done", name=selected))

    def save_message(self) -> None:
        selected = self.selected_set_name()
        if not selected:
            return

        try:
            self.service.save_set_message(selected, self.message_edit.toPlainText().strip())
        except Exception as exc:
            QMessageBox.critical(self, self.t("save_note_failed"), str(exc))
            self.set_status(str(exc))
            return

        self.update_selected_details()
        self.set_status(self.t("save_note_done", name=selected))

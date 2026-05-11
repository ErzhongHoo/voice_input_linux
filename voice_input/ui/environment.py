from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from voice_input.config import AppConfig
from voice_input.environment import EnvironmentCheck, format_check_report, run_environment_checks, summarize_checks
from voice_input.inject.base import InjectionError
from voice_input.inject.clipboard_injector import copy_to_clipboard


class EnvironmentDialog(QDialog):
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.checks: list[EnvironmentCheck] = []
        self.setWindowTitle("环境检查")
        self.setMinimumSize(780, 560)
        self.setObjectName("EnvironmentDialog")

        self.summary = QLabel("")
        self.summary.setObjectName("SummaryLabel")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["状态", "分类", "项目", "结果"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_selected_detail)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)

        self.refresh_button = QPushButton("刷新")
        self.copy_button = QPushButton("复制报告")
        self.close_button = QPushButton("关闭")
        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button.clicked.connect(self._copy_report)
        self.close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.detail)
        layout.addLayout(buttons)

        self._apply_style()
        self.refresh()

    def refresh(self) -> None:
        self.checks = run_environment_checks(self.config)
        self.summary.setText(summarize_checks(self.checks))
        self.table.setRowCount(len(self.checks))
        for row, check in enumerate(self.checks):
            items = [
                QTableWidgetItem(_status_text(check.status)),
                QTableWidgetItem(check.category),
                QTableWidgetItem(check.name),
                QTableWidgetItem(check.summary),
            ]
            for item in items:
                item.setData(Qt.ItemDataRole.UserRole, check)
                item.setForeground(_status_color(check.status))
            for column, item in enumerate(items):
                self.table.setItem(row, column, item)
        if self.checks:
            self.table.selectRow(0)
        self._show_selected_detail()

    def _show_selected_detail(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            self.detail.clear()
            return
        check = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if not isinstance(check, EnvironmentCheck):
            self.detail.clear()
            return
        lines = [f"{check.category} / {check.name}", check.summary]
        if check.detail:
            lines.extend(["", check.detail])
        self.detail.setPlainText("\n".join(lines))

    def _copy_report(self) -> None:
        try:
            copy_to_clipboard(format_check_report(self.checks))
        except InjectionError as exc:
            QMessageBox.warning(self, "复制失败", str(exc))

    def _apply_style(self) -> None:
        dark = self.palette().window().color().lightness() < 128
        if dark:
            bg = "#171717"
            panel = "#242424"
            field = "#18181b"
            border = "#3f3f46"
            text = "#f4f4f5"
            muted = "#a1a1aa"
            hover = "#2f2f32"
            selected = "#134e4a"
            selected_text = "#ccfbf1"
            focus = "#2dd4bf"
        else:
            bg = "#f6f7f9"
            panel = "#ffffff"
            field = "#f9fafb"
            border = "#d5d9e2"
            text = "#18181b"
            muted = "#667085"
            hover = "#f3f4f6"
            selected = "#ccfbf1"
            selected_text = "#115e59"
            focus = "#0f766e"
        self.setStyleSheet(
            f"""
            QDialog#EnvironmentDialog {{
                background: {bg};
                color: {text};
                font-size: 14px;
            }}
            QLabel#SummaryLabel {{
                color: {text};
                font-size: 18px;
                font-weight: 700;
                padding: 4px 0;
            }}
            QTableWidget,
            QPlainTextEdit {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
                color: {text};
                selection-background-color: {selected};
                selection-color: {selected_text};
            }}
            QHeaderView::section {{
                background: {field};
                border: 0;
                border-bottom: 1px solid {border};
                padding: 9px 10px;
                color: {muted};
                font-weight: 700;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {field};
            }}
            QTableWidget::item:selected {{
                background: {selected};
                color: {selected_text};
            }}
            QPlainTextEdit {{
                padding: 10px 12px;
            }}
            QPushButton {{
                min-height: 38px;
                border-radius: 8px;
                padding: 8px 16px;
                border: 1px solid {border};
                background: {panel};
                color: {text};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {hover};
                border-color: {focus};
            }}
            QPushButton:pressed {{
                background: {selected};
                color: {selected_text};
            }}
            """
        )


def _status_text(status: str) -> str:
    return {
        "ok": "正常",
        "warn": "注意",
        "fail": "失败",
        "info": "信息",
    }.get(status, status)


def _status_color(status: str) -> QBrush:
    colors = {
        "ok": QColor("#15803d"),
        "warn": QColor("#b45309"),
        "fail": QColor("#b42318"),
        "info": QColor("#1d4ed8"),
    }
    return QBrush(colors.get(status, QColor("#667085")))

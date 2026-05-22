from __future__ import annotations

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QDialog


class CharacterDetailDialog(QDialog):
    def __init__(self, owner: "NovelQtMainWindow") -> None:
        super().__init__(owner)
        self._owner = owner
        self.setModal(False)
        self.resize(760, 720)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._owner._confirm_character_edit_navigation():
            super().closeEvent(event)
            return
        event.ignore()

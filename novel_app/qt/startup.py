from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget


APP_SUBTITLE = "\u5c0f\u8bf4\u521b\u4f5c\u5de5\u4f5c\u53f0"
DEFAULT_STAGE = "\u6b63\u5728\u542f\u52a8..."
DEFAULT_DETAIL = "\u8bf7\u7a0d\u5019"
UI_FONT_FAMILY = "Microsoft YaHei UI"
STARTUP_IMAGE = Path(__file__).resolve().parent / "assets" / "startup_anime.jpg"


class StartupSplash(QWidget):
    def __init__(self, app_name: str = "\u7075\u67a2") -> None:
        super().__init__(None)
        self.app_name = app_name
        self.stage_text = DEFAULT_STAGE
        self.detail_text = DEFAULT_DETAIL
        self.frame_index = 0
        self.background_pixmap = QPixmap(str(STARTUP_IMAGE))
        self.setFixedSize(620, 380)
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._center_on_screen()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.center().x() - self.width() // 2,
            geometry.center().y() - self.height() // 2,
        )

    def show_stage(self, stage: str, detail: str = "") -> None:
        self.set_stage(stage, detail)
        self.show()
        self.raise_()
        QApplication.processEvents()

    def set_stage(self, stage: str, detail: str = "") -> None:
        self.stage_text = str(stage or DEFAULT_STAGE)
        self.detail_text = str(detail or DEFAULT_DETAIL)
        self.update()
        QApplication.processEvents()

    def finish(self, target: QWidget | None = None) -> None:
        self.set_stage("\u542f\u52a8\u5b8c\u6210", "\u6b63\u5728\u6253\u5f00\u5de5\u4f5c\u53f0")
        if target is not None:
            target.raise_()
        QTimer.singleShot(260, self.close)

    def _tick(self) -> None:
        self.frame_index = (self.frame_index + 1) % 360
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_anime_splash(painter)
        painter.end()

    def _paint_anime_splash(self, painter: QPainter) -> None:
        bounds = QRectF(0, 0, self.width(), self.height())
        shell = bounds.adjusted(0, 0, 0, 0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(7, 11, 18, 96))
        painter.drawRoundedRect(shell.adjusted(0, 9, 0, 9), 30, 30)

        clip = QPainterPath()
        clip.addRoundedRect(shell, 30, 30)
        painter.save()
        painter.setClipPath(clip)
        if not self.background_pixmap.isNull():
            painter.drawPixmap(shell.toRect(), self.background_pixmap, self.background_pixmap.rect())
        else:
            self._draw_fallback_background(painter, shell)
        self._draw_image_overlays(painter, shell)
        painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 115), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(shell.adjusted(0.5, 0.5, -0.5, -0.5), 30, 30)

    def _draw_fallback_background(self, painter: QPainter, bounds: QRectF) -> None:
        bg = QLinearGradient(bounds.left(), bounds.top(), bounds.right(), bounds.bottom())
        bg.setColorAt(0, QColor(242, 230, 216))
        bg.setColorAt(0.5, QColor(65, 75, 96))
        bg.setColorAt(1, QColor(14, 20, 33))
        painter.setBrush(bg)
        painter.drawRect(bounds)

    def _draw_image_overlays(self, painter: QPainter, bounds: QRectF) -> None:
        bottom = QLinearGradient(0, bounds.top() + 150, 0, bounds.bottom())
        bottom.setColorAt(0, QColor(7, 11, 18, 0))
        bottom.setColorAt(0.56, QColor(7, 11, 18, 96))
        bottom.setColorAt(1, QColor(7, 11, 18, 210))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bottom)
        painter.drawRect(bounds)

        left = QLinearGradient(bounds.left(), 0, bounds.left() + 330, 0)
        left.setColorAt(0, QColor(7, 11, 18, 150))
        left.setColorAt(0.62, QColor(7, 11, 18, 42))
        left.setColorAt(1, QColor(7, 11, 18, 0))
        painter.setBrush(left)
        painter.drawRect(bounds)

        self._draw_brand(painter)
        self._draw_status_area(painter)
        self._draw_light_sweep(painter)

    def _draw_brand(self, painter: QPainter) -> None:
        title_font = QFont(UI_FONT_FAMILY)
        title_font.setPointSize(32)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 252, 246))
        painter.drawText(QRectF(42, 224, 230, 54), Qt.AlignmentFlag.AlignLeft, self.app_name)

        subtitle_font = QFont(UI_FONT_FAMILY)
        subtitle_font.setPointSize(10)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(220, 233, 232, 222))
        painter.drawText(QRectF(45, 273, 240, 24), Qt.AlignmentFlag.AlignLeft, APP_SUBTITLE)

        flame_x = 137 + math.sin(self.frame_index / 14) * 2
        self._draw_teal_flame(painter, flame_x, 227, 13, 210, self.frame_index / 10)

    def _draw_status_area(self, painter: QPainter) -> None:
        stage_font = QFont(UI_FONT_FAMILY)
        stage_font.setPointSize(12)
        stage_font.setBold(True)
        painter.setFont(stage_font)
        painter.setPen(QColor(246, 250, 250, 235))
        painter.drawText(QRectF(44, 304, 360, 27), Qt.AlignmentFlag.AlignLeft, self.stage_text)

        detail_font = QFont(UI_FONT_FAMILY)
        detail_font.setPointSize(9)
        painter.setFont(detail_font)
        painter.setPen(QColor(201, 218, 220, 210))
        painter.drawText(QRectF(44, 329, 360, 22), Qt.AlignmentFlag.AlignLeft, self.detail_text)

        pulse = 0.5 + 0.5 * math.sin(self.frame_index / 8)
        ring_rect = QRectF(534, 304, 30, 30)
        painter.setPen(QPen(QColor(235, 238, 241, 90), 3))
        painter.drawEllipse(ring_rect)
        arc = QPen(QColor(21, 223, 201, 230), 3)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        painter.drawArc(ring_rect, self.frame_index * 74, 120 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(246, 147, 79, int(90 + pulse * 110)))
        painter.drawEllipse(QRectF(559, 299, 8, 8))

        track = QRectF(42, 357, 536, 7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(244, 248, 250, 72))
        painter.drawRoundedRect(track, 4, 4)
        phase = (self.frame_index % 124) / 124
        bar_width = 176
        bar_x = track.left() + phase * (track.width() - bar_width)
        bar = QLinearGradient(bar_x, 0, bar_x + bar_width, 0)
        bar.setColorAt(0, QColor(21, 223, 201, 22))
        bar.setColorAt(0.48, QColor(21, 223, 201, 245))
        bar.setColorAt(1, QColor(246, 147, 79, 58))
        painter.setBrush(bar)
        painter.drawRoundedRect(QRectF(bar_x, track.top(), bar_width, track.height()), 4, 4)

    def _draw_light_sweep(self, painter: QPainter) -> None:
        sweep_x = -140 + (self.frame_index % 180) / 180 * (self.width() + 280)
        sweep = QLinearGradient(sweep_x - 60, 0, sweep_x + 60, self.height())
        sweep.setColorAt(0, QColor(255, 255, 255, 0))
        sweep.setColorAt(0.5, QColor(255, 255, 255, 34))
        sweep.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sweep)
        painter.drawRect(QRectF(sweep_x - 60, 0, 120, self.height()))

    def _draw_teal_flame(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        size: float,
        alpha: int,
        phase: float,
    ) -> None:
        wiggle = math.sin(phase) * size * 0.12
        path = QPainterPath()
        path.moveTo(cx, cy - size - wiggle)
        path.cubicTo(cx + size * 0.84, cy - size * 0.42, cx + size * 0.25, cy + size * 0.22, cx + size * 0.62, cy + size * 0.78)
        path.cubicTo(cx + size * 0.1, cy + size * 0.44, cx - size * 0.1, cy + size * 1.02, cx - size * 0.72, cy + size * 0.46)
        path.cubicTo(cx - size * 0.36, cy + size * 0.22, cx - size * 0.78, cy - size * 0.42, cx, cy - size - wiggle)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 205, 187, alpha))
        painter.drawPath(path)
        painter.setBrush(QColor(112, 255, 229, min(255, alpha + 20)))
        painter.drawEllipse(QRectF(cx - size * 0.16, cy - size * 0.24, size * 0.32, size * 0.48))

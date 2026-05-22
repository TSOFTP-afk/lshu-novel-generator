from __future__ import annotations

import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENDOR_DIR = BASE_DIR / "vendor"

if VENDOR_DIR.exists():
    vendor_path = str(VENDOR_DIR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)

APP_ICON = BASE_DIR / "packaging" / "app_icon.ico"


def _startup_splash_enabled() -> bool:
    return (
        os.environ.get("SIMPLE_AI_NOVEL_SMOKE_EXIT") != "1"
        and os.environ.get("SIMPLE_AI_NOVEL_QT_OFFSCREEN") != "1"
        and os.environ.get("SIMPLE_AI_NOVEL_NATIVE_SPLASH") != "1"
    )


def main() -> None:
    app = None
    splash = None
    if _startup_splash_enabled():
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication

        from novel_app.qt.startup import StartupSplash

        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("灵枢v1.3")
        if APP_ICON.exists():
            app.setWindowIcon(QIcon(str(APP_ICON)))
        splash = StartupSplash("灵枢")
        splash.show_stage("正在启动灵枢", "准备应用环境")

    if splash is not None:
        splash.set_stage("正在加载数据模块", "准备数据库与本地资料")
    from novel_app.database import Database

    database = Database()
    if splash is not None:
        splash.set_stage("正在初始化数据库", "检查旧版本数据与表结构")
    database.initialize()

    if splash is not None:
        splash.set_stage("正在加载 AI 配置", "读取模型与用途设置")
    from novel_app.ai_service import SimpleAIService

    ai_service = SimpleAIService.from_env()
    if os.environ.get("SIMPLE_AI_NOVEL_SMOKE_EXIT") == "1":
        database.close()
        return

    if splash is not None:
        splash.set_stage("正在加载主界面", "构建编辑器、抽屉与后台服务")
    from novel_app.qt_app import run_qt_app

    try:
        raise SystemExit(run_qt_app(database=database, ai_service=ai_service, startup_splash=splash))
    finally:
        if splash is not None:
            splash.close()
        database.close()


if __name__ == "__main__":
    main()

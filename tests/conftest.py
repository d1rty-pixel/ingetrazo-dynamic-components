import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ingetrazo-source"))

import pytest


@pytest.fixture(scope="session")
def qtapp():
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("DynamicComponentsTests")
    app.setApplicationName("DynamicComponentsTests")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(ROOT / ".test-state"))
    return app

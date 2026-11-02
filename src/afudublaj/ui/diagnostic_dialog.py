"""Diagnostics / help dialog — a system summary to paste into bug reports."""
import logging
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from afudublaj import APP_NAME, __app_name__, __version__
from afudublaj.i18n import t

logger = logging.getLogger(__name__)

ISSUES_URL = 'https://github.com/keremss7/lingolay/issues/new/choose'

_STYLE = """
QDialog {
    background-color: #0E1117;
    color: #E2E8F0;
}
QLabel {
    color: #9CA3AF;
    font-size: 13px;
}
QTextEdit {
    background-color: #161B27;
    border: 1px solid #1C2333;
    border-radius: 6px;
    color: #E2E8F0;
    padding: 8px;
}
QPushButton {
    background-color: #5B6CF8;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #4B5BE8;
}
QPushButton#btn_sec {
    background-color: #1C2333;
    color: #E2E8F0;
    border: 1px solid #283347;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 12px;
}
QPushButton#btn_sec:hover {
    background-color: #242D40;
    border-color: #5B6CF8;
    color: #5B6CF8;
}
"""

def _module_version(name):
    try:
        mod = __import__(name)
        return f"{getattr(mod, '__version__', '?')} (OK)"
    except Exception as e:
        return f'MISSING — {e}'


def collect_diagnostics():
    """
    Collect the whole system and app state as a single text block.
    Must never raise — every item is gathered independently.
    """
    lines = [f'{APP_NAME} — Diagnostics', '=' * 50]
    lines.append(f'App version    : {__version__}')
    lines.append(f'Python         : {sys.version.split()[0]}')
    lines.append(f'Platform       : {platform.platform()}')
    lines.append(f"Frozen (EXE)   : {getattr(sys, 'frozen', False)}")
    for mod in ('PySide6', 'ctranslate2', 'tokenizers', 'numpy', 'cv2', 'mss', 'deepl', 'piper', 'pygame'):
        lines.append(f'{mod:<15}: {_module_version(mod)}')
    try:
        from afudublaj.ocr.windows_ocr import WINDOWS_OCR_AVAILABLE, WINDOWS_OCR_IMPORT_ERROR
        lines.append(f"Windows OCR    : {'OK' if WINDOWS_OCR_AVAILABLE else 'MISSING — ' + WINDOWS_OCR_IMPORT_ERROR}")
    except Exception as e:
        lines.append(f'Windows OCR    : check failed ({e})')
    if platform.system() == 'Windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64') as k:
                ver, _ = winreg.QueryValueEx(k, 'Version')
                lines.append(f'VC++ Redist x64: {ver}')
        except FileNotFoundError:
            lines.append('VC++ Redist x64: NOT INSTALLED — vc_redist.x64.exe required')
        except Exception as e:
            lines.append(f'VC++ Redist x64: check failed ({e})')

    lines += ['', '--- Settings ---']
    try:
        from afudublaj.core.config import get_settings
        s = get_settings()
        lines.append(f'Engine         : {s.translation_engine}')
        lines.append(f'Source/Target  : {s.source_lang} -> {s.target_lang}')
        lines.append(f'OCR language   : {s.ocr_language}')
        mp = Path(s.nllb_model_dir)
        lines.append(f'NLLB model dir : {mp}')
        lines.append(f"  has model.bin: {(mp / 'model.bin').exists()}")
        lines.append(f"  has tokenizer: {(mp / 'tokenizer.json').exists()}")
    except Exception as e:
        lines.append(f'Could not read settings: {e}')

    lines += ['', '--- Models ---']
    try:
        from afudublaj.models.manager import get_model_manager
        from afudublaj.models.manifest import ALL_ASSETS
        mgr = get_model_manager()
        for mid in ALL_ASSETS:
            lines.append(f"{mid:<15}: {'installed' if mgr.is_installed(mid) else 'missing'}")
    except Exception as e:
        lines.append(f'Could not read model status: {e}')

    lines += ['', '--- Log ---']
    try:
        from afudublaj.core.paths import LOG_FILE
        lines.append(f'Log file       : {LOG_FILE}')
        if LOG_FILE.exists():
            lines.append(f'  size         : {LOG_FILE.stat().st_size / 1024:.1f} KB')
    except Exception as e:
        lines.append(f'Could not read log info: {e}')
    return '\n'.join(lines)


class DiagnosticDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t('Diagnostics / Help'))
        self.resize(620, 520)
        self.setStyleSheet(_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        info = QLabel(t('Having a problem? Copy the information below and paste it when you open an issue on GitHub.'))
        info.setWordWrap(True)
        lay.addWidget(info)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont('Consolas' if sys.platform == 'win32' else 'Menlo', 10))
        self._text.setPlainText(collect_diagnostics())
        lay.addWidget(self._text, 1)
        row = QHBoxLayout()
        btn_copy = QPushButton(t('Copy'))
        btn_copy.clicked.connect(self._copy)
        btn_logs = QPushButton(t('Open log folder'))
        btn_logs.setObjectName('btn_sec')
        btn_logs.clicked.connect(self._open_logs)
        btn_issue = QPushButton(t('Report a bug (GitHub)'))
        btn_issue.setObjectName('btn_sec')
        btn_issue.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ISSUES_URL)))
        btn_close = QPushButton(t('Close'))
        btn_close.setObjectName('btn_sec')
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_copy)
        row.addWidget(btn_logs)
        row.addWidget(btn_issue)
        row.addStretch()
        row.addWidget(btn_close)
        lay.addLayout(row)

    def _copy(self):
        QGuiApplication.clipboard().setText(self._text.toPlainText())

    def _open_logs(self):
        from afudublaj.core.paths import LOGS_DIR
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOGS_DIR)))

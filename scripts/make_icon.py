"""Generate the app icon (PNG + ICO) with Qt — no external design assets needed.

Usage: python scripts/make_icon.py
"""
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'src' / 'lingolay' / 'assets'


def render(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    s = size / 256.0

    # Ana arkaplan: yuvarlatılmış kare (Afu koyu tonu #0E1117)
    bg_path = QPainterPath()
    bg_path.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)
    p.fillPath(bg_path, QColor('#0E1117'))

    # Hafif çerçeve
    p.setPen(QPen(QColor('#1C2333'), 2 * s))
    p.drawPath(bg_path)

    # Çeviri konuşma balonu gövdesi (Afu ACCENT gradient: #5B6CF8 -> #7C3AED)
    bubble_grad = QLinearGradient(32 * s, 32 * s, 224 * s, 200 * s)
    bubble_grad.setColorAt(0.0, QColor('#5B6CF8'))
    bubble_grad.setColorAt(1.0, QColor('#7C3AED'))

    bubble_path = QPainterPath()
    bubble_rect = QRectF(28 * s, 34 * s, 200 * s, 150 * s)
    bubble_path.addRoundedRect(bubble_rect, 36 * s, 36 * s)
    # Konuşma balonu kuyruğu
    tail_path = QPainterPath()
    tail_path.moveTo(60 * s, 170 * s)
    tail_path.lineTo(44 * s, 214 * s)
    tail_path.lineTo(96 * s, 180 * s)
    tail_path.closeSubpath()
    bubble_path = bubble_path.united(tail_path)

    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(bubble_path, bubble_grad)

    # "A" motifi (balon içinde ortalı beyaz kalın harf)
    f = QFont('Segoe UI', int(96 * s))
    f.setWeight(QFont.Weight.ExtraBold)
    p.setFont(f)
    p.setPen(QColor('#FFFFFF'))
    p.drawText(QRectF(28 * s, 28 * s, 200 * s, 150 * s), Qt.AlignmentFlag.AlignCenter, 'A')

    # Sağ alt çeviri / altyazı çizgileri
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(226, 232, 240, 220))
    p.drawRoundedRect(QRectF(130 * s, 196 * s, 72 * s, 8 * s), 4 * s, 4 * s)
    p.setBrush(QColor(156, 163, 175, 180))
    p.drawRoundedRect(QRectF(150 * s, 212 * s, 52 * s, 7 * s), 3.5 * s, 3.5 * s)

    p.end()
    return img


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    OUT.mkdir(parents=True, exist_ok=True)
    render(256).save(str(OUT / 'icon.png'))
    ok = render(256).save(str(OUT / 'icon.ico'), 'ICO')
    print('icon.png written; icon.ico', 'written' if ok else 'NOT supported by this Qt build')


if __name__ == '__main__':
    main()

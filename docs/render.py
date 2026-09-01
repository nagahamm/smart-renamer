"""README に貼るリネームダイアログの画像を生成する。

    .venv/bin/python docs/render.py

`docs/dialog-light.png` と `docs/dialog-dark.png` を上書きする。
`popup_ui.py` の見た目を変えたら実行し直すこと。
"""
import os
import sys
import tempfile

# 実画面を開かずに描画する。ヘッドレスでも動く
os.environ["QT_QPA_PLATFORM"] = "offscreen"

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DOCS_DIR))

from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import QApplication

from popup_ui import RenameDialog

WINDOW_SIZE = (1160, 720)

# 候補は config.yaml の命名規則（3. 自動車関連）に沿った架空の例
CANDIDATES = [
    "2026-05-06__Car__Camry_ACV40R_整備部品_0450.00AUD_Receipt",
    "2026-05-06__Car__Camry_ACV40R_ブレーキパッド交換_0450.00AUD_Receipt",
    "2026-05-06__Other__Northside_Auto_Service_請求書_Summary",
]

# current_theme() は QPalette の地の色の明るさでライト／ダークを判定する
BACKGROUNDS = {"light": "#ececec", "dark": "#1e1e1e"}


def draw_sample_invoice(path):
    """プレビューに写す画像を作る。

    実際のスクリーンショットを README に載せないよう、その場で架空の請求書を描く。
    シートの下から覗く部分にも中身が来るよう、横長で全体に内容を散らす。
    """
    pixmap = QPixmap(1600, 1000)
    pixmap.fill(QColor("#ffffff"))
    painter = QPainter(pixmap)

    painter.fillRect(0, 0, 1600, 92, QColor("#1f2937"))
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Helvetica", 26, QFont.Weight.Bold))
    painter.drawText(56, 60, "Northside Auto Service")
    painter.setFont(QFont("Helvetica", 20))
    painter.drawText(1290, 60, "Invoice A-20260506-118")

    painter.setPen(QColor("#111111"))
    painter.setFont(QFont("Helvetica", 40, QFont.Weight.Bold))
    painter.drawText(56, 200, "TAX INVOICE")
    painter.setFont(QFont("Helvetica", 22))
    painter.setPen(QColor("#555555"))
    painter.drawText(56, 250, "Date  06 May 2026")
    painter.drawText(56, 290, "Vehicle  Toyota Camry ACV40R")

    painter.fillRect(56, 350, 1488, 56, QColor("#f3f4f6"))
    painter.setPen(QColor("#333333"))
    painter.setFont(QFont("Helvetica", 20, QFont.Weight.Bold))
    for x, label in ((80, "Description"), (900, "Qty"), (1080, "Unit"), (1330, "Amount")):
        painter.drawText(x, 388, label)

    painter.setFont(QFont("Helvetica", 21))
    rows = [
        ("Brake pad set (front)", "2", "90.00", "180.00"),
        ("Oil filter", "1", "42.00", "42.00"),
        ("Engine oil 5W-30  5L", "1", "98.00", "98.00"),
        ("Labour  1.5h", "1", "130.00", "130.00"),
    ]
    y = 470
    for label, qty, unit, amount in rows:
        painter.setPen(QColor("#111111"))
        painter.drawText(80, y, label)
        painter.drawText(900, y, qty)
        painter.drawText(1080, y, unit)
        painter.drawText(1330, y, amount)
        painter.setPen(QColor("#e5e7eb"))
        painter.drawLine(56, y + 22, 1544, y + 22)
        y += 78

    painter.setPen(QColor("#111111"))
    painter.setFont(QFont("Helvetica", 28, QFont.Weight.Bold))
    painter.drawText(1080, y + 60, "TOTAL")
    painter.drawText(1280, y + 60, "450.00 AUD")

    painter.setPen(QColor("#888888"))
    painter.setFont(QFont("Helvetica", 18))
    painter.drawText(56, 960, "Thank you for your business.")
    painter.end()

    pixmap.save(path)


def render(app, mode, preview_path, out_path):
    palette = QPalette(app.style().standardPalette())
    palette.setColor(QPalette.ColorRole.Window, QColor(BACKGROUNDS[mode]))
    app.setPalette(palette)

    dialog = RenameDialog(
        CANDIDATES, preview_path, 10, None, os.path.expanduser("~/Documents/Screenshots")
    )
    dialog.resize(*WINDOW_SIZE)
    dialog.show()
    for _ in range(3):
        app.processEvents()

    # show() だけではプレビューの配置と拡縮が走らず、中身が空のまま写る
    dialog._layout_children()
    dialog.preview._rescale()
    app.processEvents()

    dialog.grab().save(out_path)
    dialog.close()
    print(f"{mode}: {out_path}")


def main():
    app = QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        preview_path = os.path.join(tmp, "sample-invoice.png")
        draw_sample_invoice(preview_path)
        for mode in BACKGROUNDS:
            render(app, mode, preview_path, os.path.join(DOCS_DIR, f"dialog-{mode}.png"))


if __name__ == "__main__":
    main()

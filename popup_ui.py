import os
import signal
import sys
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QPushButton, QSizePolicy,
    QHBoxLayout, QFrame, QLineEdit, QWidget, QGraphicsDropShadowEffect, QStyle
)
from PyQt6.QtCore import QEvent, QRectF, QSize, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen, QPixmap

from ocr_engine import render_pdf_preview

# ウィンドウの基準サイズ。実際の幅・高さは常にプレビュー画像の縦横比から決め直す
# （Preview.appのように、開くたびに画像に合わせて収める）。
# 画像が無い場合のみこの値を使う。画面が小さい場合は SCREEN_RATIO まで縮める
DEFAULT_WIDTH = 1160
DEFAULT_HEIGHT = 720
SCREEN_RATIO = 0.9

# ページ（プレビュー）の周囲に空ける余白。Preview.app と同じく、
# 画像はキャンバスの地の上に浮かぶ一枚の紙として見せる
CANVAS_PADDING = 28

# タイトルバーの下から降りてくるシートの幅
SHEET_WIDTH = 600
# シートに隠れてプレビューが見えなくならないための最低の高さ
MIN_CANVAS_HEIGHT = 460

# macOS のシステムカラー。ライト／ダークで入れ替えるのはこの表だけで、
# ウィンドウの組み立て方は共通にする
LIGHT_THEME = {
    "canvas": "#D5D5D8",
    "sheet": "#F4F4F4",
    "page": "#FFFFFF",
    "label": "rgba(0, 0, 0, 217)",
    "label2": "rgba(0, 0, 0, 128)",
    "label3": "rgba(0, 0, 0, 77)",
    "sep": "rgba(0, 0, 0, 28)",
    "accent": "#007AFF",
    "control": "#FFFFFF",
    "control_border": "rgba(0, 0, 0, 41)",
    "field": "#FFFFFF",
    "field_border": "rgba(0, 0, 0, 51)",
    "dim": "rgba(0, 0, 0, 46)",
    "page_shadow_alpha": 56,
}

DARK_THEME = {
    "canvas": "#171719",
    "sheet": "#3A3A3D",
    "page": "#FFFFFF",
    "label": "rgba(255, 255, 255, 219)",
    "label2": "rgba(255, 255, 255, 140)",
    "label3": "rgba(255, 255, 255, 82)",
    "sep": "rgba(255, 255, 255, 31)",
    "accent": "#0A84FF",
    "control": "#5B5B60",
    "control_border": "rgba(0, 0, 0, 102)",
    "field": "#1D1D1F",
    "field_border": "rgba(255, 255, 255, 41)",
    "dim": "rgba(0, 0, 0, 115)",
    "page_shadow_alpha": 130,
}


def current_theme():
    """システムのライト／ダーク設定に合わせた配色を返す。"""
    app = QApplication.instance()
    if app is None:
        return LIGHT_THEME

    # macOS では QPalette がシステムの外観に追従するため、地の色の明るさで判定できる
    background = app.palette().color(QPalette.ColorRole.Window)
    return DARK_THEME if background.lightnessF() < 0.5 else LIGHT_THEME


def ui_font(point_size, weight=QFont.Weight.Normal):
    """macOSのシステムUIフォント。家族名を指定するとSF Proに解決できず別書体になる。"""
    font = QFont()
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


def mono_font(point_size):
    """ファイル名用の等幅フォント。SF Monoが無い環境ではMenloに落とす。"""
    font = QFont()
    font.setFamilies(["SF Mono", "Menlo"])
    font.setPointSize(point_size)
    return font


def sanitize_filename(name):
    """入力された名前をファイル名として使える形に整える。使えなければ None。"""
    if not name:
        return None

    # "/" はパス区切りとして解釈されるため使えない
    cleaned = name.strip().replace("/", "_").replace("\0", "")
    # 先頭がドットだと不可視ファイルになってしまう
    cleaned = cleaned.lstrip(".").strip()
    return cleaned or None


def _format_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


class PreviewPane(QLabel):
    """対象ファイルの中身を一枚の紙として表示する。枠は常に画像と同じ縦横比になる。"""

    def __init__(self, filepath, theme):
        super().__init__()
        self.filepath = filepath
        self.source = self._load(filepath)

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"background-color: {theme['page']}; border: none;")

        # キャンバスの地から浮かせるための影。Preview.app のページと同じ見え方にする
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, theme["page_shadow_alpha"]))
        self.setGraphicsEffect(shadow)

        if self.source is None:
            # プレビューが出せなくてもリネーム操作は続行できるようにする
            self.setFont(ui_font(11))
            self.setStyleSheet(
                f"background-color: {theme['page']}; border: none; color: rgba(0, 0, 0, 128);"
            )
            name = os.path.basename(filepath) if filepath else ""
            self.setText("\n".join(filter(None, ["プレビューを表示できません", name])))

    def _load(self, filepath):
        if not filepath or not os.path.exists(filepath):
            return None

        if filepath.lower().endswith(".pdf"):
            return self._load_pdf(filepath)

        pixmap = QPixmap(filepath)
        return None if pixmap.isNull() else pixmap

    def _load_pdf(self, filepath):
        """QPixmapはPDFを読めないため、画像に変換してもらってから読み込む。"""
        try:
            data = render_pdf_preview(filepath)
        except Exception:
            return None

        if not data:
            return None

        pixmap = QPixmap()
        return pixmap if pixmap.loadFromData(data) else None

    def _rescale(self):
        if self.source is None:
            return

        # Retinaでぼやけないよう実ピクセルで拡縮し、描画時の倍率を戻す
        ratio = self.devicePixelRatioF()
        target = QSize(
            max(int(self.width() * ratio), 1),
            max(int(self.height() * ratio), 1),
        )
        scaled = self.source.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        self.setPixmap(scaled)

    def aspect_ratio(self):
        """元画像の縦横比。プレビューが無ければ None。"""
        if self.source is None or self.source.height() == 0:
            return None
        return self.source.width() / self.source.height()

    def source_size_text(self):
        """「2,880 × 1,800」形式の画素数。プレビューが無ければ None。"""
        if self.source is None:
            return None
        return f"{self.source.width():,} × {self.source.height():,}"

    def resizeEvent(self, event):
        self._rescale()
        super().resizeEvent(event)


class CountdownRing(QWidget):
    """残り時間を表す円形インジケータ。"""

    def __init__(self, theme):
        super().__init__()
        self.accent = QColor(theme["accent"])
        self.fraction = 1.0
        self.setFixedSize(14, 14)

    def set_fraction(self, fraction):
        self.fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.0, 1.0, 12.0, 12.0)

        track = QColor(self.accent)
        track.setAlpha(60)
        painter.setPen(QPen(track, 1.6))
        painter.drawEllipse(rect)

        pen = QPen(self.accent, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        # 12時から時計回りに減らす。Qtの角度は1/16度単位
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self.fraction))


class CandidateRow(QFrame):
    """シート内のリストに並ぶ候補1件。"""

    def __init__(self, index, cand, parent_dialog, theme):
        super().__init__()
        self.cand = cand
        self.parent_dialog = parent_dialog
        self.theme = theme

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 選択状態は current_index で管理する。行にフォーカスを持たせると
        # Tab が行間の移動に使われ、編集欄へ移せなくなる
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        self.rank = QLabel(f"第{index + 1}候補")
        self.rank.setFont(ui_font(10, QFont.Weight.DemiBold))
        layout.addWidget(self.rank)

        self.label = QLabel(cand)
        self.label.setFont(mono_font(11))
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def set_selected(self, selected):
        background = self.theme["accent"] if selected else "transparent"
        rank_color = "rgba(255, 255, 255, 184)" if selected else self.theme["label3"]
        name_color = "#FFFFFF" if selected else self.theme["label"]

        self.setStyleSheet(f"QFrame {{ background-color: {background}; border-radius: 6px; }}")
        self.rank.setStyleSheet(f"color: {rank_color}; background: transparent;")
        self.label.setStyleSheet(f"color: {name_color}; background: transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_dialog.select_candidate(self.parent_dialog.cards.index(self))


class RenameDialog(QDialog):
    def __init__(self, candidates, filepath=None, timeout_seconds=10, progress=None,
                 dest_dir=None):
        super().__init__()
        self.candidates = candidates
        self.filepath = filepath
        # timeout_seconds が None のときはタイマーを動かさない（手動モード）
        self.time_left = timeout_seconds
        # 候補を選び始めたらカウントダウンをこの秒数に戻す
        self.timeout_seconds = timeout_seconds
        self.progress = progress
        self.theme = current_theme()
        self.selected_name = None
        self.aborted = False
        self.editing = False
        self.cards = []
        self.current_index = 0

        source_dir = os.path.dirname(filepath) if filepath else ""
        self.dest_dir = dest_dir or source_dir
        # 監視モードは別フォルダへ移すが、手動モードは同じ場所で名前だけ変える。
        # 見出しとボタンの言葉をそれに合わせる
        self.moving = os.path.normpath(self.dest_dir) != os.path.normpath(source_dir or ".")

        self.init_ui()

    # --- 組み立て -------------------------------------------------

    def init_ui(self):
        # Preview.app と同じく、タイトルバーには開いているファイルの名前を出す
        self.setWindowTitle(os.path.basename(self.filepath) if self.filepath else "Smart Renamer")
        self.setStyleSheet(f"QDialog {{ background-color: {self.theme['canvas']}; }}")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setSizeGripEnabled(True)
        # キー操作はダイアログ側で受ける
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # --- キャンバス（地）とページ（プレビュー） ---
        # レイアウトに載せると固定サイズがウィンドウの下限になり、縮められなくなる
        self.preview = PreviewPane(self.filepath, self.theme)
        self.preview.setParent(self)

        self.setMinimumWidth(SHEET_WIDTH + 80)
        self.resize(self._initial_size(self.preview.aspect_ratio()))

        # --- 背後を暗転させ、注意をシートへ集める ---
        self.dim = QWidget(self)
        self.dim.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.dim.setStyleSheet(f"background-color: {self.theme['dim']};")

        self._build_sheet()
        # シートで埋まってプレビューが見えなくなる大きさには縮められないようにする
        self.setMinimumHeight(self.sheet.sizeHint().height() + 160)

        # 最初はカーソルを立てず、候補を選べる状態にする。
        # 編集したくなったら Tab か名前欄のクリックでカーソルが入る。
        self.update_card_styles()
        self.setFocus()
        self._layout_children()

        # タイマー
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        if self._has_timeout():
            self.timer.start(1000)

    def _initial_size(self, aspect_ratio=None):
        """画像の縦横比からウィンドウの大きさを決める。

        ページの周囲の余白が上下左右で等しくなるよう、余白の分を足した大きさにする。
        """
        width = DEFAULT_WIDTH
        height = int(width / aspect_ratio) if aspect_ratio else DEFAULT_HEIGHT
        height = max(height, MIN_CANVAS_HEIGHT)

        width += CANVAS_PADDING * 2
        height += CANVAS_PADDING * 2

        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            max_width = int(available.width() * SCREEN_RATIO)
            max_height = int(available.height() * SCREEN_RATIO)
            # 画面に収めるときも比率を保つ
            scale = min(max_width / width, max_height / height, 1.0)
            width = int(width * scale)
            height = int(height * scale)

        return QSize(max(width, 1), max(height, 1))

    def _build_sheet(self):
        """タイトルバーの下から降りてくるシート。レイアウトには載せず、自前で位置を決める。"""
        self.sheet = QFrame(self)
        self.sheet.setObjectName("sheet")
        self.sheet.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.sheet.setStyleSheet(f"""
            QFrame#sheet {{
                background-color: {self.theme['sheet']};
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self.sheet)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        layout.addLayout(self._build_head())
        layout.addLayout(self._build_name_row())
        layout.addWidget(self._build_listbox())
        layout.addLayout(self._build_location_row())
        layout.addLayout(self._build_foot())

    def _build_head(self):
        head = QHBoxLayout()
        head.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(3)

        title = QLabel("この名前で保存" if self.moving else "この名前に変更")
        title.setFont(ui_font(13, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {self.theme['label']}; background: transparent;")
        titles.addWidget(title)

        subtitle = QLabel(self._file_meta_text())
        subtitle.setFont(ui_font(11))
        subtitle.setStyleSheet(f"color: {self.theme['label2']}; background: transparent;")
        titles.addWidget(subtitle)

        head.addLayout(titles)
        head.addStretch()

        if self.progress:
            # 複数ファイルを順に処理しているときの「3 / 50」表示
            done, total = self.progress
            pill = QLabel(f"{done} / {total}")
            pill.setFont(ui_font(11))
            pill.setStyleSheet(f"""
                color: {self.theme['label2']};
                background-color: {self.theme['sep']};
                border-radius: 10px;
                padding: 3px 9px;
            """)
            head.addWidget(pill, alignment=Qt.AlignmentFlag.AlignTop)

        return head

    def _file_meta_text(self):
        """「PNG · 2,880 × 1,800 · 2.4 MB」形式の見出し補足。"""
        if not self.filepath:
            return ""

        extension = os.path.splitext(self.filepath)[1].lstrip(".").upper()
        parts = [extension] if extension else []

        size_text = self.preview.source_size_text()
        if size_text:
            parts.append(size_text)

        try:
            parts.append(_format_size(os.path.getsize(self.filepath)))
        except OSError:
            pass

        return " · ".join(parts)

    def _build_name_row(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._field_label("名前"))

        # 候補を選ぶとここに入る。Tab またはクリックでカーソルが入り、書き換えられる
        self.name_edit = QLineEdit()
        self.name_edit.setFont(mono_font(12))
        self.name_edit.setFixedHeight(28)
        # Tabキーは自前で処理する。勝手にフォーカスが移らないようクリックのみ許可する
        self.name_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.theme['field']};
                border: 1px solid {self.theme['field_border']};
                border-radius: 6px;
                padding: 0 8px;
                color: {self.theme['label']};
            }}
            QLineEdit:focus {{ border: 2px solid {self.theme['accent']}; }}
        """)
        self.name_edit.returnPressed.connect(self.confirm_edited_name)
        # 名前欄にカーソルが入ったらタイマーを止めるため、フォーカスを監視する
        self.name_edit.installEventFilter(self)
        if self.candidates:
            self.name_edit.setText(self.candidates[0])
        row.addWidget(self.name_edit)

        extension = os.path.splitext(self.filepath)[1] if self.filepath else ""
        if extension:
            ext_label = QLabel(extension)
            ext_label.setFont(mono_font(12))
            ext_label.setStyleSheet(f"color: {self.theme['label2']}; background: transparent;")
            row.addWidget(ext_label)

        return row

    def _field_label(self, text):
        label = QLabel(text)
        label.setFont(ui_font(13))
        label.setFixedWidth(40)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet(f"color: {self.theme['label']}; background: transparent;")
        return label

    def _build_listbox(self):
        box = QFrame()
        box.setObjectName("listbox")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        box.setStyleSheet(f"""
            QFrame#listbox {{
                background-color: {self.theme['field']};
                border: 1px solid {self.theme['field_border']};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for index, cand in enumerate(self.candidates):
            row = CandidateRow(index, cand, self, self.theme)
            layout.addWidget(row)
            self.cards.append(row)

        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(50, 0, 0, 0)
        wrapper_layout.addWidget(box)
        return wrapper

    def _build_location_row(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._field_label("場所"))

        popup = QFrame()
        popup.setObjectName("popup")
        popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        popup.setFixedHeight(28)
        # 余った幅はパス表示に回す。伸ばすとフォルダ名が中央に浮いてしまう
        popup.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        popup.setStyleSheet(f"""
            QFrame#popup {{
                background-color: {self.theme['control']};
                border: 1px solid {self.theme['control_border']};
                border-radius: 6px;
            }}
        """)
        popup_layout = QHBoxLayout(popup)
        popup_layout.setContentsMargins(8, 0, 10, 0)
        popup_layout.setSpacing(7)

        icon = QLabel()
        icon.setPixmap(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon).pixmap(15, 15)
        )
        icon.setStyleSheet("background: transparent;")
        popup_layout.addWidget(icon)

        name = QLabel(os.path.basename(self.dest_dir.rstrip("/")) or "/")
        name.setFont(ui_font(13))
        name.setStyleSheet(f"color: {self.theme['label']}; background: transparent;")
        popup_layout.addWidget(name)

        row.addWidget(popup)

        # 長いパスでもシートを押し広げないよう、余った幅に合わせて省略する
        self.path_label = QLabel()
        self.path_label.setFont(ui_font(11))
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.path_label.setStyleSheet(f"color: {self.theme['label3']}; background: transparent;")
        self.path_label.setToolTip(self.dest_dir)
        row.addWidget(self.path_label)

        return row

    def _update_path_label(self):
        metrics = QFontMetrics(self.path_label.font())
        elided = metrics.elidedText(
            self._display_path(), Qt.TextElideMode.ElideMiddle, self.path_label.width()
        )
        if elided != self.path_label.text():
            self.path_label.setText(elided)

    def _display_path(self):
        home = os.path.expanduser("~")
        if self.dest_dir.startswith(home):
            return "~" + self.dest_dir[len(home):]
        return self.dest_dir

    def _build_foot(self):
        foot = QHBoxLayout()
        foot.setSpacing(10)

        self.ring = CountdownRing(self.theme)
        self.ring.setVisible(self._has_timeout())
        foot.addWidget(self.ring)

        self.timer_label = QLabel(self._status_text())
        self.timer_label.setFont(ui_font(11))
        self.timer_label.setStyleSheet(f"color: {self.theme['label2']}; background: transparent;")
        foot.addWidget(self.timer_label)
        foot.addStretch()

        if self.progress:
            abort_btn = self._button("すべて中止", kind="plain")
            abort_btn.clicked.connect(self.on_abort)
            foot.addWidget(abort_btn)

        cancel_btn = self._button("スキップ" if self.progress else "キャンセル")
        cancel_btn.clicked.connect(lambda: self.on_select(None))
        foot.addWidget(cancel_btn)

        confirm_btn = self._button("保存" if self.moving else "名前を変更", kind="default")
        confirm_btn.clicked.connect(self.confirm_edited_name)
        foot.addWidget(confirm_btn)

        return foot

    def _button(self, text, kind="normal"):
        button = QPushButton(text)
        button.setFont(ui_font(13))
        button.setFixedHeight(28)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        # Return はダイアログ側で処理するため、ボタンに横取りさせない
        button.setAutoDefault(False)
        button.setDefault(False)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        if kind == "default":
            style = f"background-color: {self.theme['accent']}; border: none; color: #FFFFFF;"
        elif kind == "plain":
            style = f"background: transparent; border: none; color: {self.theme['label2']};"
        else:
            style = (
                f"background-color: {self.theme['control']};"
                f"border: 1px solid {self.theme['control_border']};"
                f"color: {self.theme['label']};"
            )

        button.setStyleSheet(f"QPushButton {{ {style} border-radius: 6px; padding: 0 14px; }}")
        return button

    # --- 配置 -----------------------------------------------------

    def _layout_children(self):
        """暗転とシートをウィンドウに合わせて置き直す。"""
        if not hasattr(self, "sheet"):
            return

        self._layout_page()

        self.dim.setGeometry(0, 0, self.width(), self.height())
        self.dim.raise_()

        width = min(SHEET_WIDTH, max(self.width() - 80, 320))
        height = self.sheet.sizeHint().height()
        self.sheet.setGeometry((self.width() - width) // 2, 0, width, height)
        self.sheet.raise_()
        self._update_path_label()

    def _layout_page(self):
        """ページをキャンバスの縦横比に合わせて収める。余りはキャンバスの地になる。"""
        available_width = max(self.width() - CANVAS_PADDING * 2, 1)
        available_height = max(self.height() - CANVAS_PADDING * 2, 1)

        ratio = self.preview.aspect_ratio()
        if ratio is None:
            width, height = available_width, available_height
        else:
            width = min(available_width, available_height * ratio)
            height = width / ratio

        width, height = max(int(width), 1), max(int(height), 1)
        self.preview.setGeometry(
            (self.width() - width) // 2, (self.height() - height) // 2, width, height
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_children()

    # --- 状態 -----------------------------------------------------

    def _has_timeout(self):
        return bool(self.time_left)

    def _status_text(self):
        if self.editing:
            return "自動保存を停止中"
        if self._has_timeout():
            return f"{self.time_left} 秒後に第1候補で保存"
        return "↑↓ 選択　tab 書き換え　return 確定"

    def update_card_styles(self):
        """選択状態に合わせて候補行のスタイルを一括変更"""
        for index, card in enumerate(self.cards):
            card.set_selected(index == self.current_index)

    def select_candidate(self, index):
        """候補を選び、名前欄の中身を差し替える。カーソルは立てない。"""
        if not (0 <= index < len(self.candidates)):
            return
        self.current_index = index
        self.update_card_styles()
        self.name_edit.setText(self.candidates[index])
        # 候補を見比べている最中に自動保存されないよう、カウントダウンを戻す
        self.extend_timeout()

    def extend_timeout(self):
        """操作があったらカウントダウンを最初からやり直す。"""
        if self.editing or not self._has_timeout():
            return
        self.time_left = self.timeout_seconds
        self._refresh_countdown()

    def _refresh_countdown(self):
        self.timer_label.setText(self._status_text())
        if self.timeout_seconds:
            self.ring.set_fraction(self.time_left / self.timeout_seconds)

    def enter_edit_mode(self):
        """名前欄にカーソルを入れる。自分で書く以上、自動保存は止める。"""
        if self.editing:
            return
        self.editing = True
        self.timer.stop()
        self.ring.setVisible(False)
        self.timer_label.setText(self._status_text())
        self.name_edit.setFocus()
        self.name_edit.setCursorPosition(len(self.name_edit.text()))

    def eventFilter(self, obj, event):
        # 名前欄をクリックされた場合もタイマーを止める
        if obj is self.name_edit and event.type() == QEvent.Type.FocusIn:
            self.enter_edit_mode()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        key = event.key()

        # 編集中は矢印キーを文字カーソルの移動として扱う（候補は切り替えない）
        if self.editing and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            super().keyPressEvent(event)
            return

        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            delta = 1 if key == Qt.Key.Key_Down else -1
            self.select_candidate(self.current_index + delta)

        elif key == Qt.Key.Key_Tab:
            self.enter_edit_mode()

        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.confirm_edited_name()

        elif key == Qt.Key.Key_Escape:
            self.on_select(None)
        else:
            super().keyPressEvent(event)

    def confirm_edited_name(self):
        """名前欄の内容で確定する。"""
        self.on_select(self.name_edit.text())

    def update_timer(self):
        self.time_left -= 1
        if self.time_left > 0:
            self._refresh_countdown()
        else:
            # 放置された場合は従来通り、現在選んでいる候補で自動保存する
            self.on_select(self.name_edit.text() or None)

    def on_select(self, name):
        self.timer.stop()
        # 候補クリック・キー確定・タイムアウトのどの経路でも同じ整形を通す
        self.selected_name = sanitize_filename(name)
        self.accept()

    def on_abort(self):
        """複数処理中に残り全てを中止する。"""
        self.timer.stop()
        self.aborted = True
        self.selected_name = None
        self.reject()


# QApplicationをローカル変数だけで持つと関数を抜けた時点で破棄される。
# NSApplication側はGUIアプリとして登録されたまま残るため、イベントを捌く主体が
# 居ない状態になり、レインボーカーソルの原因になる。プロセス全体で保持する。
_app = None


def _ensure_app(foreground=False):
    """QApplicationを取得（無ければ生成）し、常駐ツールとしての体裁を整える。

    foreground=True は手動モード用。利用者が自分で起動しているため、
    通常のアプリとして前面に出るのが正しい。
    """
    global _app
    app = QApplication.instance() or QApplication(sys.argv)
    _app = app

    # 監視モードでは、QApplicationを生成するとプロセスが通常のGUIアプリ扱いになり、
    # Dockアイコンとメニューバーを占有したまま常駐してしまう。メニューバー常駐アプリと
    # 同じ Accessory に変更し、Dockに居座らせない。
    policy = (
        NSApplicationActivationPolicyRegular
        if foreground
        else NSApplicationActivationPolicyAccessory
    )
    NSApplication.sharedApplication().setActivationPolicy_(policy)

    # これが無いと、リネームのダイアログを閉じた時点で「最後のウィンドウが閉じた」と
    # 判断され、常駐プロセスごと終了してしまう。
    app.setQuitOnLastWindowClosed(False)
    return app


def run_event_loop(on_tick, interval_ms=500):
    """Cocoaのイベントを処理し続けるメインループ。

    自前の while ループで待機すると、GUIアプリとして登録されているのにイベント
    キューを処理しないプロセスになり、macOSから応答なしと判断されてレインボー
    カーソルの原因になる。待機中もイベントループを回し続ける必要がある。
    """
    app = _ensure_app()

    # Qtのイベントループ実行中はPythonのシグナルハンドラが動かないが、
    # 定期的に発火するタイマーでPython側へ制御が戻るため Ctrl+C が効く
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    timer = QTimer()
    timer.timeout.connect(on_tick)
    timer.start(interval_ms)

    app.exec()


def stop_event_loop():
    app = QApplication.instance()
    if app:
        app.quit()


def show_rename_dialog(candidates, filepath=None, timeout_seconds=10, progress=None,
                       foreground=False, dest_dir=None):
    """リネーム候補を提示する。戻り値は (確定した名前, 全体中止されたか)。

    timeout_seconds に None を渡すとタイムアウトしない（手動モード）。
    dest_dir は確定後の保存先。省略すると元のフォルダを表示する。
    """
    app = _ensure_app(foreground=foreground)
    ns_app = NSApplication.sharedApplication()

    dialog = RenameDialog(candidates, filepath, timeout_seconds, progress, dest_dir)
    # Accessoryではウィンドウが自動で前面に来ないため、明示的にフォーカスを取る
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.exec()

    # 閉じた後は前面から退き、フォーカスを元のアプリへ返す
    ns_app.deactivate()

    return dialog.selected_name, dialog.aborted

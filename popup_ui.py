import os
import signal
import sys
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel,
    QHBoxLayout, QFrame, QLineEdit
)
from PyQt6.QtCore import QSettings, QSize, QTimer, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPixmap

# ダイアログの初期サイズ。画面が小さい場合は SCREEN_RATIO まで縮める
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 760
SCREEN_RATIO = 0.9

# ウィンドウサイズの保存先。利用者が編集する設定ではないため config.yaml には置かない
SETTINGS_ORG = "screenshot_renamer"
SETTINGS_APP = "RenameDialog"


def sanitize_filename(name):
    """入力された名前をファイル名として使える形に整える。使えなければ None。"""
    if not name:
        return None

    # "/" はパス区切りとして解釈されるため使えない
    cleaned = name.strip().replace("/", "_").replace("\0", "")
    # 先頭がドットだと不可視ファイルになってしまう
    cleaned = cleaned.lstrip(".").strip()
    return cleaned or None


class PreviewPane(QLabel):
    """対象ファイルの中身を表示する。枠のサイズは変えず、中身をアスペクト比維持で収める。"""

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        self.source = self._load(filepath)

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(160)
        self.setStyleSheet(
            "background-color: #000000; border: 1px solid #3A3A3C; border-radius: 6px;"
        )

        if self.source is None:
            # プレビューが出せなくてもリネーム操作は続行できるようにする
            self.setFont(QFont("SF Pro Text", 11))
            name = os.path.basename(filepath) if filepath else ""
            self.setText("\n".join(filter(None, ["プレビューを表示できません", name])))

    def _load(self, filepath):
        if not filepath or not os.path.exists(filepath):
            return None
        pixmap = QPixmap(filepath)
        return None if pixmap.isNull() else pixmap

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

    def resizeEvent(self, event):
        self._rescale()
        super().resizeEvent(event)


class CandidateCard(QFrame):
    """テキストが100%垂直中央に揃うカード型選択肢"""
    def __init__(self, cand, parent_dialog):
        super().__init__()
        self.cand = cand
        self.parent_dialog = parent_dialog

        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        self.label = QLabel()
        self.label.setFont(QFont("SF Mono", 10))
        # 確実に左寄せ＆垂直中央揃え
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)

        self._update_elided_text()

    def _update_elided_text(self):
        """幅に合わせて省略位置を計算し直す。ウィンドウを広げれば全体が見える。"""
        metrics = QFontMetrics(self.label.font())
        available = max(self.width() - 40, 0)
        text = f" {metrics.elidedText(self.cand, Qt.TextElideMode.ElideLeft, available)}"
        # 同じ文字列を再設定するとレイアウトが再帰的に走るため、変化時のみ更新する
        if text != self.label.text():
            self.label.setText(text)

    def resizeEvent(self, event):
        self._update_elided_text()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_dialog.on_select(self.cand)


class RenameDialog(QDialog):
    def __init__(self, candidates, filepath=None, timeout_seconds=10, progress=None):
        super().__init__()
        self.candidates = candidates
        self.filepath = filepath
        # timeout_seconds が None のときはタイマーを動かさない（手動モード）
        self.time_left = timeout_seconds
        self.progress = progress
        self.selected_name = None
        self.aborted = False
        self.cards = []
        self.current_index = 0
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        self.init_ui()

    def _initial_size(self):
        """前回のサイズがあればそれを使う。無ければ既定値。画面をはみ出さないよう上限を設ける。"""
        width = self.settings.value("width", DEFAULT_WIDTH, type=int)
        height = self.settings.value("height", DEFAULT_HEIGHT, type=int)

        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            width = min(width, int(available.width() * SCREEN_RATIO))
            height = min(height, int(available.height() * SCREEN_RATIO))

        return QSize(max(width, 1), max(height, 1))

    def done(self, result):
        """閉じ方（選択・キャンセル・タイムアウト）に関わらず最後のサイズを覚える"""
        self.settings.setValue("width", self.width())
        self.settings.setValue("height", self.height())
        super().done(result)

    def init_ui(self):
        self.setWindowTitle("Screenshot Renamer")
        self.setStyleSheet("background-color: #1E1E1E; color: #FFFFFF;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setSizeGripEnabled(True)
        self.resize(self._initial_size())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        # --- ヘッダー ---
        header_layout = QHBoxLayout()

        title_label = QLabel("ファイル名を選択")
        title_label.setFont(QFont("SF Pro Text", 13, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        if self.progress:
            # 複数ファイルを順に処理しているときの「3 / 50」表示
            done, total = self.progress
            progress_label = QLabel(f"{done} / {total}")
            progress_label.setFont(QFont("SF Pro Text", 11))
            progress_label.setStyleSheet("color: #8E8E93;")
            header_layout.addWidget(progress_label)

        layout.addLayout(header_layout)

        self.timer_label = QLabel()
        self.timer_label.setFont(QFont("SF Pro Text", 10))
        self.timer_label.setStyleSheet("color: #0A84FF;")
        if self._has_timeout():
            self.timer_label.setText(
                f"選択されない場合、{self.time_left}秒後に第1候補で自動保存します"
            )
        else:
            self.timer_label.setText("名前を選ぶか、直接書き換えて Enter で確定します")
        layout.addWidget(self.timer_label)

        # --- プレビュー ---
        # 余った領域は全てプレビューに割り当てる。ウィンドウを広げた分だけ大きく見える
        self.preview = PreviewPane(self.filepath)
        layout.addWidget(self.preview, stretch=1)

        # --- 候補リスト ---
        for cand in self.candidates:
            card = CandidateCard(cand, self)
            layout.addWidget(card)
            self.cards.append(card)

        # --- 編集欄 ---
        # 候補を選ぶとここに入る。そのまま書き換えて確定できる
        self.name_edit = QLineEdit()
        self.name_edit.setFont(QFont("SF Mono", 11))
        self.name_edit.setFixedHeight(38)
        self.name_edit.setStyleSheet("""
            QLineEdit {
                background-color: #2C2C2E;
                border: 1px solid #3A3A3C;
                border-radius: 6px;
                padding: 0 10px;
                color: #FFFFFF;
            }
            QLineEdit:focus { border: 2px solid #0A84FF; }
        """)
        self.name_edit.returnPressed.connect(self.confirm_edited_name)
        if self.candidates:
            self.name_edit.setText(self.candidates[0])
        layout.addWidget(self.name_edit)

        # --- フッター ---
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        if self.progress:
            abort_btn = QLabel("すべて中止")
            abort_btn.setFont(QFont("SF Pro Text", 10))
            abort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            abort_btn.setStyleSheet("color: #FF9F0A; margin-right: 16px;")
            abort_btn.mousePressEvent = lambda e: self.on_abort()
            footer_layout.addWidget(abort_btn)

        cancel_btn = QLabel("スキップ（変更しない）" if self.progress else "キャンセル（保存しない）")
        cancel_btn.setFont(QFont("SF Pro Text", 10))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("color: #FF453A;")
        cancel_btn.mousePressEvent = lambda e: self.on_select(None)
        footer_layout.addWidget(cancel_btn)

        layout.addLayout(footer_layout)

        # 初期表示・フォーカス設定
        # 矢印キーは dialog 側で拾うため、フォーカスは常に編集欄に置く
        self.update_card_styles()
        self.name_edit.setFocus()

        # タイマー
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        if self._has_timeout():
            self.timer.start(1000)

    def _has_timeout(self):
        return bool(self.time_left)

    def update_card_styles(self):
        """選択状態に合わせてカードとラベルのスタイルを一括変更"""
        for i, card in enumerate(self.cards):
            is_active = (i == self.current_index)
            
            border = "2px solid #0A84FF" if is_active else "1px solid #3A3A3C"
            text_color = "#64D2FF" if is_active else "#FFFFFF"

            card.setStyleSheet(f"""
                QFrame {{
                    background-color: #2C2C2E;
                    border: {border};
                    border-radius: 6px;
                }}
                QFrame:hover {{
                    background-color: #3A3A3C;
                }}
            """)
            card.label.setStyleSheet(f"color: {text_color}; border: none; background: transparent;")

    def select_candidate(self, index):
        """候補を選び、編集欄の中身を差し替える。"""
        if not (0 <= index < len(self.candidates)):
            return
        self.current_index = index
        self.update_card_styles()
        self.name_edit.setText(self.candidates[index])
        self.name_edit.setFocus()

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            delta = 1 if key == Qt.Key.Key_Down else -1
            self.select_candidate(self.current_index + delta)

        elif key == Qt.Key.Key_Escape:
            self.on_select(None)
        else:
            super().keyPressEvent(event)

    def confirm_edited_name(self):
        """編集欄の内容で確定する。"""
        self.on_select(self.name_edit.text())

    def update_timer(self):
        self.time_left -= 1
        if self.time_left > 0:
            self.timer_label.setText(f"選択されない場合、{self.time_left}秒後に第1候補で自動保存します")
        else:
            self.on_select(self.candidates[0] if self.candidates else None)

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
                       foreground=False):
    """リネーム候補を提示する。戻り値は (確定した名前, 全体中止されたか)。

    timeout_seconds に None を渡すとタイムアウトしない（手動モード）。
    """
    app = _ensure_app(foreground=foreground)
    ns_app = NSApplication.sharedApplication()

    dialog = RenameDialog(candidates, filepath, timeout_seconds, progress)
    # Accessoryではウィンドウが自動で前面に来ないため、明示的にフォーカスを取る
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.exec()

    # 閉じた後は前面から退き、フォーカスを元のアプリへ返す
    ns_app.deactivate()

    return dialog.selected_name, dialog.aborted

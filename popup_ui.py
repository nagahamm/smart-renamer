import sys
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, 
    QHBoxLayout, QFrame
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QFontMetrics

class CandidateCard(QFrame):
    """テキストが100%垂直中央に揃うカード型選択肢"""
    def __init__(self, text, cand, parent_dialog):
        super().__init__()
        self.cand = cand
        self.parent_dialog = parent_dialog
        
        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        self.label = QLabel(f" {text}")
        self.label.setFont(QFont("SF Mono", 10))
        # 確実に左寄せ＆垂直中央揃え
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_dialog.on_select(self.cand)


class RenameDialog(QDialog):
    def __init__(self, candidates, timeout_seconds=10):
        super().__init__()
        self.candidates = candidates
        self.time_left = timeout_seconds
        self.selected_name = None
        self.cards = []
        self.current_index = 0

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Screenshot Renamer")
        self.setFixedSize(620, 310)
        self.setStyleSheet("background-color: #1E1E1E; color: #FFFFFF;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        # --- ヘッダー ---
        title_label = QLabel("ファイル名を選択")
        title_label.setFont(QFont("SF Pro Text", 13, QFont.Weight.Bold))
        layout.addWidget(title_label)

        self.timer_label = QLabel(f"選択されない場合、{self.time_left}秒後に第1候補で自動保存します")
        self.timer_label.setFont(QFont("SF Pro Text", 10))
        self.timer_label.setStyleSheet("color: #0A84FF;")
        layout.addWidget(self.timer_label)

        # --- 候補リスト ---
        btn_font = QFont("SF Mono", 10)
        font_metrics = QFontMetrics(btn_font)

        for cand in self.candidates:
            display_text = font_metrics.elidedText(cand, Qt.TextElideMode.ElideLeft, 540)
            card = CandidateCard(display_text, cand, self)
            layout.addWidget(card)
            self.cards.append(card)

        layout.addStretch()

        # --- フッター ---
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        cancel_btn = QLabel("キャンセル（保存しない）")
        cancel_btn.setFont(QFont("SF Pro Text", 10))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("color: #FF453A;")
        cancel_btn.mousePressEvent = lambda e: self.on_select(None)
        footer_layout.addWidget(cancel_btn)

        layout.addLayout(footer_layout)

        # 初期表示・フォーカス設定
        self.update_card_styles()
        if self.cards:
            self.cards[0].setFocus()

        # タイマー
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)

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

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            delta = 1 if key == Qt.Key.Key_Down else -1
            new_idx = self.current_index + delta
            if 0 <= new_idx < len(self.cards):
                self.current_index = new_idx
                self.update_card_styles()
                self.cards[self.current_index].setFocus()

        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if 0 <= self.current_index < len(self.candidates):
                self.on_select(self.candidates[self.current_index])

        elif key == Qt.Key.Key_Escape:
            self.on_select(None)
        else:
            super().keyPressEvent(event)

    def update_timer(self):
        self.time_left -= 1
        if self.time_left > 0:
            self.timer_label.setText(f"選択されない場合、{self.time_left}秒後に第1候補で自動保存します")
        else:
            self.on_select(self.candidates[0] if self.candidates else None)

    def on_select(self, name):
        self.timer.stop()
        self.selected_name = name
        self.accept()


def show_rename_dialog(candidates, timeout_seconds=10):
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = RenameDialog(candidates, timeout_seconds)
    dialog.exec()
    return dialog.selected_name

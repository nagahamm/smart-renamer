import tkinter as tk
from tkinter import font

def show_rename_dialog(candidates, timeout_seconds=10):
    selected_name = [None]
    time_left = [timeout_seconds]

    # main.py のルートからToplevelを作成（新しい独立ウィンドウ）
    dialog = tk.Toplevel()
    dialog.title("Screenshot Renamer")
    dialog.geometry("740x260")
    dialog.configure(bg="#1E1E1E")
    
    # 最前面化
    dialog.lift()
    dialog.attributes('-topmost', True)
    dialog.eval('tk::PlaceWindow . center')

    # フォント設定
    title_font = font.Font(family="SF Pro Text", size=13, weight="bold")
    sub_font = font.Font(family="SF Pro Text", size=10)
    cand_font = font.Font(family="SF Mono", size=11)

    # --- ヘッダーエリア ---
    header_frame = tk.Frame(dialog, bg="#1E1E1E")
    header_frame.pack(fill="x", padx=20, pady=(10, 2))

    title_label = tk.Label(
        header_frame, 
        text="✨ AI生成されたファイル名を選択", 
        font=title_font, 
        fg="#FFFFFF", 
        bg="#1E1E1E",
        anchor="w"
    )
    title_label.pack(fill="x")

    timer_label = tk.Label(
        header_frame, 
        text=f"選択されない場合、{time_left[0]}秒後に第1候補で自動保存します", 
        font=sub_font, 
        fg="#0A84FF",
        bg="#1E1E1E",
        anchor="w"
    )
    timer_label.pack(fill="x", pady=(2, 0))

    def on_select(name):
        selected_name[0] = name
        dialog.destroy()

    # --- 候補リスト ---
    btn_frame = tk.Frame(dialog, bg="#1E1E1E")
    btn_frame.pack(fill="both", expand=True, padx=20, pady=(6, 0))

    for i, cand in enumerate(candidates):
        is_first = (i == 0)
        border_color = "#0A84FF" if is_first else "#3A3A3C"
        bg_color = "#2C2C2E"
        hover_color = "#3A3A3C"
        text_color = "#64D2FF" if is_first else "#FFFFFF"

        card = tk.Frame(btn_frame, bg=border_color, bd=1, relief="flat")
        card.pack(fill="x", pady=3)

        lbl_btn = tk.Label(
            card,
            text=f"  {cand}",
            font=cand_font,
            fg=text_color,
            bg=bg_color,
            anchor="w",
            padx=12,
            pady=8,
            cursor="hand2"
        )
        lbl_btn.pack(fill="both", expand=True)

        def on_enter(e, l=lbl_btn):
            l.configure(bg=hover_color)
        def on_leave(e, l=lbl_btn, bg=bg_color):
            l.configure(bg=bg)
        def on_click(e, c=cand):
            on_select(c)

        lbl_btn.bind("<Enter>", on_enter)
        lbl_btn.bind("<Leave>", on_leave)
        lbl_btn.bind("<Button-1>", on_click)

    # --- カウントダウンタイマー ---
    def update_timer():
        if not dialog.winfo_exists():
            return
        if time_left[0] > 0:
            timer_label.config(text=f"選択されない場合、{time_left[0]}秒後に第1候補で自動保存します")
            time_left[0] -= 1
            dialog.after(1000, update_timer)
        else:
            if selected_name[0] is None and candidates:
                selected_name[0] = candidates[0]
            dialog.destroy()

    update_timer()

    # --- キャンセル ---
    footer_frame = tk.Frame(dialog, bg="#1E1E1E")
    footer_frame.pack(fill="x", padx=20, pady=(4, 8))

    cancel_btn = tk.Label(
        footer_frame,
        text="キャンセル（保存しない）",
        font=sub_font,
        fg="#FF453A",
        bg="#1E1E1E",
        cursor="hand2"
    )
    cancel_btn.pack(side="right")
    cancel_btn.bind("<Button-1>", lambda e: dialog.destroy())

    # ダイアログが閉じるまで待機（モーダル表示）
    dialog.grab_set()
    dialog.wait_window()

    return selected_name[0]

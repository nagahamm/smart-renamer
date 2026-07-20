import tkinter as tk
from tkinter import ttk

def show_rename_dialog(candidates, timeout_seconds=5):
    root = tk.Tk()
    root.title("ファイル名を確認")
    root.attributes('-topmost', True)
    root.eval('tk::PlaceWindow . center')

    selected_name = tk.StringVar(value=candidates[0] if candidates else "")
    
    combo = ttk.Combobox(root, textvariable=selected_name, values=candidates, width=60)
    combo.pack(padx=20, pady=15)
    combo.focus_set()

    result = None

    def on_submit(event=None):
        nonlocal result
        result = selected_name.get()
        root.destroy()

    def on_cancel(event=None):
        root.destroy()

    def countdown(remaining):
        if remaining <= 0:
            on_submit()
        else:
            root.title(f"ファイル名を確認 (自動保存まで {remaining}秒)")
            root.after(1000, countdown, remaining - 1)

    root.bind('<Return>', on_submit)
    root.bind('<Escape>', on_cancel)

    countdown(timeout_seconds)
    root.mainloop()

    return result

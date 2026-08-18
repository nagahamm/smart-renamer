import os
# Tkinterの非推奨警告（DeprecationWarning）を非表示にする設定
os.environ["TK_SILENCE_DEPRECATION"] = "1"

import time
import shutil
import yaml
import queue
import re
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

from ocr_engine import extract_text
from llm_client import get_filename_candidates
from popup_ui import show_rename_dialog

file_queue = queue.Queue()
processed_files = set()  # 重複処理防止用のセット

# launchdのWatchPathsで起動された直後に拾う、既存ファイルの新しさの上限（秒）
STARTUP_SCAN_MAX_AGE_SECONDS = 60


class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, watch_dir):
        self.watch_dir = watch_dir

    def enqueue(self, path):
        filename = os.path.basename(path)
        # 隠しファイル除外 ＆ PNG画像のみ対象
        if not path.lower().endswith('.png') or filename.startswith('.'):
            return
        
        # 即座にキューへ入れる（イベントスレッドをブロックしない）
        if os.path.exists(path) and path not in processed_files:
            print(f"\n📸 新規スクリーンショットを検知: {path}")
            processed_files.add(path)
            file_queue.put(path)

    # macOSのスクショ特有の挙動（一時ファイルからのリネーム発生）を検知
    def on_moved(self, event):
        if not event.is_directory:
            self.enqueue(event.dest_path)

    # 他アプリからの直接保存などを検知
    def on_created(self, event):
        if not event.is_directory:
            self.enqueue(event.src_path)


def enqueue_recent_files(handler, watch_dir):
    """launchdのWatchPathsで起動された場合、起動のきっかけとなったスクショは
    watchdogのイベントに乗らないため、起動直後に直接キューへ入れる。"""
    if not os.path.isdir(watch_dir):
        return

    now = time.time()
    for filename in os.listdir(watch_dir):
        path = os.path.join(watch_dir, filename)
        if not os.path.isfile(path):
            continue
        if now - os.path.getmtime(path) <= STARTUP_SCAN_MAX_AGE_SECONDS:
            handler.enqueue(path)


def get_next_sequence_name(save_dir):
    # """ LLMから候補が得られなかった場合のフォールバック（日付+連番）"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    existing_files = os.listdir(save_dir)
    max_seq = 0

    # 例: "2026-07-21__0001_Capture" から末尾4桁の連番を抽出
    pattern = re.compile(rf"{today_str}__(\d{{4}})_Capture")
    
    for filename in existing_files:
        match = pattern.search(filename)
        if match:
            seq = int(match.group(1))
            if seq > max_seq:
                max_seq = seq
                
    next_seq = max_seq + 1
    return f"{today_str}__{next_seq:04d}_Capture"


def process_screenshot(filepath, config):
    # OSによるファイル書き込み完了を待つため1秒待機
    time.sleep(1.0)
    if not os.path.exists(filepath):
        print(f"⚠️ ファイルが存在しないためスキップします: {filepath}")
        return

    save_dir = os.path.expanduser(config['directories']['save_dir'])
    timeout = config['ui']['timeout_seconds']
    prompt_template = config['llm_rules']['prompt_template']
    
    os.makedirs(save_dir, exist_ok=True)

    print("🔍 OCR処理を実行中...")
    text = extract_text(filepath)

    print("🧠 LLMへファイル名候補をリクエスト中...")
    candidates = get_filename_candidates(text, prompt_template)

    if not candidates:
        final_name = get_next_sequence_name(save_dir)
        print(f"⚠️ 候補を取得できなかったため、自動連番で保存します: {final_name}")
    else:
        print(f"✨ 取得した候補: {candidates}")
        print("🖥️ UIを表示します...")
        # 単一のTkウィンドウとしてダイアログを起動
        final_name = show_rename_dialog(candidates, filepath, timeout_seconds=timeout)
        
    if final_name:
        new_filename = f"{final_name}.png"
        dest_path = os.path.join(save_dir, new_filename)

        # 同名ファイルが存在する場合の重複回避 (_1, _2 ...)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(save_dir, f"{final_name}_{counter}.png")
            counter += 1

        try:
            shutil.move(filepath, dest_path)
            print(f"✅ 保存完了: {dest_path}\n")
        except Exception as e:
            print(f"❌ ファイル移動エラー: {e}")
    else:
        print("⚠️ キャンセルされました。ファイルは元の場所に残ります。\n")


if __name__ == "__main__":
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("エラー: config.yaml が見つかりません。")
        exit(1)

    watch_dir = os.path.expanduser(config['directories']['watch_dir'])
    idle_timeout = config['ui'].get('idle_timeout_minutes', 0) * 60

    handler = ScreenshotHandler(watch_dir)
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()

    # 監視開始前に保存されたスクショを取りこぼさないよう、起動直後に一度スキャンする
    enqueue_recent_files(handler, watch_dir)

    print(f"👀 監視を開始しました: {watch_dir}")
    print("終了する場合は Ctrl+C を押してください。")

    # メインの軽量監視ループ（0.5秒おきにキューをチェック）
    last_activity = time.time()
    try:
        while True:
            try:
                filepath = file_queue.get_nowait()
                process_screenshot(filepath, config)
                last_activity = time.time()
            except queue.Empty:
                if idle_timeout > 0 and time.time() - last_activity > idle_timeout:
                    print(f"💤 {idle_timeout // 60}分間スクショがなかったため終了します。")
                    break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n監視を終了しました。")

    observer.stop()
    observer.join()

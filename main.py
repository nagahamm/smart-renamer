import warnings
warnings.filterwarnings("ignore")

import os
import time
import shutil
import yaml
import queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

from ocr_engine import extract_text
from llm_client import get_filename_candidates
from popup_ui import show_rename_dialog

file_queue = queue.Queue()

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, watch_dir):
        self.watch_dir = watch_dir

    def on_created(self, event):
        filename = os.path.basename(event.src_path)
        if not event.is_directory and event.src_path.lower().endswith('.png') and not filename.startswith('.'):
            print(f"📸 新規スクリーンショットを検知: {event.src_path}")
            time.sleep(1.5)
            file_queue.put(event.src_path)

def process_screenshot(filepath, config):
    save_dir = os.path.expanduser(config['directories']['save_dir'])
    timeout = config['ui']['timeout_seconds']
    prompt_template = config['llm_rules']['prompt_template']
    
    os.makedirs(save_dir, exist_ok=True)

    print("🔍 OCR処理を実行中...")
    text = extract_text(filepath)

    print("🧠 LLMへファイル名候補をリクエスト中...")
    candidates = get_filename_candidates(text, prompt_template)

    print("🖥️ UIを表示します...")
    final_name = show_rename_dialog(candidates, timeout_seconds=timeout)

    if final_name:
        new_filename = f"{final_name}.png"
        dest_path = os.path.join(save_dir, new_filename)

        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(save_dir, f"{final_name}_{counter}.png")
            counter += 1

        try:
            shutil.move(filepath, dest_path)
            print(f"✅ 保存完了: {dest_path}")
        except Exception as e:
            print(f"❌ ファイル移動エラー: {e}")
    else:
        print("⚠️ キャンセルされました。ファイルは元の場所に残ります。")

if __name__ == "__main__":
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("エラー: config.yaml が見つかりません。")
        exit(1)

    watch_dir = os.path.expanduser(config['directories']['watch_dir'])
    handler = ScreenshotHandler(watch_dir)
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()

    print(f"👀 監視を開始しました: {watch_dir}")
    print("終了する場合は Ctrl+C を押してください。")
    
    try:
        while True:
            try:
                filepath = file_queue.get_nowait()
                process_screenshot(filepath, config)
            except queue.Empty:
                pass
            
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n監視を終了しました。")
    
    observer.join()
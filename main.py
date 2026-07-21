import os
# Tkの警告を非表示にする設定
os.environ["TK_SILENCE_DEPRECATION"] = "1"

import time
import shutil
import yaml
import queue
import re # 正規表現を使って数字を探すため
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
processed_files = set()  # 重複処理防止用
                

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, watch_dir):
        self.watch_dir = watch_dir

    def _enqueue(self, path):
        filename = os.path.basename(path)
        # 隠しファイル除外 ＆ PNG画像のみ
        if not path.lower().endswith('.png') or filename.startswith('.'):
            return
        
        # 1.5秒待ってファイルが完全に書き込まれるのを待つ
        time.sleep(1.5)
        if os.path.exists(path) and path not in processed_files:
            print(f"📸 新規スクリーンショットを検知: {path}")
            processed_files.add(path)
            file_queue.put(path)

    # Macのスクショ特有の挙動（隠しファイルからのリネーム）を検知する
    def on_moved(self, event):
        if not event.is_directory:
            self._enqueue(event.dest_path)

    # 他のアプリから直接保存された場合のために、作成時の検知も残しておく
    def on_created(self, event):
        if not event.is_directory:
            self._enqueue(event.src_path)

def get_next_sequence_name(save_dir):
    # 保存先フォルダを確認し、0001からの連番を含むファイル名を生成する
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    existing_files = os.listdir(save_dir)
    max_seq = 0

    # 例: "2026-07-20__0001_Capture" のようなファイル名から数字部分(0001)を探す
    pattern = re.compile(rf"{today_str}__(\d{{4}})_Capture")
    
    for filename in existing_files:
        match = pattern.search(filename)
        if match:
            seq = int(match.group(1))
            if seq > max_seq:
                max_seq = seq
                
    # 最大値に1を足して、4桁（0001など）にフォーマットする
    next_seq = max_seq + 1
    return f"{today_str}__{next_seq:04d}_Capture"

def process_screenshot(filepath, config):
    save_dir = os.path.expanduser(config['directories']['save_dir'])
    timeout = config['ui']['timeout_seconds']
    prompt_template = config['llm_rules']['prompt_template']
    
    os.makedirs(save_dir, exist_ok=True)

    print("🔍 OCR処理を実行中...")
    text = extract_text(filepath)

    print("🧠 LLMへファイル名候補をリクエスト中...")
    candidates = get_filename_candidates(text, prompt_template)

    # candidatesのチェックとログ強化
    if not candidates:
        final_name = get_next_sequence_name(save_dir)
        print(f"⚠️ 候補を取得できなかったため、自動連番で保存します: {final_name}")
    else:
        print(f"✨ 取得した候補: {candidates}")
        # 正常時はUIを表示
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

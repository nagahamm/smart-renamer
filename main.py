import argparse
import os
import queue
import re
import shutil
import time
import yaml
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

from ocr_engine import extract_text, is_supported
from llm_client import API_KEY_ENV, get_api_key, get_filename_candidates
from popup_ui import run_event_loop, show_rename_dialog, stop_event_loop

file_queue = queue.Queue()
processed_files = set()  # 重複処理防止用のセット

# 「撮りたて」と見なす更新時刻の上限（秒）。
# launchdのWatchPathsで起動された直後のスキャンと、監視中のイベント判定の両方で使う。
RECENT_FILE_MAX_AGE_SECONDS = 60


class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, watch_dir):
        self.watch_dir = watch_dir

    def enqueue(self, path):
        filename = os.path.basename(path)
        # 隠しファイル除外 ＆ PNG画像のみ対象
        if not path.lower().endswith('.png') or filename.startswith('.'):
            return

        if not os.path.exists(path) or path in processed_files:
            return

        # 手動リネーム（--rename）で既存ファイルの名前を変えると on_moved が発火するが、
        # 撮りたてのスクショと違い更新時刻は古いままなので、それを手掛かりに除外する。
        # 手動モードは別プロセスのため processed_files では共有できない。
        if not is_recent(path):
            return

        # 即座にキューへ入れる（イベントスレッドをブロックしない）
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


def is_recent(path):
    """撮りたてのファイルか（更新時刻が十分に新しいか）。"""
    try:
        return time.time() - os.path.getmtime(path) <= RECENT_FILE_MAX_AGE_SECONDS
    except OSError:
        return False


def enqueue_recent_files(handler, watch_dir):
    """launchdのWatchPathsで起動された場合、起動のきっかけとなったスクショは
    watchdogのイベントに乗らないため、起動直後に直接キューへ入れる。"""
    if not os.path.isdir(watch_dir):
        return

    for filename in os.listdir(watch_dir):
        path = os.path.join(watch_dir, filename)
        if os.path.isfile(path):
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


def collect_targets(paths):
    """CLIで渡されたパスを、リネーム対象のファイル一覧に展開する。

    フォルダは直下のみを見る。再帰すると意図せず大量のファイルを拾い、
    そのぶんAPIを呼んでしまうため。
    """
    targets = []
    for path in paths:
        if os.path.isdir(path):
            entries = sorted(os.listdir(path))
            candidates = [os.path.join(path, name) for name in entries]
        else:
            candidates = [path]

        for candidate in candidates:
            filename = os.path.basename(candidate)
            if filename.startswith('.') or not os.path.isfile(candidate):
                continue
            if is_supported(candidate) and candidate not in targets:
                targets.append(candidate)

    return targets


def rename_manually(paths, config):
    """選ばれたファイルをその場でリネームする（移動しない）。"""
    targets = collect_targets(paths)
    if not targets:
        print("対象になるファイルがありません（対応形式: png / jpg / jpeg / heic / pdf）")
        return

    total = len(targets)
    print(f"🗂 {total}件のファイルをリネームします")

    for index, filepath in enumerate(targets, start=1):
        print(f"\n[{index}/{total}] {filepath}")
        candidates = build_candidates(filepath, config)

        if not candidates:
            # 手動モードでは連番より、元の名前を出して直してもらう方が親切
            candidates = [os.path.splitext(os.path.basename(filepath))[0]]
            print("⚠️ 候補を取得できませんでした。元のファイル名を表示します。")
        else:
            print(f"✨ 取得した候補: {candidates}")

        final_name, aborted = show_rename_dialog(
            candidates,
            filepath,
            timeout_seconds=None,      # 自分で決める必要があるためタイムアウトしない
            progress=(index, total),
            foreground=True,           # 自分で起動しているので前面に出す
            dest_dir=os.path.dirname(filepath),  # 移動はせず、元のフォルダのまま
        )

        if aborted:
            print("⏹ 残りを中止しました。")
            return

        if final_name:
            # 移動はせず、元のフォルダの中で名前だけ変える
            apply_rename(filepath, final_name, os.path.dirname(filepath))
        else:
            print("↩︎ スキップしました。")


# ファイル名に含まれる日付。区切りの有無と種類だけが違う
DATE_PATTERNS = [
    re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})_(\d{2})_(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"),
]


def extract_date_from_name(filepath):
    """ファイル名に含まれる日付を YYYY-MM-DD で返す。見つからなければ None。"""
    stem = os.path.splitext(os.path.basename(filepath))[0]
    for pattern in DATE_PATTERNS:
        for year, month, day in pattern.findall(stem):
            try:
                return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
            except ValueError:
                # 8桁の数字が金額や連番だった場合。次の候補を試す
                continue
    return None


def get_file_date(filepath):
    """対象ファイルの日付。ファイル名の日付を優先し、無ければ作成日時を使う。"""
    from_name = extract_date_from_name(filepath)
    if from_name:
        return from_name

    stat = os.stat(filepath)
    # macOSでは作成日時が取れる。取れない場合のみ更新日時にフォールバックする
    timestamp = getattr(stat, "st_birthtime", stat.st_mtime)
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def prefer_file_date(candidates, file_date, today):
    """本日の日付で生成された候補を、最後の1件を残してファイルの日付に差し替える。

    OCR本文から日付を読み取れた候補は本日の日付にならないため、そのまま残る。
    内容由来の日付の方が正しく、書き換えると壊れるため触らない。
    本日の日付の候補を1件残すのは、撮り直しなどで今日の日付を使いたい場合のため。
    """
    if file_date == today:
        return candidates

    # YYYY-MM-DD と、学習系ルールの YYYY-MM の両方を対象にする
    prefixes = [(today, file_date), (today[:7], file_date[:7])]

    matches = []
    for index, name in enumerate(candidates):
        # 長い YYYY-MM-DD から先に見て、1候補につき1回だけ差し替える
        for old, new in prefixes:
            if name.startswith(old):
                matches.append((index, old, new))
                break

    result = list(candidates)
    for index, old, new in matches[:-1]:
        result[index] = new + result[index][len(old):]
    return result


def build_candidates(filepath, config):
    """OCR/テキスト抽出からファイル名候補までをまとめる。監視・手動の共通処理。"""
    print("🔍 テキストを抽出中...")
    text = extract_text(filepath)

    print("🧠 LLMへファイル名候補をリクエスト中...")
    candidates = get_filename_candidates(
        text,
        config['llm_rules']['prompt_template'],
        config['llm']['model'],
        config['llm']['timeout_seconds'],
    )
    if not candidates:
        return candidates

    return prefer_file_date(
        candidates, get_file_date(filepath), datetime.now().strftime("%Y-%m-%d")
    )


def process_screenshot(filepath, config):
    # OSによるファイル書き込み完了を待つため1秒待機
    time.sleep(1.0)
    if not os.path.exists(filepath):
        print(f"⚠️ ファイルが存在しないためスキップします: {filepath}")
        return

    save_dir = os.path.expanduser(config['directories']['save_dir'])
    timeout = config['ui']['timeout_seconds']

    os.makedirs(save_dir, exist_ok=True)

    candidates = build_candidates(filepath, config)

    if not candidates:
        final_name = get_next_sequence_name(save_dir)
        print(f"⚠️ 候補を取得できなかったため、自動連番で保存します: {final_name}")
    else:
        print(f"✨ 取得した候補: {candidates}")
        print("🖥️ UIを表示します...")
        final_name, _ = show_rename_dialog(
            candidates, filepath, timeout_seconds=timeout, dest_dir=save_dir
        )
        
    if final_name:
        apply_rename(filepath, final_name, save_dir)
    else:
        print("⚠️ キャンセルされました。ファイルは元の場所に残ります。\n")


def apply_rename(filepath, final_name, dest_dir):
    """元の拡張子を保ったままリネームして dest_dir へ移す。"""
    # 拡張子を決め打ちすると、PNG以外を渡したときに壊れたファイル名になる
    extension = os.path.splitext(filepath)[1]
    dest_path = os.path.join(dest_dir, f"{final_name}{extension}")

    # 同名ファイルが存在する場合の重複回避 (_1, _2 ...)
    counter = 1
    while os.path.exists(dest_path):
        dest_path = os.path.join(dest_dir, f"{final_name}_{counter}{extension}")
        counter += 1

    try:
        shutil.move(filepath, dest_path)
        print(f"✅ 保存完了: {dest_path}\n")
        return dest_path
    except Exception as e:
        print(f"❌ ファイル移動エラー: {e}")
        return None


def load_config():
    # 実行ディレクトリに依存せず、スクリプトと同じ場所の設定を読む
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"エラー: config.yaml が見つかりません。({config_path})")
        exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="スクリーンショットのリネームツール")
    parser.add_argument(
        "--rename",
        nargs="+",
        metavar="PATH",
        help="指定したファイル（またはフォルダ直下のファイル）をその場でリネームする",
    )
    args = parser.parse_args()

    config = load_config()

    # キーが無いと候補が取れず、全ファイルが無言で連番になる。
    # API障害による連番フォールバックとは違い設定ミスは直らないので、起動時に弾く
    if not get_api_key():
        print(f"エラー: {API_KEY_ENV} が設定されていません。")
        print(".env に GEMINI_API_KEY=<キー> を記述してください。")
        exit(1)

    # 手動モード: 常駐せず、渡されたファイルを処理して終了する
    if args.rename:
        rename_manually(args.rename, config)
        exit(0)

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

    state = {"last_activity": time.time(), "processing": False}

    def check_queue():
        """0.5秒おきにキューを確認する。イベントループから呼ばれる。"""
        # ダイアログ表示中はネストしたイベントループが回っており、ここが再入する。
        # ガードが無いと2件目の処理が入れ子で走り、ダイアログが二重に開く。
        if state["processing"]:
            return

        try:
            filepath = file_queue.get_nowait()
        except queue.Empty:
            if idle_timeout > 0 and time.time() - state["last_activity"] > idle_timeout:
                print(f"💤 {idle_timeout // 60}分間スクショがなかったため終了します。")
                stop_event_loop()
            return

        state["processing"] = True
        try:
            process_screenshot(filepath, config)
        finally:
            state["processing"] = False
            state["last_activity"] = time.time()

    # 待機中もイベントを処理し続ける必要があるため、Qtのイベントループを本体にする
    run_event_loop(check_queue, interval_ms=500)

    print("\n監視を終了しました。")
    observer.stop()
    observer.join()

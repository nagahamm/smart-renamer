# Screenshot Auto-Renamer

Macで撮影したスクリーンショットをリアルタイムに自動検知し、Google Gemini (3.1 Flash Lite) のOCR機能とLLMを活用して、内容（領収書、財務データ、学習教材など）に合わせた最適なファイル名を提案・自動リネームするバックグラウンドツールです。

PyQt6によるポップアップUIからキーボード（`↑`/`↓`/`Enter`）またはマウスで選択するだけで、指定したディレクトリへ自動でリネーム＆移動保存されます。


## 🌟 主な特長

- **リアルタイム監視**: macOS特有のスクショ生成挙動（一時ファイルからのリネーム発生）を `watchdog` で確実に検知。
- **高精度な候補生成**: 画像内のテキストをOCR解析し、Gemini API（`gemini-3.1-flash-lite`）により文脈に沿った3つのファイル名候補を即座に提案。
- **キーボードナビゲーション対応**: `↑` / `↓` キーで選択、`Enter` で決定、`Esc` でキャンセル。キーボードから手を離さずに1秒でリネームが完了。
- **自動フォールバック**: API制限やタイムアウト発生時は、日付＋4桁連番（例: `2026-07-21__0001_Capture.png`）で自動保存。
- **超軽量常駐 (launchd)**: macOS標準のバックグラウンド管理（`launchd`）に対応。待機時CPU/GPU消費 0.0%、メモリ約20〜30MBの省電力設計。
- **アイドルタイムアウト**: 一定時間スクショが無ければ自動終了し、常駐プロセスを残さない（`config.yaml` の `ui.idle_timeout_minutes`、デフォルト30分）。次のスクショ撮影時に `launchd` の `WatchPaths` で自動復帰。
- **プレビュー表示**: リネーム候補と一緒に対象ファイルの中身を表示。ウィンドウは自由にリサイズでき、サイズは次回に引き継がれる。
- **手動リネーム**: `--rename` で任意のファイル・フォルダをその場でリネーム。Finderの右クリックからも実行可能。候補の選択に加えて**自分で名前を書き換えられる**。`pdf` / `jpg` / `heic` にも対応。


## 🚀 1. 仮想環境の作成と有効化

システム環境を汚さないために、Pythonの仮想環境（`.venv`）を作成して実行します。ターミナルを開き、以下のコマンドを順番に実行してください。

```bash
# プロジェクトのディレクトリに移動
cd ~/Documents/screenshot_renamer

# 仮想環境（.venv）を作成
python3 -m venv .venv

# 仮想環境を有効化（ターミナルの先頭に (.venv) と表示されれば成功です）
source .venv/bin/activate
```
※以降の作業は、必ずこの仮想環境が有効化された状態で行ってください。

## 📦 2. 必要なパッケージのインストール

仮想環境を有効にした状態で、本ツールの動作に必要な外部ライブラリをインストールします。

```bash
pip install watchdog google-genai pyyaml python-dotenv PyQt6 pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-Vision
```

**【インストールされる主なパッケージ】**

- `watchdog`: デスクトップの新規スクリーンショット検知
- `google-genai`: 新仕様のGemini APIクライアント
- `PyQt6`: 高速かつ洗練されたGUIポップアップダイアログ
- `pyyaml`: `config.yaml` の読み込み
- `python-dotenv`: `.env` ファイルからのAPIキー読み込み
- `pyobjc-framework-*`: Vision framework によるOCR（Cocoa / Quartz / Vision）


## 🔐 3. APIキーの設定 (Configuration)

セキュリティを確保するため、APIキーはGitの管理対象外である `.env` ファイルに保存します。

1. プロジェクトのルートディレクトリ（`~/Documents/screenshot_renamer`）に `.env` という名前のファイルを作成します。
2. 取得したGoogle Gemini APIキーを以下のように記述して保存してください。

```env
# .env (このファイルはGitにはプッシュされません)
GEMINI_API_KEY=ここにあなたのAPIキー(AIza...から始まる文字列)を貼り付けてください
```

※監視するフォルダや保存先、細かい命名規則の設定を変更したい場合は、同階層にある `config.yaml` を編集してください。

## 💡 4. 使い方 (Usage)

準備が完了したら、ツールを起動して実際にスクリーンショットを処理します。

### ツールの起動
ターミナルで仮想環境を有効にした状態（`.venv`）で、以下のコマンドを実行します。

```bash
python main.py
```

ターミナルに以下のように表示されれば、正常に起動し、監視がスタートしています。
```text
👀 監視を開始しました: ~/Desktop
終了する場合は Ctrl+C を押してください。
```

### 実行の流れ
1. **スクショ撮影**: Macの標準機能（`Cmd + Shift + 3` または `4`）でスクリーンショットを撮影します。
2. **自動検知とAI処理**: プログラムが画像を検知し、GeminiにOCRとファイル名の生成をリクエストします。
3. **ポップアップ確認**: 画面にリネーム候補のポップアップが表示されます。
4. **保存**: 最適な候補をクリック（またはタイムアウト）すると、`config.yaml` で指定したフォルダ（デフォルトは `~/Documents/Screenshots`）に自動でリネームされて移動します。

ツールの実行を終了したい場合は、ターミナル上で `Ctrl + C` を押してください。

### 既存ファイルを手動でリネームする

他のフォルダにあるファイルや、一度リネームしたファイルを付け直したい場合は `--rename` を使います。

```bash
python main.py --rename ~/Documents/Screenshots/2026-08-18__SBI__口座管理_Capture.png
python main.py --rename ~/Downloads          # フォルダ直下のファイルをまとめて
```

- 対応形式は `png` / `jpg` / `jpeg` / `heic` / `pdf`
- **その場でリネームします。** 監視モードと違い `save_dir` へは移動しません
- フォルダを渡した場合、**直下のファイルのみ**が対象です（サブフォルダは見ません）
- タイムアウトはありません。候補を選ぶか、**編集欄で自分で書き換えて** `Enter` で確定します
- 複数件のときは `3 / 50` の進捗が出ます。`Esc` でその1件をスキップ、「すべて中止」で残り全部を中止

## 🖱 5. Finderの右クリックからリネームする（Quick Action）

`--rename` をFinderの右クリックメニューに登録すると、ファイルを選んで即リネームできます。

1. **ショートカット.app** を開き、新規ショートカットを作成
2. 「クイックアクション」として登録し、**受け取る項目を「ファイルとフォルダ」**、**「Finder」から使用可能** に設定
3. アクション「**シェルスクリプトを実行**」を追加し、以下を設定
   - 入力: **ショートカットの入力**
   - 入力の引き渡し方法: **引数として**
   - シェルスクリプト:

```bash
cd /Users/cygnu/Documents/screenshot_renamer
.venv/bin/python main.py --rename "$@"
```

4. ショートカットに名前を付けて保存（例: `Rename with Gemini`）

   この名前がFinderの右クリックメニューにそのまま表示されます。

Finderでファイルやフォルダを選んで右クリック →「クイックアクション」から実行できます。

※ Desktop / Documents / Downloads 配下のファイルを操作するには、実行するPythonに**フルディスクアクセス**の許可が必要になる場合があります（システム設定 → プライバシーとセキュリティ → フルディスクアクセス）。

## ⚙️ 6. macOS ログイン時自動常駐化 (launchd)

手動起動せず、Mac起動時にバックグラウンドで完全自動実行させる設定です。

### 6-1. launchd 用設定ファイル (.plist) の作成

```bash
cat << 'PLIST_EOF' > ~/Library/LaunchAgents/com.user.screenshot_renamer.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "[http://www.apple.com/DTDs/PropertyList-1.0.dtd](http://www.apple.com/DTDs/PropertyList-1.0.dtd)">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.screenshot_renamer</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/osascript</string>
        <string>-e</string>
        <string>do shell script "cd /Users/cygnu/Documents/screenshot_renamer && .venv/bin/python main.py > app.log 2> app_error.log"</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <!-- 異常終了時のみ再起動する。アイドルタイムアウトによる正常終了では再起動しない -->
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <!-- 監視ディレクトリに変更があった時（＝スクショ撮影時）に launchd が再起動する -->
    <key>WatchPaths</key>
    <array>
        <string>/Users/cygnu/Desktop</string>
    </array>

    <key>LimitLoadToSessionType</key>
    <array>
        <string>Aqua</string>
    </array>
</dict>
</plist>
PLIST_EOF
```

※ `WatchPaths` のパスは `config.yaml` の `watch_dir` と一致させてください（`~` は展開されないため絶対パスで記述します）。

### 6-2. 権限設定と常駐登録
```bash
# フォルダ権限の許可
chmod 755 ~/Library/LaunchAgents

# ユーザーセッションへ登録・起動
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.screenshot_renamer.plist
```

### 6-3. 管理用コマンド
動作確認: `launchctl list | grep screenshot_renamer` または `ps aux | grep main.py`

サービス停止: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.user.screenshot_renamer.plist`

再読み込み:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.user.screenshot_renamer.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.screenshot_renamer.plist
```

ログ確認: `cat app_error.log`

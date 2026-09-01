#!/bin/bash
#
# smart-renamer のセットアップ。
# 仮想環境・APIキー・常駐登録・Finderの右クリックメニューまでを一括で行う。
# 何度実行しても同じ結果になる（冪等）。
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
VENV_DIR="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"

LAUNCHD_LABEL="com.user.smart_renamer"
PLIST_PATH="$HOME/Library/LaunchAgents/$LAUNCHD_LABEL.plist"

QUICK_ACTION_NAME="Rename with Gemini"
QUICK_ACTION_PATH="$HOME/Library/Services/$QUICK_ACTION_NAME.workflow"

step() { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
info() { printf '  %s\n' "$1"; }
warn() { printf '  \033[33m⚠️  %s\033[0m\n' "$1"; }

if [ "$(uname -s)" != "Darwin" ]; then
    echo "エラー: macOS 専用です（Vision framework / PyObjC / PyQt6 に依存）。" >&2
    exit 1
fi


# 1. 仮想環境と依存パッケージ
step "仮想環境と依存パッケージ"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    info "$VENV_DIR を作成します"
    python3 -m venv "$VENV_DIR"
else
    info "既存の $VENV_DIR を使います"
fi

info "requirements.txt をインストール中..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"
info "完了"


# 2. APIキー
step "Gemini APIキー"

if [ -f "$ENV_FILE" ] && grep -qE '^GEMINI_API_KEY=.+' "$ENV_FILE"; then
    info ".env に設定済みです。変更しません"
elif [ ! -t 0 ]; then
    warn ".env が未設定です。対話実行できないためスキップします"
    warn "後で $ENV_FILE に GEMINI_API_KEY=<キー> を記述してください"
else
    info "https://aistudio.google.com/apikey で取得したキーを貼り付けてください"
    info "（入力は表示されません。空のまま Enter でスキップ）"
    printf '  GEMINI_API_KEY: '
    read -r -s api_key
    printf '\n'

    if [ -z "$api_key" ]; then
        warn "スキップしました。キーが無いとファイル名は連番になります"
    else
        # 既存の .env を壊さないよう、古い行だけ落として追記する
        if [ -f "$ENV_FILE" ]; then
            grep -vE '^GEMINI_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
            mv "$ENV_FILE.tmp" "$ENV_FILE"
        fi
        printf 'GEMINI_API_KEY=%s\n' "$api_key" >> "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        info ".env に保存しました"
    fi
fi


# 3. launchd への常駐登録
step "常駐の登録（launchd）"

# WatchPaths は config.yaml の watch_dir と一致させる必要がある。
# チルダは launchd が展開しないため、絶対パスに直してから埋め込む。
watch_dir="$("$VENV_DIR/bin/python" - "$PROJECT_DIR/config.yaml" <<'PY'
import os, sys, yaml
with open(sys.argv[1], encoding="utf-8") as f:
    config = yaml.safe_load(f)
print(os.path.expanduser(config["directories"]["watch_dir"]))
PY
)"
info "監視先: $watch_dir"

mkdir -p "$HOME/Library/LaunchAgents"
chmod 755 "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LAUNCHD_LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/osascript</string>
        <string>-e</string>
        <string>do shell script "cd $PROJECT_DIR &amp;&amp; .venv/bin/python -u main.py &gt; app.log 2&gt; app_error.log"</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <!-- 監視ディレクトリに変更があった時（＝スクショ撮影時）に launchd が起動する。
         起動に失敗した場合も、次のスクショまで再試行しない -->
    <key>WatchPaths</key>
    <array>
        <string>$watch_dir</string>
    </array>

    <key>LimitLoadToSessionType</key>
    <array>
        <string>Aqua</string>
    </array>
</dict>
</plist>
PLIST_EOF

plutil -lint "$PLIST_PATH" > /dev/null

# 登録済みなら一度外さないと bootstrap が Input/output error になる
launchctl bootout "gui/$(id -u)/$LAUNCHD_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
info "$PLIST_PATH を登録しました"


# 4. Finderの右クリックメニュー（Automator の Quick Action）
step "Finderの右クリックメニュー（サービス）"

rm -rf "$QUICK_ACTION_PATH"
mkdir -p "$QUICK_ACTION_PATH/Contents"

cat > "$QUICK_ACTION_PATH/Contents/Info.plist" << INFO_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleIdentifier</key>
    <string>com.user.smart-renamer.quickaction</string>
    <key>CFBundleName</key>
    <string>$QUICK_ACTION_NAME</string>
    <key>CFBundlePackageType</key>
    <string>BNDL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>NSServices</key>
    <array>
        <dict>
            <key>NSMenuItem</key>
            <dict>
                <key>default</key>
                <string>$QUICK_ACTION_NAME</string>
            </dict>
            <key>NSMessage</key>
            <string>runWorkflowAsService</string>
            <key>NSSendFileTypes</key>
            <array>
                <string>public.item</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
INFO_EOF

cat > "$QUICK_ACTION_PATH/Contents/document.wflow" << WFLOW_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>AMApplicationBuild</key>
    <string>528</string>
    <key>AMApplicationVersion</key>
    <string>2.10</string>
    <key>AMDocumentVersion</key>
    <string>2</string>
    <key>actions</key>
    <array>
        <dict>
            <key>action</key>
            <dict>
                <key>AMAccepts</key>
                <dict>
                    <key>Container</key>
                    <string>List</string>
                    <key>Optional</key>
                    <true/>
                    <key>Types</key>
                    <array>
                        <string>com.apple.cocoa.string</string>
                    </array>
                </dict>
                <key>AMActionVersion</key>
                <string>2.0.3</string>
                <key>AMApplication</key>
                <array>
                    <string>Automator</string>
                </array>
                <key>AMParameterProperties</key>
                <dict>
                    <key>COMMAND_STRING</key>
                    <dict/>
                    <key>CheckedForUserDefaultShell</key>
                    <dict/>
                    <key>inputMethod</key>
                    <dict/>
                    <key>shell</key>
                    <dict/>
                    <key>source</key>
                    <dict/>
                </dict>
                <key>AMProvides</key>
                <dict>
                    <key>Container</key>
                    <string>List</string>
                    <key>Types</key>
                    <array>
                        <string>com.apple.cocoa.string</string>
                    </array>
                </dict>
                <key>ActionBundlePath</key>
                <string>/System/Library/Automator/Run Shell Script.action</string>
                <key>ActionName</key>
                <string>Run Shell Script</string>
                <key>ActionParameters</key>
                <dict>
                    <key>COMMAND_STRING</key>
                    <string>"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/main.py" --rename "\$@"</string>
                    <key>CheckedForUserDefaultShell</key>
                    <true/>
                    <key>inputMethod</key>
                    <integer>1</integer>
                    <key>shell</key>
                    <string>/bin/zsh</string>
                    <key>source</key>
                    <string></string>
                </dict>
                <key>BundleIdentifier</key>
                <string>com.apple.RunShellScript</string>
                <key>CFBundleVersion</key>
                <string>2.0.3</string>
                <key>CanShowSelectedItemsWhenRun</key>
                <false/>
                <key>CanShowWhenRun</key>
                <true/>
                <key>Category</key>
                <array>
                    <string>AMCategoryUtilities</string>
                </array>
                <key>Class Name</key>
                <string>RunShellScriptAction</string>
                <key>InputUUID</key>
                <string>$(uuidgen)</string>
                <key>OutputUUID</key>
                <string>$(uuidgen)</string>
                <key>UUID</key>
                <string>$(uuidgen)</string>
                <key>UnlocalizedApplications</key>
                <array>
                    <string>Automator</string>
                </array>
                <key>arguments</key>
                <dict/>
                <key>isViewVisible</key>
                <integer>1</integer>
                <key>location</key>
                <string>309.000000:253.000000</string>
                <key>nibPath</key>
                <string>/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib</string>
            </dict>
            <key>isViewVisible</key>
            <integer>1</integer>
        </dict>
    </array>
    <key>connectors</key>
    <dict/>
    <key>workflowMetaData</key>
    <dict>
        <key>serviceApplicationBundleID</key>
        <string></string>
        <key>serviceInputTypeIdentifier</key>
        <string>com.apple.Automator.fileSystemObject</string>
        <key>serviceOutputTypeIdentifier</key>
        <string>com.apple.Automator.nothing</string>
        <key>serviceProcessesInput</key>
        <integer>0</integer>
        <key>workflowTypeIdentifier</key>
        <string>com.apple.Automator.servicesMenu</string>
    </dict>
</dict>
</plist>
WFLOW_EOF

plutil -lint "$QUICK_ACTION_PATH/Contents/Info.plist" > /dev/null
plutil -lint "$QUICK_ACTION_PATH/Contents/document.wflow" > /dev/null

# Services メニューのキャッシュを更新する
/System/Library/CoreServices/pbs -update 2>/dev/null || true
info "「${QUICK_ACTION_NAME}」を登録しました"


step "セットアップ完了"
info "常駐:       launchctl print gui/$(id -u)/$LAUNCHD_LABEL"
info "ログ:       $PROJECT_DIR/app.log"
info "右クリック: Finderでファイルを選択 →「サービス」→「${QUICK_ACTION_NAME}」"
printf '\n'
warn "メニューに出てこない場合は Finder を再起動してください: killall Finder"
warn "Operation not permitted で失敗する場合は、システム設定 → プライバシーとセキュリティ →"
warn "フルディスクアクセス に WorkflowServiceRunner を追加してください"
warn "（$PROJECT_DIR がDesktop/Documents/Downloads配下にある場合に必要です）"
warn "「クイックアクション」の側に、より上位に出したい場合は README の"
warn "「ショートカット.app で登録する場合」を参照してください"

# CLAUDE.md

## プロジェクト概要

macOSで撮影したスクリーンショットを `watchdog` で検知し、Vision framework のOCRとGemini APIでファイル名候補を生成、PyQt6のポップアップで選択させてリネーム・移動する常駐ツール。

監視による自動リネームに加え、`--rename` で任意のファイル・フォルダをその場でリネームする手動モードを持つ。

| ファイル | 役割 |
| --- | --- |
| `main.py` | ファイル監視、処理キュー、CLI、全体のフロー制御 |
| `ocr_engine.py` | Vision framework によるOCR、PDFのテキスト抽出とページ描画 |
| `llm_client.py` | Gemini APIへのファイル名候補リクエスト |
| `popup_ui.py` | PyQt6のリネーム候補ダイアログ、Qtイベントループの管理 |
| `config.yaml` | 全ての設定値と命名規則プロンプト |
| `setup.sh` | 仮想環境・`.env`・launchd常駐・Finderの右クリック登録のセットアップ |
| `requirements.txt` | 依存パッケージ。READMEと二重管理しない |
| `docs/` | READMEに貼るダイアログの画像 |

**設定値をコードにハードコードしないこと。** 監視先・保存先・タイムアウト・モデル名・命名規則は全て `config.yaml` に集約する。

Communication Rules・Interaction & Execution Policy はグローバル `~/.claude/CLAUDE.md` の通り。

## Git Commit Rules

Conventional Commits 規約（英語）に準拠する。

```
<type>(<scope>): <short summary>

- 変更点を箇条書き

Fixes #<issue番号>
```

対応するIssueを `Fixes #N`（バグ修正）または `Closes #N`（機能追加）で必ず閉じる。1つのIssueに複数コミットが紐づく場合は、最後のコミットにのみ書く。

粒度・順序・amend運用はグローバル `~/.claude/CLAUDE.md` の通り。

プロジェクト固有の補足: 同種のタスクや機械的に連動する変更（例: クラス名リネームに伴う
複数ファイルの同時修正）は1コミットにまとめてよい。

### タグ

**このプロジェクトは既に一般公開済みのため、グローバルの「開発中はv0.x.xに留める」は
適用しない。** PATCH/MINOR/MAJORの決め方（利用者から見た変化の大きさ）自体はグローバルの通り。

プロジェクト固有の補足:

- ライブラリ的な厳密なSemVerではなく、一般的なアプリのリリース慣習に合わせる。`fix` が1件でも `feat` が混ざっていても、体感が変わらない範囲なら PATCH のままでよい。
- **利用者側の再設定が必要な場合**（`.plist` の書き換え、`config.yaml` への項目追加など）は、バージョンを上げる理由にはしないが、タグの注釈に必ず手順を明記する。

```
git tag -a v1.0.2 -m "Release v1.0.2: <利用者から見た変更点> (#1, #2, #3)"
git push origin v1.0.2
```

## Core Principles

共通原則（SOLID/KISS/YAGNI/DRY）はグローバル `~/.claude/CLAUDE.md` の通り。

プロジェクト固有の適用: **SOLID**: 各モジュールの責務を上表の通りに保つ。OCR・LLM・UIの実装をまたいで混ぜない。

## 開発環境の制約

このリポジトリはmacOS専用（Vision framework / PyObjC / PyQt6）。検証と確認の基本方針は
グローバル `~/.claude/CLAUDE.md` の通り。

確認できる範囲は実行環境によって変わる。

- **Mac実機で作業している場合**: CLI・OCR・LLM呼び出し・launchd登録まで実際に動かせる。`QT_QPA_PLATFORM=offscreen` を使えばダイアログの描画も確認できる。動かせるものは動かしてからコミットする。
- **Linuxのサンドボックス上の場合**: macOS依存を含まないロジックは、依存モジュールをスタブ化すれば検証できる。検証可能なものは検証してからコミットする。

どちらの環境でも**自動化できない確認がある。** Finderの右クリックメニューへの表示、実ウィンドウのフォーカス挙動、システム設定での権限付与などはGUI操作が必要で、コマンドからは追い切れない。これらは「未確認」と明記して利用者に依頼する。

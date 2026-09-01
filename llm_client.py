import os
import yaml
import json
from datetime import datetime
from google import genai
from google.genai import types


# yamlファイルを読み込む処理を追加
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# yamlから設定を取得（値がない場合のデフォルト値も設定）
MODEL_NAME = config.get("llm", {}).get("model", "gemini-3.1-flash-lite")
# APIが詰まって無期限にブロックし続けるのを防ぐためのタイムアウト（秒）
TIMEOUT_SECONDS = config.get("llm", {}).get("timeout_seconds", 15)

API_KEY_ENV = "GEMINI_API_KEY"


# APIキーを環境変数から取得する。未設定なら None を返す
def get_api_key():
    return os.environ.get(API_KEY_ENV)

# Gemini APIを呼び出してファイル名の候補を取得する
def get_filename_candidates(ocr_text: str, prompt_template: str) -> list:
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    api_key = get_api_key()

    if not api_key:
        print("エラー: APIキーが設定されていません。(.envファイルを確認してください)")
        return None

    client = genai.Client(api_key=api_key)
    
    if not ocr_text.strip():
        return None

    system_instruction = f"""
    {prompt_template}
    
    【本日の日付】
    {today_str}
    
    【出力形式の絶対ルール】
    結果は必ず以下の形式のJSONオブジェクトで出力してください。Markdownのコードブロックは含めず、純粋なJSONデータのみを出力してください。
    {{
        "candidates": [
            "候補1（本命）",
            "候補2（少し短い版など）",
            "候補3（別カテゴリの可能性）"
        ]
    }}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=f"【OCRテキスト】\n{ocr_text}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.2,
                # ネットワーク不調時に無期限でブロックし、ファイルがリネーム待ちのまま
                # 固まってしまうのを防ぐためのタイムアウト設定
                http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000),
            ),
        )
        data = json.loads(response.text)
        return data.get("candidates")
        
    except Exception as e:
        print(f"Gemini APIエラー: {e}")
        # エラーが起きたら None を返して main.py に知らせる
        return None

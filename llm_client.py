import os
import json
from datetime import datetime
from google import genai
from google.genai import types


API_KEY_ENV = "GEMINI_API_KEY"


# APIキーを環境変数から取得する。未設定なら None を返す
def get_api_key():
    return os.environ.get(API_KEY_ENV)

# Gemini APIを呼び出してファイル名の候補を取得する。
# モデル名とタイムアウトは設定ファイルの値を main.py から受け取る
def get_filename_candidates(
    ocr_text: str, prompt_template: str, model: str, timeout_seconds: int
) -> list:
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
            model=model,
            contents=f"【OCRテキスト】\n{ocr_text}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.2,
                # ネットワーク不調時に無期限でブロックし、ファイルがリネーム待ちのまま
                # 固まってしまうのを防ぐためのタイムアウト設定
                http_options=types.HttpOptions(timeout=timeout_seconds * 1000),
            ),
        )
        data = json.loads(response.text)
        return data.get("candidates")
        
    except Exception as e:
        print(f"Gemini APIエラー: {e}")
        # エラーが起きたら None を返して main.py に知らせる
        return None

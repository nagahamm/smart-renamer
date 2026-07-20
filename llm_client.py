import os
import json
from datetime import datetime
from google import genai
from google.genai import types

def get_filename_candidates(ocr_text: str, prompt_template: str) -> list:
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 環境変数からAPIキーを取得
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("エラー: APIキーが設定されていません。(.envファイルを確認してください)")
        return [f"{today_str}__NoAPIKey", "Error_1", "Error_2"]

    client = genai.Client(api_key=api_key)
    
    if not ocr_text.strip():
        return [f"{today_str}__NoText_Screenshot", f"{today_str}__Screenshot", "Screenshot"]

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
            model='gemini-1.5-flash',
            contents=f"【OCRテキスト】\n{ocr_text}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        data = json.loads(response.text)
        return data.get("candidates", [f"{today_str}__ParseError", "Error_1", "Error_2"])
        
    except Exception as e:
        print(f"Gemini APIエラー: {e}")
        return [f"{today_str}__API_Error", "API_Error_1", "API_Error_2"]

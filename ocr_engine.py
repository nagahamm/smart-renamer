import os
import objc
import Foundation
import Vision
import Quartz

def extract_text(image_path: str) -> str:
    if not os.path.exists(image_path):
        return ""

    # このスクリプトにはCocoaのイベントループが無く、通常のアプリのように
    # オートリリースプールが自動で drain されない。プールで明示的に囲むことで、
    # NSURL/VNImageRequestHandlerが掴んだファイルハンドルを含む一時オブジェクトを
    # この関数を抜けた時点で確実に解放する。
    with objc.autorelease_pool():
        url = Foundation.NSURL.fileURLWithPath_(image_path)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setRecognitionLanguages_(["ja-JP", "en-US"])

        success, error = handler.performRequests_error_([request], None)
        if not success:
            return ""

        results = request.results()
        if not results:
            return ""

        extracted_text = []
        for observation in results:
            candidate = observation.topCandidates_(1).firstObject()
            if candidate:
                extracted_text.append(candidate.string())

        return "\n".join(extracted_text)

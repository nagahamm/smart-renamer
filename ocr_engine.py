import os
import objc
import Foundation
import Vision
import Quartz

# 対応する画像形式。Vision はいずれもそのまま読める
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".heic")
PDF_EXTENSION = ".pdf"

SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS + (PDF_EXTENSION,)

# ファイル名を決めるには先頭ページだけあれば足りる
PDF_PAGE_INDEX = 0
# PDFを画像化する際の拡大率。OCR精度のため実寸より大きく描画する
PDF_RENDER_SCALE = 2.0


def is_supported(filepath: str) -> bool:
    return filepath.lower().endswith(SUPPORTED_EXTENSIONS)


def extract_text(filepath: str) -> str:
    """画像またはPDFからテキストを取り出す。"""
    if not os.path.exists(filepath):
        return ""

    if filepath.lower().endswith(PDF_EXTENSION):
        return _extract_pdf_text(filepath)

    # このスクリプトにはCocoaのイベントループが無く、通常のアプリのように
    # オートリリースプールが自動で drain されない。プールで明示的に囲むことで、
    # NSURL/VNImageRequestHandlerが掴んだファイルハンドルを含む一時オブジェクトを
    # この関数を抜けた時点で確実に解放する。
    with objc.autorelease_pool():
        url = Foundation.NSURL.fileURLWithPath_(filepath)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
        return _recognize(handler)


def _extract_pdf_text(filepath: str) -> str:
    """PDFはまず埋め込みテキストを試し、無ければ先頭ページを画像化してOCRする。

    領収書や決算資料の大半はテキスト層を持つため、OCRより速く正確に取れる。
    テキスト層が無いスキャンPDFのみレンダリングに回す。
    """
    with objc.autorelease_pool():
        page = _first_pdf_page(filepath)
        if page is None:
            return ""

        text = page.string()
        if text and text.strip():
            return text.strip()

        cg_image = _render_pdf_page(page)
        if cg_image is None:
            return ""

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            cg_image, None
        )
        return _recognize(handler)


def _first_pdf_page(filepath: str):
    url = Foundation.NSURL.fileURLWithPath_(filepath)
    document = Quartz.PDFDocument.alloc().initWithURL_(url)
    if document is None or document.pageCount() <= PDF_PAGE_INDEX:
        return None
    return document.pageAt_(PDF_PAGE_INDEX)


def _render_pdf_page(page):
    """PDFのページをCGImageに描画する。Visionは画像しか受け取れないため。"""
    bounds = page.boundsForBox_(Quartz.kPDFDisplayBoxMediaBox)
    size = Foundation.NSMakeSize(
        bounds.size.width * PDF_RENDER_SCALE,
        bounds.size.height * PDF_RENDER_SCALE,
    )
    if size.width < 1 or size.height < 1:
        return None

    image = page.thumbnailOfSize_forBox_(size, Quartz.kPDFDisplayBoxMediaBox)
    if image is None:
        return None

    # CGImageForProposedRect: の第1引数は in/out のため、PyObjCでは
    # (CGImage, rect) のタプルで返ることがある
    result = image.CGImageForProposedRect_context_hints_(None, None, None)
    return result[0] if isinstance(result, tuple) else result


def _recognize(handler) -> str:
    """VNImageRequestHandler に文字認識をかけ、結果を改行区切りで返す。"""
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

import io

from pypdf import PdfReader

from core.parser.base import DocumentParser


class PdfParser(DocumentParser):
    """PDF 원본을 페이지별 텍스트로 추출해 개행으로 연결한다.

    표/이미지 구조 보존은 ADR-0013 §6 후속. 현재는 텍스트 추출 수준.
    """

    def parse(self, raw: bytes) -> str:
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

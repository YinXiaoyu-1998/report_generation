#!/usr/bin/env python3
"""
Report generation script using LLM (Gemini or Qwen).
LLM outputs HTML; we convert to PDF with WeasyPrint (images, styling, backgrounds).
References: images (embedded in output) and optional PDFs (structure/layout examples for Gemini).
Outputs: output/response.txt (raw LLM output), output/report.html, output/generated.pdf.

To switch models: set MODEL_PROVIDER env var to 'gemini' or 'qwen'.
API keys: GEMINI_API_KEY, DASHSCOPE_API_KEY (for Qwen)
"""

import argparse
import logging
import re
import shutil
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

load_dotenv()

# --- Model configuration (easy to add more providers) ---
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "gemini").lower()

# Default prompt when none provided - instructs LLM to output HTML in Chinese
# {customer_name} is filled when building the prompt
DEFAULT_PROMPT_BASE = """请生成一份完整、合法的 HTML 格式专业报告。
要求：
- 全文使用中文撰写（标题、段落、图表说明等所有可见文字均为中文）
- 输出完整的 HTML5 文档：包含 <!DOCTYPE html>、<html>、<head>、<body>
- 在 <style> 块中使用内联 CSS 控制版式：字体、背景、布局、边距
- 用标题、段落、小节组织内容，结构清晰
- 便于打印和转为 PDF
项目背景：这是一个选址报告，为名为{customer_name}的商家客户寻找的商铺位置的分析。商家的需求如下（注意，这些需求不必加入到报告中）:
{customer_requirement}
目标商铺详情（供报告参考，请适当融入报告内容）：
{shop_detail}
报告可以包括如下内容，如能搜索到相关信息，请尽可能多的包含：
1. 项目基础信息：商场名称、商业体量、运营年限、商圈定位、周边房价、交通配套（地铁/公交/自驾）；

2. 客流数据：核心辐射区人口、常驻人口密度、商场日均客流；

3. 客群数据：三类客群名称、占比、年龄/身份、消费特征；

4. 铺位信息：所在楼层/区域、业态定位、紧邻配套、铺位面积；

5. 竞争信息：已入驻知名餐饮品牌、商圈竞争特征；

6. 各项评分：区域匹配度、客流匹配度、客群契合度、竞争格局评分，综合匹配度（由前四项综合得出）；五项评分都按照百分制打分，应各自带有一个分值条。

7. 评估日期：{year}年{month}月
"""

DEFAULT_PROMPT_IMAGES = """
- 你有一批参考图片，这些图片是目标商铺的地址，位置，以及实拍图，店铺门面有可能已经用红框圈出。请按以下路径（相对于输出目录）嵌入到报告中：
{image_refs}
- 在合适位置插入图片（如相关内容左侧、右侧、图集、背景图等），并配中文说明
- 使用 <img src="_report_assets/xxx.ext" alt="中文描述" style="max-width:100%;"> 格式嵌入每张图
"""
IMAGE_DESC_LOCATION = "  - _report_assets/location{ext}：商铺选址位置图（展示商铺所在的地理位置），必须嵌入，并在其右侧插入相关内容分析"
IMAGE_DESC_POSITION = "  - _report_assets/position{ext}：商铺在商场内的相对位置图（仅商场铺位时有，街铺无此图），如有则嵌入，并在其右侧插入相关内容分析"
IMAGE_DESC_PHOTO = "  - _report_assets/photo_{n}{ext}：商铺实景照片（第{ord}张），请在合适位置嵌入并配中文说明。配图中可能有红色方框，那是目标商铺的店面。- 注意图片可以被嵌入到某一小节的左侧，右侧展示与其相关的文字内容。"

DEFAULT_PROMPT_PDF_ATTACHED = """
- 已附带一个PDF 作为版式与结构参考，请严格参考其章节结构、标题层级和整体风格来撰写 HTML 报告。不要将 PDF 嵌入 HTML，仅嵌入上述列出的参考图片。
- 注意，附件PDF仅作为版式与结构参考，请不要在新报告中引用附件PDF中的内容。
- 注意图片可以被嵌入到某一页的一侧，另一侧展示与其相关的文字内容。
"""
DEFAULT_PROMPT_PDF_NOT_ATTACHED = """
- 请按专业报告结构撰写：标题清晰、分节、多级标题、版式统一。
- 不要分页，保持一个流畅的长页阅读体验，各个小节之间以及小节内部不要留下大段空白空间影响阅读体验。
"""

# Supported image extensions (for embedding in HTML)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
# Named reference images: LOCATION (shop location map), POSITION (shop position in mall, optional for street spots)
REFERENCE_IMAGE_NAMES = ("LOCATION", "POSITION")
# PDF allowed as structure/layout example (sent to LLM only, not embedded)
PDF_EXTENSIONS = {".pdf"}

EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _build_pdf_filename(customer_name: str, date: datetime | None = None) -> str:
    """
    Build output PDF filename from customer_name and current date, e.g. '麦当劳_选址报告_20251028.pdf'.
    Falls back to '客户_选址报告_YYYYMMDD.pdf' when name is empty.
    Sanitizes path separators. Date format: YYYYMMDD.
    """
    name = (customer_name or "客户").strip()
    if not name:
        name = "客户"
    for ch in ("/", "\\"):
        name = name.replace(ch, "_")
    if date is None:
        date = datetime.now()
    date_str = date.strftime("%Y%m%d")
    return f"{name}_选址报告_{date_str}.pdf"

def get_reference_images(references_dir: Path) -> list[tuple[str, Path]]:
    """
    Collect LOCATION, POSITION, and PHOTO_0, PHOTO_1, ... images from the references folder.
    Returns list of (role, path) where role is 'location', 'position', or 'photo_0', 'photo_1', ...
    LOCATION: shop location map. POSITION: shop position inside mall (optional). PHOTO_N: shop photos.
    Supports .jpg, .jpeg, .png. Case-insensitive stem (PHOTO_0.jpg, photo_1.PNG, etc.).
    """
    if not references_dir.exists():
        return []
    result: list[tuple[str, Path]] = []
    photo_matches: list[tuple[int, Path]] = []  # (index, path)
    for f in references_dir.iterdir():
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        stem = f.stem.upper()
        if stem == "LOCATION" and not any(r[0] == "location" for r in result):
            result.append(("location", f))
        elif stem == "POSITION" and not any(r[0] == "position" for r in result):
            result.append(("position", f))
        else:
            m = re.match(r"^PHOTO_(\d+)$", stem, re.IGNORECASE)
            if m:
                photo_matches.append((int(m.group(1)), f))
    # Sort location first, position second, then photo_0, photo_1, ...
    result.sort(key=lambda x: (0 if x[0] == "location" else (1 if x[0] == "position" else 2)))
    photo_matches.sort(key=lambda x: x[0])
    for idx, path in photo_matches:
        result.append((f"photo_{idx}", path))
    return result


def get_reference_pdfs(
    references_dir: Path, report_type: str | None = None
) -> list[Path]:
    """
    Collect PDF files from the references folder (structure/layout examples).
    If report_type is 'MALL' or 'STREET', only returns the matching PDF (MALL.pdf or STREET.pdf).
    """
    if not references_dir.exists():
        return []
    if report_type and report_type.upper() in ("MALL", "STREET"):
        pdf_name = f"{report_type.upper()}.pdf"
        pdf_path = references_dir / pdf_name
        return [pdf_path] if pdf_path.is_file() else []
    return sorted(
        f for f in references_dir.iterdir()
        if f.is_file() and f.suffix.lower() in PDF_EXTENSIONS
    )


def read_requirement_file(references_dir: Path) -> str:
    """Read requirement.txt from the references folder. Returns empty string if missing."""
    req_path = references_dir / "requirement.txt"
    if not req_path.is_file():
        return ""
    return req_path.read_text(encoding="utf-8").strip()


def read_shop_detail_file(references_dir: Path) -> str:
    """Read SHOP_DETAIL.txt from the references folder. Returns empty string if missing or empty."""
    detail_path = references_dir / "SHOP_DETAIL.txt"
    if not detail_path.is_file():
        return ""
    return detail_path.read_text(encoding="utf-8").strip()


def _format_image_refs(image_specs: list[tuple[str, str]]) -> str:
    """Build image reference lines for the prompt from (role, filename) list."""
    lines = []
    for role, filename in image_specs:
        ext = Path(filename).suffix
        if role == "location":
            lines.append(IMAGE_DESC_LOCATION.format(ext=ext))
        elif role == "position":
            lines.append(IMAGE_DESC_POSITION.format(ext=ext))
        elif role.startswith("photo_"):
            n = role.replace("photo_", "", 1)
            ord_num = int(n) + 1  # 1-based for display (第1张, 第2张)
            lines.append(IMAGE_DESC_PHOTO.format(n=n, ext=ext, ord=ord_num))
    return "\n".join(lines) if lines else ""


def build_default_prompt(
    image_specs: list[tuple[str, str]],
    has_pdf_example: bool = False,
    pdf_attached: bool = True,
    customer_name: str = "",
    customer_requirement: str = "",
    shop_detail: str = "",
) -> str:
    """Build the default prompt, including image and PDF example instructions."""
    customer_name = customer_name.strip() or "客户"
    customer_requirement = customer_requirement.strip() or "（未提供具体需求）"
    shop_detail = shop_detail.strip() or "（未提供）"
    now = datetime.now()
    prompt = DEFAULT_PROMPT_BASE.format(
        customer_name=customer_name,
        customer_requirement=customer_requirement,
        shop_detail=shop_detail,
        year=now.year,
        month=now.month,
    )
    if image_specs:
        refs = _format_image_refs(image_specs)
        prompt += DEFAULT_PROMPT_IMAGES.format(image_refs=refs)
    if has_pdf_example:
        prompt += (
            DEFAULT_PROMPT_PDF_ATTACHED
            if pdf_attached
            else DEFAULT_PROMPT_PDF_NOT_ATTACHED
        )
    return prompt


def prepare_report_assets(
    image_specs: list[tuple[str, Path]], assets_dir: Path
) -> list[tuple[str, str]]:
    """
    Copy reference images to assets_dir with predictable names.
    Returns list of (role, filename) e.g. [("location", "location.jpg"), ("position", "position.png")].
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    result: list[tuple[str, str]] = []
    for role, src in image_specs:
        ext = src.suffix.lower()
        dst_name = f"{role}{ext}"
        dst = assets_dir / dst_name
        shutil.copy2(src, dst)
        result.append((role, dst_name))
    return result


def call_gemini(
    prompt: str,
    image_paths: list[Path],
    pdf_paths: list[Path],
    api_key: str,
    model_name: str,
) -> str:
    """Call Gemini API with optional image and PDF inputs (PDFs as structure examples)."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    contents = [prompt]
    for p in image_paths:
        uploaded = genai.upload_file(str(p))
        contents.append(uploaded)
    for p in pdf_paths:
        uploaded = genai.upload_file(str(p), mime_type="application/pdf")
        contents.append(uploaded)

    response = model.generate_content(contents)
    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        # Gemini usage: prompt, candidates, total tokens
        log.info(
            "Gemini tokens - prompt: %s, output: %s, total: %s",
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "total_token_count", None),
        )
    return response.text


def call_qwen(prompt: str, image_paths: list[Path], api_key: str, model_name: str) -> str:
    """Call Qwen API (DashScope) with optional image inputs."""
    import base64

    import dashscope
    from dashscope import MultiModalConversation

    dashscope.api_key = api_key

    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        mime = EXT_TO_MIME.get(p.suffix.lower(), "image/png")
        content.append({"type": "image", "image": f"data:{mime};base64,{b64}"})

    messages = [{"role": "user", "content": content}]
    response = MultiModalConversation.call(model=model_name, messages=messages)
    if response.status_code == 200:
        # Try to log token usage if DashScope returns it
        usage = None
        try:
            usage = getattr(response, "usage", None)
            if usage is None and hasattr(response, "output"):
                usage = getattr(response.output, "usage", None)
        except Exception:  # pragma: no cover - defensive
            usage = None
        if usage is not None:
            # Common DashScope fields: input_tokens, output_tokens, total_tokens
            in_tokens = getattr(usage, "input_tokens", None) or getattr(
                usage, "prompt_tokens", None
            )
            out_tokens = getattr(usage, "output_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
            log.info(
                "Qwen tokens - input: %s, output: %s, total: %s",
                in_tokens,
                out_tokens,
                total_tokens,
            )
        return response.output.choices[0].message.content[0]["text"]
    raise RuntimeError(f"Qwen API error: {response.code} - {response.message}")


def generate_with_llm(
    prompt: str, image_paths: list[Path], pdf_paths: list[Path]
) -> str:
    """Route to the configured model provider. PDFs are sent only to Gemini."""
    if MODEL_PROVIDER == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-pro")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set. Add it to .env or set MODEL_PROVIDER to 'qwen'.")
        return call_gemini(prompt, image_paths, pdf_paths, api_key, model_name)
    elif MODEL_PROVIDER == "qwen":
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        model_name = os.getenv("QWEN_MODEL_NAME", "qwen-vl-plus")
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY not set. Add it to .env for Qwen.")
        return call_qwen(prompt, image_paths, api_key, model_name)
    else:
        raise ValueError(
            f"Unknown MODEL_PROVIDER '{MODEL_PROVIDER}'. Use 'gemini' or 'qwen'."
        )


def postprocess_html(raw: str) -> str:
    """
    Extract HTML from LLM output, stripping any leading/trailing commentary.
    Handles: text before ```html ... ```, or raw HTML starting with <!DOCTYPE/<html>.
    """
    text = raw.strip()
    # Find code fence anywhere (LLM may add intro text before ```html)
    fence_open = re.search(r"```(?:html)?\s*\n", text, re.IGNORECASE)
    if fence_open:
        start = fence_open.end()
        fence_close = text.find("```", start)
        if fence_close != -1:
            text = text[start:fence_close].strip()
    else:
        # No fence: try to find where HTML actually starts
        html_start = re.search(
            r"<\s*!?\s*doctype\s+html|<html[\s>]",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if html_start:
            text = text[html_start.start() :].strip()
    # Ensure we have HTML
    if not (
        text.lower().startswith("<!doctype")
        or text.lower().startswith("<html")
        or text.lower().startswith("<?xml")
    ):
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>报告</title></head>
<body><pre style="font-family:serif; white-space:pre-wrap;">{escaped}</pre></body>
</html>"""
    return text


def _strip_html_to_text(html: str) -> str:
    """Extract plain text from HTML for reportlab fallback."""
    import re

    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# new Crop logic.
def _crop_pdf_to_content(pdf_path: Path, padding_pt: float = 14) -> None:
    """
    Crop each PDF page to its visible content bounds, removing trailing white space.
    Uses PyMuPDF; no-op if PyMuPDF is not installed.
    padding_pt: extra margin around content (default 14pt ~ 5mm).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.info("PyMuPDF not installed; skipping PDF crop (pip install pymupdf for trim)")
        return

    doc = fitz.open(str(pdf_path))
    for page in doc:
        bboxes: list[tuple[float, float, float, float]] = []

        # Text blocks
        blocks = page.get_text("dict", clip=page.rect).get("blocks", [])
        for block in blocks:
            if "bbox" in block:
                bboxes.append(tuple(block["bbox"]))

        # Images
        for img in page.get_images(full=True):
            xref = img[0]
            rects = page.get_image_rects(xref)
            for r in rects:
                bboxes.append((r.x0, r.y0, r.x1, r.y1))

        if not bboxes:
            continue

        min_x = min(b[0] for b in bboxes) - padding_pt
        min_y = min(b[1] for b in bboxes) - padding_pt
        max_x = max(b[2] for b in bboxes) + padding_pt
        max_y = max(b[3] for b in bboxes) + padding_pt

        # Clamp to page bounds
        r = page.rect
        rect = fitz.Rect(
            max(0, min_x),
            max(0, min_y),
            min(r.width, max_x),
            min(r.height, max_y),
        )
        page.set_cropbox(rect)

    if doc.can_save_incrementally():
        doc.saveIncr()
    else:
        # Save to temp file, then replace (required when incremental not supported)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        doc.save(tmp_path, garbage=4)
        Path(tmp_path).replace(pdf_path)
    doc.close()
    log.info("PDF cropped to content bounds")


def html_to_pdf(html_file: Path, pdf_path: Path) -> None:
    """
    Convert HTML file to PDF using WeasyPrint, with xhtml2pdf then reportlab fallback.
    base_url is the HTML file's parent so relative image paths resolve.
    """
    base_url = str(html_file.parent)
    html_content = html_file.read_text(encoding="utf-8")

    # One long page (no pagination) - landscape width, very tall height
    # Override page-break rules from LLM HTML (e.g. .page-break { page-break-after: always })
    no_break_css = (
        "* { page-break-after: auto !important; page-break-before: auto !important; "
        "page-break-inside: auto !important; }"
    )
    try:
        from weasyprint import CSS, HTML

        html_obj = HTML(filename=str(html_file), base_url=base_url)
        page_css = CSS(
            string="@page { size: 297mm 10000mm; margin: 1cm; }\n" + no_break_css
        )
        html_obj.write_pdf(str(pdf_path), stylesheets=[page_css])
        log.info("PDF conversion: using WeasyPrint")
        _crop_pdf_to_content(pdf_path)
        return
    except (ImportError, OSError):
        # OSError when WeasyPrint is installed but system libs missing (e.g. libgobject, Pango)
        try:
            from xhtml2pdf import pisa

            import warnings

            warnings.warn(
                "WeasyPrint not usable (not installed or system libs missing; "
                "on macOS: brew install pkg-config cairo pango). Using xhtml2pdf fallback (limited CSS).",
                UserWarning,
            )
            # xhtml2pdf doesn't support custom page size; use landscape A4
            cjk_css = (
                "@page { size: A4 landscape; }\n"
                "body { font-family: 'PingFang SC', 'Microsoft YaHei', "
                "'SimSun', 'Noto Sans CJK SC', 'STSong-Light', serif; }\n"
                + no_break_css
            )
            with open(pdf_path, "wb") as dest:
                pisa.CreatePDF(
                    html_content,
                    dest,
                    encoding="utf-8",
                    path=base_url,
                    default_css=cjk_css,
                )
            log.info("PDF conversion: using xhtml2pdf")
        except Exception:
            # xhtml2pdf not installed, or import/runtime failed (e.g. missing pyhanko)
            import warnings

            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            from reportlab.platypus import SimpleDocTemplate, Paragraph

            warnings.warn(
                "WeasyPrint and xhtml2pdf not available. Using reportlab fallback (text only, no images). "
                "Install xhtml2pdf for better PDFs: pip install xhtml2pdf",
                UserWarning,
            )
            # Register Chinese (Simplified) font so CJK characters render instead of blocks
            try:
                pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                cjk_font_name = "STSong-Light"
            except Exception:
                cjk_font_name = "Helvetica"
            text = _strip_html_to_text(html_content)
            # One long page: landscape width, very tall height (~4m)
            w, _ = landscape(A4)
            doc = SimpleDocTemplate(
                str(pdf_path),
                pagesize=(w, 30000),
                rightMargin=inch,
                leftMargin=inch,
                topMargin=inch,
                bottomMargin=inch,
            )
            styles = getSampleStyleSheet()
            normal_style = styles["Normal"]
            if cjk_font_name != "Helvetica":
                normal_style = ParagraphStyle(
                    name="NormalCJK",
                    parent=normal_style,
                    fontName=cjk_font_name,
                )
            story = []
            for para in text.split("\n\n"):
                para = para.strip()
                if para:
                    story.append(
                        Paragraph(para.replace("\n", "<br/>"), normal_style)
                    )
            doc.build(story)
            log.info("PDF conversion: using reportlab")


def cleanup_temp_outputs(output_dir: Path) -> None:
    """
    Remove temporary artifacts after successful PDF generation:
    - response.txt
    - report.html
    - _report_assets/ directory
    """
    try:
        response_file = output_dir / "response.txt"
        report_html = output_dir / "report.html"
        assets_dir = output_dir / "_report_assets"

        if response_file.exists():
            response_file.unlink()
        if report_html.exists():
            report_html.unlink()
        if assets_dir.exists() and assets_dir.is_dir():
            shutil.rmtree(assets_dir, ignore_errors=True)
    except Exception as exc:  # pragma: no cover - defensive cleanup
        log.info(f"Warning: failed to clean temporary outputs: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a report using LLM (Gemini or Qwen) with optional reference images."
    )
    parser.add_argument(
        "customer_name",
        nargs="?",
        default="",
        help="Customer/brand name for the report (e.g. macdonald). Used in the default prompt.",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        default="",
        help="Text prompt for the LLM (default: built-in HTML report prompt)",
    )
    parser.add_argument(
        "--references-dir",
        "-r",
        default="references",
        help="Folder containing reference images (default: references)",
    )
    parser.add_argument(
        "--report-type",
        "-t",
        choices=["MALL", "STREET"],
        default=None,
        help="Use MALL.pdf or STREET.pdf as structure reference (default: use all PDFs)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="output",
        help="Output directory for response.txt, report.html, generated.pdf (default: output)",
    )
    args = parser.parse_args()

    # Base dir: report_generation/ (script's parent)
    base_dir = Path(__file__).resolve().parent
    references_dir = (base_dir / args.references_dir).resolve()
    output_dir = (base_dir / args.output_dir).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "_report_assets"
    image_specs_raw = get_reference_images(references_dir)
    pdf_paths = get_reference_pdfs(references_dir, report_type=args.report_type)
    image_specs = prepare_report_assets(image_specs_raw, assets_dir) if image_specs_raw else []
    image_paths = [p for _, p in image_specs_raw]
    customer_requirement = read_requirement_file(references_dir)
    shop_detail = read_shop_detail_file(references_dir)

    has_pdf = len(pdf_paths) > 0
    pdf_attached = has_pdf and MODEL_PROVIDER == "gemini"
    prompt = args.prompt.strip() or build_default_prompt(
        image_specs,
        has_pdf_example=has_pdf,
        pdf_attached=pdf_attached,
        customer_name=args.customer_name,
        customer_requirement=customer_requirement,
        shop_detail=shop_detail,
    )

    print(f"Model provider: {MODEL_PROVIDER}")
    if args.customer_name:
        print(f"Customer name: {args.customer_name}")
    if args.report_type:
        print(f"Report type (PDF reference): {args.report_type}")
    print(f"Reference images: {len(image_specs_raw)}")
    if image_specs_raw:
        for role, p in image_specs_raw:
            print(f"  - {p.name} ({role})")
    print(f"Reference PDFs (structure examples): {len(pdf_paths)}")
    if pdf_paths:
        for p in pdf_paths:
            print(f"  - {p.name}")

    response_text = generate_with_llm(prompt, image_paths, pdf_paths)

    response_file = output_dir / "response.txt"
    response_file.write_text(response_text, encoding="utf-8")
    print(f"Saved response to {response_file}")

    html_content = postprocess_html(response_text)
    report_html = output_dir / "report.html"
    report_html.write_text(html_content, encoding="utf-8")
    print(f"Saved HTML to {report_html}")

    pdf_file = output_dir / _build_pdf_filename(args.customer_name, datetime.now())
    html_to_pdf(report_html, pdf_file)
    print(f"Saved PDF to {pdf_file}")

    # Clean up temporary files and assets after successful generation
    cleanup_temp_outputs(output_dir)


if __name__ == "__main__":
    main()

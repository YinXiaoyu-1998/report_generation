---
name: report-generation
description: Generate Chinese PDF site-selection reports from reference images and PDFs using the report_generation module and LLMs (Gemini or Qwen). Use when an agent needs to produce, debug, or modify site-selection PDF reports in this project.
---

# Report Generation Skill

## Overview

This skill describes how to operate the `report_generation` module in this project.

The module generates **Chinese PDF site-selection reports** for a customer using:

- A local **references** folder (images, PDFs, requirement text)
- An **LLM** (Gemini or Qwen) that outputs HTML
- An **HTML-to-PDF** pipeline (WeasyPrint with fallbacks)

Core files:

- Main script: `report_generation.py`
- Documentation: `README.md`

Agents should **reuse this script** instead of re-implementing the pipeline.

---

## Environment and Dependencies

### Python

- Python **3.10+** is recommended.

### Python packages

Install dependencies from the project root:

```bash
pip install -r requirements.txt
```

Packages include:

- LLM clients: `google-generativeai` (for Gemini), `dashscope` (for Qwen, optional)
- HTML → PDF stack: `weasyprint` (best), `xhtml2pdf`, `reportlab`, `pymupdf` (optional but useful)

### System libraries for WeasyPrint (recommended)

WeasyPrint requires system libraries such as **Pango**, **Cairo**, **GLib**, **Harfbuzz**, etc.

Preferred installation method (from the project root):

```bash
bash setup_weasyprint.sh
```

Behavior of this script:

- Detects the OS:
  - `Darwin` → macOS
  - `Linux` → Linux (apt / dnf / pacman)
- Installs (as appropriate):
  - Python package manager (`python3-pip` / `python-pip`)
  - Pango/Cairo and related libraries for WeasyPrint

If WeasyPrint is not available, the script falls back to `xhtml2pdf`, then to a text-only `reportlab` output.

---

## Configuration (environment variables)

Set environment variables (for example, via a `.env` file in the project root or in `.env`). The script uses `python-dotenv` to load them.

### Model provider

- `MODEL_PROVIDER` (string; default: `gemini`)

Supported values:

- `gemini` — uses Google Gemini via `google.generativeai`
- `qwen` — uses Alibaba Qwen via DashScope

### Gemini configuration

Used when `MODEL_PROVIDER=gemini`:

- **Required**:
  - `GEMINI_API_KEY`
- **Optional**:
  - `GEMINI_MODEL_NAME` (default: `gemini-2.5-pro`)

### Qwen configuration

Used when `MODEL_PROVIDER=qwen`:

- **Required**:
  - `DASHSCOPE_API_KEY`
- **Optional**:
  - `QWEN_MODEL_NAME` (default: `qwen3.5-plus`)

If the required API key is missing, `report_generation.py` will raise a clear `ValueError`.

---

## Inputs: references folder

By default, the script reads inputs from:

- `references/`

Agents may override this via `--references-dir`, but the structure stays the same.

Expected files (case-insensitive stems, typical extensions: `.jpg`, `.jpeg`, `.png`):

- **`LOCATION.(jpg|jpeg|png)`** — **required**
  - Shop location map.
  - Used as a key image; must exist.
- **`POSITION.(jpg|jpeg|png)`** — optional
  - Shop position inside a mall.
- **`PHOTO_N.(jpg|jpeg|png)`** — optional
  - Additional photos, where N is a non-negative integer:
  - Examples: `PHOTO_0.jpg`, `PHOTO_1.png`, etc.
- **`requirement.txt`** — optional but recommended
  - Customer requirements text.
  - Injected into the prompt as `customer_requirement`.
- **`SHOP_DETAIL.txt`** — optional but recommended
  - Description of the shop.
  - Injected into the prompt as `shop_detail`.
- **`MALL.pdf`** / **`STREET.pdf`** — optional
  - Structure/layout example PDFs.
  - Used as layout references when the `--report-type` argument is provided.

### How images are used

The script:

1. Scans the references directory to find `LOCATION`, `POSITION`, and `PHOTO_N` images.
2. Copies them into `output/_report_assets/` with predictable names:
   - `location.ext`
   - `position.ext`
   - `photo_N.ext`
3. Builds prompt lines that describe each image’s role in Chinese.
4. Instructs the LLM to embed the images into the report HTML with Chinese captions.

### How PDFs are used

- PDFs in the references directory are **structure examples only**.
- When using **Gemini**, PDFs are uploaded and provided as layout/style references (not as content to copy).
- When using **Qwen**, PDFs cannot be sent, but the prompt still asks for a professional report structure when PDFs are present.

---

## Running the script

Run commands from the **project root**.

The main entry point is:

```bash
python3 report_generation.py
```

The script arguments (summarized from `argparse`):

- Positional:
  - `customer_name` (optional):
    - The customer/brand name (e.g. `"麦当劳"`).
    - Used in the prompt and in the PDF filename.
- Options:
  - `--report-type`, `-t`:
    - Choices: `MALL`, `STREET`
    - Selects `MALL.pdf` or `STREET.pdf` as the structure example.
    - If omitted, all PDFs in the references folder are used as examples.


### Common invocation patterns

#### Basic run (defaults)

```bash
python report_generation.py
```

- Uses default prompt (Chinese).
- Uses `references/` as the references folder.
- Uses `output/` as the output folder.

#### With customer name and report type

```bash
python report_generation.py "客户名" --report-type MALL
python report_generation.py "客户名" --report-type STREET
```

- Embeds the customer name into the prompt and output PDF filename.
- Uses only the corresponding `MALL.pdf` or `STREET.pdf` as structure example (if present).


---

## Outputs

By default, outputs go to:

- `output/`

On success:

- **Final PDF report**:
  - Filename pattern: `<客户名>_选址报告_YYYYMMDD.pdf`
  - Example: `麦当劳_选址报告_20251028.pdf`
- This is the artifact agents and users should care about.

Intermediate files during the run:

- `response.txt` — raw LLM text output.
- `report.html` — cleaned/normalized HTML used for PDF generation.
- `_report_assets/` — copied reference images used by the HTML.

After successful PDF generation, the script runs `cleanup_temp_outputs`, which:

- Deletes `response.txt`
- Deletes `report.html`
- Deletes the `_report_assets/` directory

Agents should **not assume** these intermediate artifacts exist after a successful run; they are temporary.

---

## Internal behavior (reference for agents)

High-level process in `report_generation.py`:

1. **Collect references**
   - Images via `get_reference_images` and `prepare_report_assets`.
   - PDFs via `get_reference_pdfs`.
   - Text via `read_requirement_file` and `read_shop_detail_file`.
2. **Build prompt**
   - Uses `build_default_prompt` if `--prompt` is not provided.
   - Prompt includes:
     - Customer name.
     - Customer requirements (`requirement.txt`) content.
     - Shop detail (`SHOP_DETAIL.txt`) content.
     - Structured bullet points about what to cover in the report.
     - Image description lines describing each image’s role.
     - Layout/structure instructions, depending on whether PDFs are available and can be attached.
3. **Call the LLM**
   - Uses `generate_with_llm` to choose provider:
     - `gemini` → `call_gemini` (HTML + images + PDFs).
     - `qwen` → `call_qwen` (HTML + images only).
   - Handles token usage logging when available.
4. **Post-process HTML**
   - `postprocess_html`:
     - Extracts HTML from within code fences if present.
     - If no explicit HTML, wraps the text into a minimal valid HTML document.
     - Ensures a valid HTML5 document for PDF generation.
5. **Convert HTML to PDF**
   - `html_to_pdf`:
     - Tries WeasyPrint:
       - Uses a very tall single-page layout (`297mm x 10000mm`).
       - Applies CSS to prevent forced page breaks from the model.
       - If PyMuPDF (`fitz`) is available, auto-crops pages to content bounds.
     - On WeasyPrint failure (ImportError or system libraries missing):
       - Tries `xhtml2pdf` with basic CSS, including CJK-friendly fonts.
     - If that fails:
       - Falls back to `reportlab`:
         - Extracts text from HTML.
         - Generates a long, text-only PDF with a CJK-capable font when available.
6. **Clean up temporary files**
   - `cleanup_temp_outputs` removes `response.txt`, `report.html`, and `_report_assets/` on success.

---

## Troubleshooting

### Missing or incorrect API keys

Symptoms:

- Exceptions from `generate_with_llm`:
  - Missing `GEMINI_API_KEY` when `MODEL_PROVIDER=gemini`.
  - Missing `DASHSCOPE_API_KEY` when `MODEL_PROVIDER=qwen`.

Agent actions:

- Check `MODEL_PROVIDER`.
- Ensure the correct API key variable is set in `.env` or environment.
- Retry the script after setting the key.

### WeasyPrint or system library errors

Symptoms:

- Import errors or `OSError` when importing/using WeasyPrint.
- Errors mentioning `libgobject`, `Pango`, `cairo`, or similar.

Agent actions:

- Run:

  ```bash
  bash setup_weasyprint.sh
  ```

- On macOS, if WeasyPrint still cannot locate Homebrew libraries, consult `README.md` for instructions on setting `DYLD_FALLBACK_LIBRARY_PATH` (Apple Silicon vs Intel).

Even if WeasyPrint fails, the script attempts `xhtml2pdf` and finally `reportlab`. Agents can recommend installing WeasyPrint properly for best layout and styling.

### Missing reference files

Symptoms:

- Warnings about no reference images.
- Report lacks expected images or context.

Agent actions:

- Verify that:
  - A `LOCATION` image exists and is correctly named (`LOCATION.jpg`, `LOCATION.png`, etc.).
  - Optional `POSITION` and `PHOTO_N` images are correctly named.
  - `requirement.txt` and `SHOP_DETAIL.txt` exist and are UTF-8 encoded if used.
- Ensure paths are correct relative to `references/`.

---

## Guidance for agents

**Recommended behavior:**

- **Do:**
  - Use this skill whenever generating or debugging Chinese PDF site-selection reports in this project.
  - Prefer running `report_generation.py` with appropriate arguments instead of re-writing similar code.
  - Help the user:
    - Set up and verify `.env` configuration.
    - Prepare the `references/` folder with correct filenames and formats.
    - Install dependencies using `requirements.txt` and `setup_weasyprint.sh`.
  - Inspect script output and log messages to suggest concrete fixes.

- **Avoid:**
  - Storing or hardcoding secrets (API keys) in source code or committed files.
  - Modifying system-level installation scripts or environment variables without explicit user approval.
  - Re-implementing the HTML-to-PDF pipeline unless specifically requested; instead, rely on the existing tested script.


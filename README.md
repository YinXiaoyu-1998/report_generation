# Report Generation

Generate PDF reports using LLMs (Gemini or Qwen). The LLM outputs HTML (with layout, styling, images); we convert it to PDF using WeasyPrint.

## Prerequisites

- Python 3.10+
- Virtual environment (recommended)

## Installation

**One-liner (system deps + Python deps, including WeasyPrint):**

```bash
bash report_generation/setup_weasyprint.sh
```

Runs from project root; detects macOS (Homebrew) or Linux (apt/dnf/pacman), installs WeasyPrint system libraries and `pip install -r report_generation/requirements.txt`. Uses `.venv` if present.

**Manual (Python only, no WeasyPrint system libs):**

```bash
pip install -r report_generation/requirements.txt
```

### WeasyPrint (optional, for best PDF quality)

WeasyPrint is commented out in `requirements.txt` because it requires system libraries. Without it, the script uses `xhtml2pdf` (limited CSS) or `reportlab` (text only).

**System libraries WeasyPrint needs:** Python ≥ 3.10, **Pango** ≥ 1.44.0 (which brings in Cairo, GLib, GObject, Harfbuzz, Fontconfig, etc.).

#### macOS (Homebrew)

**Option A — use Homebrew’s WeasyPrint (simplest):**

```bash
brew install weasyprint
```

Then use that environment, or uncomment `weasyprint` in `requirements.txt` and rely on the script’s fallback if your venv doesn’t have the libs.

**Option B — use pip in a virtualenv:** Install the system libs, then pip:

```bash
brew install pkg-config cairo pango
pip install weasyprint
```

If you see errors like `cannot load library 'libgobject-2.0-0'`, the venv can’t see Homebrew’s libs. Set:

```bash
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH   # Apple Silicon
# or
export DYLD_FALLBACK_LIBRARY_PATH=/usr/local/lib:$DYLD_FALLBACK_LIBRARY_PATH     # Intel
```

Then run the script again.

#### Linux

**Debian / Ubuntu (≥ 20.04):**

```bash
sudo apt install python3-pip libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0
pip install weasyprint
```

**Fedora (≥ 39):**

```bash
sudo dnf install python3-pip pango
pip install weasyprint
```

**Arch:**

```bash
sudo pacman -S python-pip pango
pip install weasyprint
```

More options (Alpine, Macports, Conda, Windows): [WeasyPrint — First steps](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).

## Environment Setup

Create a `.env` file at the **project root** so it works regardless of where you run the script.  
You can also place it in `report_generation/.env` if you only use this module.

### Gemini (default)

```env
MODEL_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL_NAME=gemini-2.5-pro
```

### Qwen (China-friendly alternative)

```env
MODEL_PROVIDER=qwen
DASHSCOPE_API_KEY=your_dashscope_api_key
QWEN_MODEL_NAME=qwen3.5-plus
```

> **Note:** When using Qwen, install the optional dependency: `pip install dashscope`

## Recommended folder structure

Below is a recommended layout for the `report_generation` module:

```text
report_generation/
├── report_generation.py        # Main entrypoint
├── README.md                   # This documentation
├── requirements.txt            # Python dependencies (LLM + PDF stack)
├── setup_weasyprint.sh         # Helper script to install WeasyPrint + deps
├── .env                        # (optional) Local model keys for this module only
├── references/                 # Input data for a single report
│   ├── requirement.txt         # Customer requirements (injected into prompt)
│   ├── SHOP_DETAIL.txt         # Shop detail text (injected into prompt)
│   ├── LOCATION.jpg            # Required: shop location map
│   ├── POSITION.jpg            # Optional: shop position inside mall
│   ├── MALL.pdf                # Optional: mall report structure example
│   └── STREET.pdf              # Optional: street report structure example
├── resources/
│   └── current_flow/
│       ├── original_prompt.txt # Internal prompt template
│       └── requirements.txt    # Internal flow requirements
├── output/                     # Generated artifacts (git-ignored; kept via .gitkeep)
│   ├── .gitkeep
│   ├── response.txt            # Raw LLM output
│   ├── report.html             # Cleaned HTML used for PDF conversion
│   ├── <客户名>_选址报告_YYYYMMDD.pdf
│   └── _report_assets/         # Copied reference images (location/position/photos)
└── .gitignore                  # Ignores output/, caches, env files, etc.
```

## Usage

### Basic run

```bash
python report_generation/report_generation.py
```

Uses the default prompt (Chinese) and looks for reference images in `report_generation/references/`. The generated report is in Chinese.

### With custom prompt

```bash
python report_generation/report_generation.py -p "请生成一份市场分析 HTML 报告，使用内联 CSS，输出合法 HTML5。"
```

### With custom paths

```bash
python report_generation/report_generation.py -r references -o output
```

All paths are relative to the `report_generation/` folder.

### With report type (MALL vs STREET)

Use `--report-type` to choose which PDF structure reference to use. Both `MALL.pdf` and `STREET.pdf` should be present in the references folder; the script uses only the selected one.

```bash
python report_generation/report_generation.py "客户名" --report-type MALL
python report_generation/report_generation.py "客户名" -t STREET
```

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--prompt` | `-p` | (built-in) | Text prompt for the LLM |
| `--references-dir` | `-r` | `references` | Folder containing reference images, PDFs, and requirement.txt |
| `--report-type` | `-t` | (all PDFs) | Use `MALL.pdf` or `STREET.pdf` as structure reference |
| `--output-dir` | `-o` | `output` | Output directory for response and PDF |

## Output

- **`output/response.txt`** — Raw LLM output (before HTML post-processing, **deleted after successful run**)
- **`output/report.html`** — Processed HTML used for PDF conversion (**deleted after successful run**)
- **`output/<客户名>_选址报告_YYYYMMDD.pdf`** — Final PDF report (with images, styling, backgrounds)
- **`output/_report_assets/`** — Copy of reference images with predictable names (`location.ext`, `position.ext`, `photo_N.ext`, **deleted after successful run**)

All are written under `report_generation/output/` by default (or the folder you pass via `--output-dir`).  
Temporary artifacts (`response.txt`, `report.html`, `_report_assets/`) are removed automatically once the PDF has been generated without error.

## References Folder

Place inputs in `report_generation/references/`:

| File / Type | Purpose |
|-------------|---------|
| **`LOCATION`** (`.jpg` or `.png`) | Shop location map. Required. Named `LOCATION.jpg`, `LOCATION.png`, etc. (case-insensitive). |
| **`POSITION`** (`.jpg` or `.png`) | Shop’s relative position inside a mall. Optional; absent for street spots. Named `POSITION.jpg`, `POSITION.png`, etc. |
| **`MALL.pdf`** / **`STREET.pdf`** | Structure/layout examples. Use `--report-type MALL` or `--report-type STREET` to select which one the LLM should follow. |
| **`requirement.txt`** | Customer requirements. Content is read and injected into the prompt as `customer_requirement`. |

### Reference Images

Place `LOCATION` and optionally `POSITION` images in the references folder:

- **LOCATION** — Shop location map (required). Shows where the available shop is located.
- **POSITION** — Shop’s position inside a mall (optional). Only used for mall spots; omit for street locations.

Files are copied to `output/_report_assets/` as `location.ext` and `position.ext`. The LLM is instructed to embed them with appropriate Chinese captions. Supported formats: `.jpg`, `.jpeg`, `.png`.

### Reference PDFs (structure examples)

- **With `--report-type`:** Only the selected PDF (`MALL.pdf` or `STREET.pdf`) is used.
- **Without `--report-type`:** All PDFs in the folder are used.
- **Gemini:** PDFs are uploaded and sent to the model with the prompt.
- **Qwen:** PDFs are not sent (API limitation). The prompt still asks for a professional report structure when PDFs are present.

PDFs are not embedded in the output; only images are.

### requirement.txt

Place `requirement.txt` in the references folder. Its content is read and included in the prompt as the customer’s requirements. If the file is missing, the prompt uses a placeholder.

## Switching Models

Set `MODEL_PROVIDER` in `.env`:

- `gemini` — Google Gemini (requires VPN outside supported regions)
- `qwen` — Alibaba Qwen via DashScope (works in China)

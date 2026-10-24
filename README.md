<p align="center">
  <img src="assets/cutout-studio-banner.svg" alt="VerityAgent Cutout Studio — a local AI background-removal workspace" width="100%">
</p>

<h1 align="center">VerityAgent Cutout Studio</h1>

<p align="center">
  <strong>Keep the subject. Lose everything else.</strong><br>
  A polished local web app for AI background removal, transparent PNG export, and custom background compositing.
</p>

<p align="center">
  <a href="https://github.com/muhammadsaeed-ai/verityagent-ai-background-remover/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/muhammadsaeed-ai/verityagent-ai-background-remover/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Flask" src="https://img.shields.io/badge/Flask-local%20web%20app-20232A?logo=flask">
  <img alt="AI model" src="https://img.shields.io/badge/AI-rembg%20%2F%20U%C2%B2--Net-75D9AD?labelColor=172720">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-9EF5CE?labelColor=172720">
</p>

Cutout Studio combines a custom HTML/CSS/JavaScript interface with a Python image-processing backend. Drop in a product photo, portrait, or other image; let `rembg` isolate the foreground; then export a transparent PNG or composite the subject over a solid color or another image. The app is designed to run on your own machine: it does not require an API key or a hosted inference account.

## At a glance

- **Three output modes:** transparent background, solid HEX color, or a user-uploaded replacement image.
- **Local AI inference:** `rembg` with the U²-Net model; the model is initialized on the first processing request and reused by the server process.
- **Purpose-built interface:** responsive dark creative studio, drag-and-drop upload, image preview, color presets, result comparison, status feedback, and one-click PNG export.
- **Careful input handling:** checks image content rather than trusting file extensions, caps each uploaded image at 12 MB, and rejects images above 20 megapixels.
- **Original-size PNG output:** retains the processed image dimensions and preserves the alpha channel when transparent mode is selected.
- **Testable API:** a health endpoint and deterministic unit tests that mock inference, so tests do not download model weights.

## The processing architecture

<p align="center">
  <img src="assets/architecture.svg" alt="Cutout Studio architecture from browser interface through Flask validation, rembg U2-Net, Pillow and NumPy to a PNG response" width="100%">
</p>

The browser submits the chosen files and settings to the Flask API. The server validates the upload, normalizes the image with Pillow, runs foreground segmentation through `rembg`, and optionally composites a background. Pillow writes the final PNG; NumPy calculates the percentage of fully transparent pixels for response metadata.

## Get started

### 1. Requirements

- Python **3.10 or newer**
- `pip`
- An internet connection for the first model-weight download
- A modern browser

The app runs on the CPU and does not require a GPU. First-run inference can take longer while the U²-Net weights are downloaded and loaded.

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
git clone https://github.com/muhammadsaeed-ai/verityagent-ai-background-remover.git
cd verityagent-ai-background-remover
py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**macOS / Linux**

```bash
git clone https://github.com/muhammadsaeed-ai/verityagent-ai-background-remover.git
cd verityagent-ai-background-remover
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Start the studio

```bash
python app.py
```

Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser. The server binds to loopback only, so it is not exposed to the local network by default. Stop it with `Ctrl+C`.

## Use the studio

1. **Upload a source image.** Drag it into the source panel or choose a file. PNG, JPG/JPEG, WEBP, BMP, and TIFF are accepted by the server, although browser preview support for TIFF depends on the browser.
2. **Choose a background finish.** Select transparent output, a solid color, or a custom background image.
3. **Process the image.** The first request may take longer while the model is initialized.
4. **Compare and export.** Switch between the original and processed preview, then choose **Export PNG** to save the result.

### Background modes

| Mode | Result |
|---|---|
| Transparent | Foreground on an alpha-enabled canvas; transparent pixels are retained in PNG. |
| Solid color | Foreground composited over a selected HEX color. Includes quick color presets. |
| New image | Foreground composited over an uploaded background, center-cropped to cover the output dimensions. |

## API reference

The web interface uses `POST /api/remove-background`. It accepts `multipart/form-data` and returns a PNG on success or a JSON error object with an appropriate HTTP status on validation failure.

| Field | Required | Description |
|---|---|---|
| `image` | Yes | Source image file; maximum 12 MB. |
| `mode` | No | `transparent` (default), `color`, or `image`. |
| `color` | For `color` mode | Six-digit HEX value such as `#F4F1EB`. |
| `background` | For `image` mode | Replacement background image; maximum 12 MB. |

Example: remove the background and save a transparent PNG.

```bash
curl -f -X POST http://127.0.0.1:5000/api/remove-background \\
  -F "image=@input.png" \\
  -F "mode=transparent" \\
  --output cutout.png
```

Example: composite the foreground over a solid color.

```bash
curl -f -X POST http://127.0.0.1:5000/api/remove-background \\
  -F "image=@input.jpg" \\
  -F "mode=color" \\
  -F "color=#E0F0EA" \\
  --output product-cutout.png
```

`GET /healthz` returns a lightweight JSON health status without loading the segmentation model. Successful image responses include `X-Output-Width`, `X-Output-Height`, `X-Transparent-Pixels`, and `X-Output-Format` headers.

## Tests

Install the development dependency and run the suite:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use generated in-memory images and a mocked segmentation function. They cover the health endpoint, homepage rendering, missing and invalid uploads, transparent output, solid-color compositing, custom-background compositing, validation before inference, and cross-origin request rejection. They do **not** measure segmentation quality or download real model weights.

A GitHub Actions workflow runs the test suite against Python 3.10, 3.11, and 3.12.

## Privacy and safety boundaries

- The server binds to `127.0.0.1:5000` and rejects unexpected host values and cross-origin browser requests.
- Image uploads are processed in memory. The application does not save source images or results into a gallery.
- The `rembg` model weights are cached by the model library on the machine; those weights are separate from uploaded image data.
- Files are checked by decoded format and pixel count. Each source/background file must be no larger than 12 MB and no larger than 20 megapixels.
- Local-first is not a substitute for machine security. Use a trusted device, keep dependencies updated, and do not expose Flask's development server directly to the internet.

## Limitations

Cutout quality depends on the subject, contrast, lighting, and occlusion. Fine hair, glass, motion blur, low contrast, and complex edges may require manual refinement in an image editor. This version processes one source image per request; it does not provide batch processing, manual mask editing, user accounts, or cloud storage.

## Project structure

```text
verityagent-ai-background-remover/
├── app.py                     # Flask routes, upload validation, segmentation and compositing
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Test dependency
├── templates/
│   └── index.html             # Studio interface
├── static/
│   ├── css/styles.css         # Responsive visual system
│   └── js/app.js              # Upload, controls, preview and export
├── assets/
│   ├── cutout-studio-banner.svg
│   └── architecture.svg
├── tests/
│   └── test_app.py
└── .github/workflows/ci.yml
```

## License

MIT. See [LICENSE](LICENSE).

---

<p align="center">
  <strong>Built by <a href="https://github.com/muhammadsaeed-ai">VerityAgent</a></strong><br>
  <sub>Local-first AI tools with thoughtful UX and clear technical boundaries.</sub>
</p>

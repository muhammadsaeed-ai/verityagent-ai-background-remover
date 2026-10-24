# AI Background Remover

**VerityAgent Python AI Mini Projects — Project 04**

Remove an image background with AI, export a transparent PNG, then optionally replace it with a solid color or a custom image.

**Workflow:** Input image → AI background removal → transparent PNG → optional background replacement.

## Features

| Feature | Details |
|---|---|
| AI background removal | Uses the `rembg` U²-Net model. |
| Transparent PNG | Keeps the model-generated alpha channel. |
| Solid color | Composite over a validated `#RRGGBB` color. |
| Custom image | Resize and center-crop a second image to fit. |
| CLI modes | `transparent`, `solid`, and `image`. |
| Helpful errors | Clear messages for invalid files, colors, and output paths. |
| Offline tests | Unit tests mock inference and do not download model weights. |

## Installation

Use Python 3.10 or newer.

```bash
git clone https://github.com/muhammadsaeed-ai/verityagent-ai-background-remover.git
cd verityagent-ai-background-remover
python -m venv .venv
```

Activate the environment:

**Windows Command Prompt**
```bat
.venv\Scripts\activate.bat
```

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

Install packages:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The `rembg[cpu]` extra installs the CPU ONNX Runtime dependency. The first real inference may download model weights. Unit tests do not.

## Usage

Put your images in `sample_images/` or pass a path elsewhere. Supported inputs: JPEG, PNG, WebP, BMP, and TIFF.

### Help

```bash
python app.py --help
```

### Transparent PNG

```bash
python app.py --input sample_images/person.jpg --output outputs/person.png
```

### Solid-color replacement

```bash
python app.py --input sample_images/person.jpg --output outputs/person_blue.png --mode solid --color "#2563EB"
```

Color must be six-digit hexadecimal (`#RRGGBB`). Default: `#FFFFFF`.

### Custom image background

```bash
python app.py --input sample_images/person.jpg --output outputs/person_scene.png --mode image --background sample_images/background.jpg
```

The replacement image is scaled proportionally and center-cropped to the foreground dimensions. Transparent pixels in a replacement background are flattened over white.

If `--output` is omitted, the result is saved as `outputs/<input-name>_no_bg.png`.

## Demo

Screenshots are not bundled yet. Add genuine examples here when available:
- [ ] Original image and transparent PNG preview
- [ ] Solid-color background result
- [ ] Custom image background result

## Project Structure

```text
verityagent-ai-background-remover/
├── app.py
├── background_remover.py
├── config.py
├── requirements.txt
├── .gitignore
├── README.md
├── LICENSE
├── tests/
│   ├── __init__.py
│   └── test_background_remover.py
├── sample_images/
│   └── .gitkeep
└── outputs/
    └── .gitkeep
```

| File | Purpose |
|---|---|
| `app.py` | CLI arguments, mode selection, and terminal progress. |
| `background_remover.py` | Image loading, rembg inference, compositing, validation, and saving. |
| `config.py` | Model choice, defaults, and supported formats. |
| `requirements.txt` | Python dependencies, including the CPU inference runtime extra. |
| `tests/` | Fast tests using mocked model output. |
| `sample_images/` | Source images and optional background images. |
| `outputs/` | Generated results. |
| `LICENSE` | License for this project's files. |

## How It Works

1. Pillow validates and loads the image as RGBA.
2. The image is encoded as PNG bytes for inference.
3. `rembg` runs the configured `u2net` model and generates foreground transparency.
4. The result is normalized to RGBA and checked against the input dimensions.
5. The application keeps the transparency or composites the foreground over a solid/custom background.
6. Pillow saves the result to the requested path.

## Technologies

- **Python 3.10+:** CLI and reusable application logic.
- **rembg:** Background removal using a pretrained segmentation model.
- **Pillow:** Image loading, resizing, compositing, and saving.
- **NumPy:** Efficient solid-color canvas creation.
- **ONNX Runtime:** CPU inference, installed via `rembg[cpu]`.

## Testing

```bash
python -m unittest discover -v
```

Tests use generated images and mocked inference, so no network/model download is required. To verify actual AI inference, install dependencies and run a usage command with a real image. The first run may need internet access to download model weights.

## Limitations

- Results vary with lighting, image quality, hair/fine details, reflections, transparency, and model behavior.
- First inference may download model weights and use disk space.
- Runtime and memory use depend on image dimensions and hardware.
- This is a command-line application, not a web UI or batch-processing interface.
- JPEG cannot preserve alpha; transparent output should be PNG.
- No sample photos or model weights are bundled.

## Future Improvements

Batch processing, a web UI, drag-and-drop, webcam processing, custom segmentation models, background blur, and background presets.

## License

This project's original code and documentation are released under the MIT License; see [LICENSE](LICENSE). That license covers this repository only. Third-party dependencies and pretrained model weights may have their own license and usage terms; review them before redistribution or commercial use.

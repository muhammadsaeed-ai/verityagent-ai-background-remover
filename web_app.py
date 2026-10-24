"""Optional local web studio for the VerityAgent AI Background Remover.

The existing command-line entry point remains app.py. Start this interface with:
    python web_app.py
"""

from __future__ import annotations

import io
import logging
import re

import numpy as np
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

from config import SUPPORTED_INPUT_FORMATS
from background_remover import (
    BackgroundRemoverError,
    load_image,
    parse_hex_color,
    remove_background as perform_removal,
    replace_background_with_image,
    replace_background_with_solid_color,
)

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ALLOWED_HOSTS = {"127.0.0.1:5000", "localhost:5000"}
ALLOWED_ORIGINS = {"http://127.0.0.1:5000", "http://localhost:5000"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("cutout-studio")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES * 2 + 1024 * 1024


def _local_request_is_allowed() -> bool:
    """Restrict web controls to the locally hosted app by default."""
    if request.host.lower() not in ALLOWED_HOSTS:
        return False
    origin = request.headers.get("Origin")
    return not origin or origin.lower() in ALLOWED_ORIGINS


def _read_image_upload(storage, label: str) -> Image.Image:
    """Decode, inspect and bound a multipart image upload."""
    if storage is None or not storage.filename:
        raise ValueError(f"Choose a {label} image first.")

    raw = storage.stream.read(MAX_UPLOAD_BYTES + 1)
    if not raw:
        raise ValueError(f"The {label} image is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError(f"The {label} image must be 12 MB or smaller.")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            actual_format = (probe.format or "").upper()
            if actual_format not in SUPPORTED_INPUT_FORMATS:
                supported = ", ".join(sorted(SUPPORTED_INPUT_FORMATS))
                raise ValueError(f"Unsupported {label} format. Supported formats: {supported}.")
            probe.verify()

        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width < 1 or opened.height < 1:
                raise ValueError(f"The {label} image has invalid dimensions.")
            if opened.width * opened.height > MAX_PIXELS:
                raise ValueError(f"The {label} image exceeds the 20-megapixel limit.")
            oriented = ImageOps.exif_transpose(opened)
            oriented.load()
            return load_image(oriented)
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(f"The {label} file is not a valid, safely decodable image.") from exc


def _png_response(image: Image.Image):
    """Serialize an in-memory output without writing user images to disk."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    response = send_file(
        buffer,
        mimetype="image/png",
        as_attachment=False,
        download_name="verityagent-cutout.png",
        max_age=0,
    )
    alpha = np.asarray(image.convert("RGBA").getchannel("A"), dtype=np.uint8)
    transparent_pct = np.count_nonzero(alpha == 0) / alpha.size * 100
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Output-Width"] = str(image.width)
    response.headers["X-Output-Height"] = str(image.height)
    response.headers["X-Transparent-Pixels"] = f"{transparent_pct:.1f}"
    response.headers["X-Output-Format"] = "PNG"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    """Health endpoint that does not initialize or download the AI model."""
    return jsonify({"status": "ok", "service": "cutout-studio"})


@app.post("/api/remove-background")
def api_remove_background():
    if not _local_request_is_allowed():
        return jsonify({"error": "Cutout Studio only accepts local requests."}), 403

    try:
        source = _read_image_upload(request.files.get("image"), "source")
        mode = (request.form.get("mode") or "transparent").strip().lower()
        if mode not in {"transparent", "color", "image"}:
            return jsonify({"error": "Choose transparent, color, or image mode."}), 400

        color = (request.form.get("color") or "#F4F1EB").strip()
        replacement = None
        if mode == "color":
            if not HEX_COLOR.fullmatch(color):
                return jsonify({"error": "Enter a valid six-digit HEX background color."}), 400
            # Run the canonical color parser before expensive model inference.
            parse_hex_color(color)
        elif mode == "image":
            replacement = _read_image_upload(request.files.get("background"), "background")

        foreground = perform_removal(source)
        if mode == "color":
            output = replace_background_with_solid_color(foreground, color)
        elif mode == "image":
            assert replacement is not None
            output = replace_background_with_image(foreground, replacement)
        else:
            output = foreground

        return _png_response(output)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except BackgroundRemoverError as exc:
        logger.warning("Background processing was rejected: %s", exc)
        return jsonify({"error": str(exc)}), 422
    except RequestEntityTooLarge:
        return jsonify({"error": "Combined upload is too large. Each image must be at most 12 MB."}), 413
    except Exception:
        logger.exception("Background removal web request failed.")
        return jsonify({"error": "The AI operation failed. Check the server log and try again."}), 500


@app.errorhandler(413)
def payload_too_large(_error):
    return jsonify({"error": "Combined upload is too large. Each image must be at most 12 MB."}), 413


if __name__ == "__main__":
    # Loopback-only by default; do not expose Flask's development server publicly.
    app.run(host="127.0.0.1", port=5000, debug=False)

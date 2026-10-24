from __future__ import annotations

import io
import logging
import re
from functools import lru_cache

import numpy as np
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from rembg import new_session, remove
from werkzeug.exceptions import RequestEntityTooLarge

APP_NAME = "VerityAgent Cutout Studio"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("cutout-studio")

app = Flask(__name__, template_folder="templates", static_folder="static")
# Leave room for the source image and optional background image in one request.
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES * 2 + 1024 * 1024
app.config["MAX_IMAGE_PIXELS"] = MAX_PIXELS


@lru_cache(maxsize=1)
def get_model_session():
    """Load the segmentation model once per server process, on first use."""
    logger.info("Loading the rembg U2-Net model on first request.")
    return new_session("u2net")


def decode_upload(storage, field_label: str) -> tuple[bytes, Image.Image]:
    """Validate an uploaded image's actual format and dimensions."""
    if storage is None or not storage.filename:
        raise ValueError(f"Choose a {field_label} image first.")

    raw = storage.read(MAX_UPLOAD_BYTES + 1)
    if not raw:
        raise ValueError(f"The {field_label} file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError(f"The {field_label} image must be 12 MB or smaller.")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            actual_format = (probe.format or "").upper()
            if actual_format not in ALLOWED_FORMATS:
                raise ValueError(
                    "Unsupported image format. Use PNG, JPG, WEBP, BMP, or TIFF."
                )
            probe.verify()

        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width < 1 or opened.height < 1:
                raise ValueError(f"The {field_label} image has invalid dimensions.")
            if opened.width * opened.height > MAX_PIXELS:
                raise ValueError(
                    f"The {field_label} image is too large. Maximum is 20 megapixels."
                )
            # Honor EXIF rotation and normalize color/alpha before model inference.
            normalized = ImageOps.exif_transpose(opened).convert("RGBA")
            normalized.load()
        return raw, normalized
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(
            f"That {field_label} file could not be decoded as a safe image."
        ) from exc


def as_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def cover_background(background: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize and center-crop a background image to cover the foreground canvas."""
    target_width, target_height = size
    scale = max(target_width / background.width, target_height / background.height)
    resized = background.resize(
        (
            max(1, round(background.width * scale)),
            max(1, round(background.height * scale)),
        ),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop(
        (left, top, left + target_width, top + target_height)
    ).convert("RGBA")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    # This route deliberately does not load the model or download its weights.
    return jsonify({"status": "ok", "service": "cutout-studio"})


@app.post("/api/remove-background")
def remove_background():
    try:
        _, source = decode_upload(request.files.get("image"), "source")
        mode = (request.form.get("mode") or "transparent").strip().lower()
        if mode not in {"transparent", "color", "image"}:
            return jsonify({"error": "Choose a supported background mode."}), 400

        # Feed a normalized PNG to the model so EXIF orientation and decoding
        # behave consistently across the accepted upload formats.
        foreground = remove(as_png_bytes(source), session=get_model_session())
        try:
            with Image.open(io.BytesIO(foreground)) as decoded:
                foreground_rgba = decoded.convert("RGBA")
                foreground_rgba.load()
        except (UnidentifiedImageError, OSError) as exc:
            logger.exception("The segmentation model returned an unreadable image.")
            raise RuntimeError("The image model could not produce a valid result.") from exc

        if mode == "color":
            color = (request.form.get("color") or "#F4F1EB").strip()
            if not HEX_COLOR.fullmatch(color):
                return jsonify({"error": "Enter a valid 6-digit HEX background color."}), 400
            background = Image.new(
                "RGBA", foreground_rgba.size, color.upper()
            )
            result = Image.alpha_composite(background, foreground_rgba)
        elif mode == "image":
            _, uploaded_background = decode_upload(
                request.files.get("background"), "background"
            )
            fitted_background = cover_background(
                uploaded_background, foreground_rgba.size
            )
            result = Image.alpha_composite(fitted_background, foreground_rgba)
        else:
            result = foreground_rgba

        alpha = np.asarray(result.getchannel("A"), dtype=np.uint8)
        fully_transparent_pct = float(np.count_nonzero(alpha == 0) / alpha.size * 100)
        payload = as_png_bytes(result)

        response = send_file(
            io.BytesIO(payload),
            mimetype="image/png",
            as_attachment=False,
            download_name="verityagent-cutout.png",
            max_age=0,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Output-Width"] = str(result.width)
        response.headers["X-Output-Height"] = str(result.height)
        response.headers["X-Transparent-Pixels"] = f"{fully_transparent_pct:.1f}"
        response.headers["X-Output-Format"] = "PNG"
        return response

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RequestEntityTooLarge:
        return jsonify(
            {"error": "The combined upload is too large. Each image must be 12 MB or smaller."}
        ), 413
    except Exception:
        logger.exception("Background removal failed.")
        return jsonify(
            {
                "error": (
                    "The model could not process this image. Check the server log "
                    "for details, then retry with another image."
                )
            }
        ), 500


@app.errorhandler(413)
def too_large(_error):
    return jsonify(
        {"error": "The combined upload is too large. Each image must be 12 MB or smaller."}
    ), 413


if __name__ == "__main__":
    # Local-only by default. Do not expose the development server directly to the internet.
    app.run(host="127.0.0.1", port=5000, debug=False)

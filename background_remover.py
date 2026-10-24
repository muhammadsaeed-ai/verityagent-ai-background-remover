"""Reusable image loading, AI background removal, composition, and saving."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import TypeAlias

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from config import (
    DEFAULT_REMBG_MODEL,
    DEFAULT_SOLID_BACKGROUND_COLOR,
    SUPPORTED_INPUT_FORMATS,
    SUPPORTED_OUTPUT_FORMATS,
)

ImageSource: TypeAlias = Image.Image | str | Path
RGBColor: TypeAlias = tuple[int, int, int]


class BackgroundRemoverError(Exception):
    """Base class for expected application errors."""


class ImageLoadError(BackgroundRemoverError):
    """Raised when an image cannot be loaded or decoded."""


class UnsupportedImageError(ImageLoadError):
    """Raised when an image format is unsupported."""


class BackgroundRemovalError(BackgroundRemoverError):
    """Raised when AI background removal fails."""


class ColorValidationError(BackgroundRemoverError):
    """Raised when a solid color is invalid."""


class OutputSaveError(BackgroundRemoverError):
    """Raised when an output cannot be saved."""


def load_image(source: ImageSource) -> Image.Image:
    """Load a supported image and return an independent RGBA image."""
    if isinstance(source, Image.Image):
        try:
            source.load()
            return source.convert("RGBA")
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ImageLoadError("The supplied image could not be decoded safely.") from exc

    path = Path(source).expanduser()
    if not path.exists():
        raise ImageLoadError(f"Input image not found: '{path}'. Check the path and try again.")
    if not path.is_file():
        raise ImageLoadError(f"Input path is not a file: '{path}'.")

    try:
        with Image.open(path) as opened_image:
            image_format = (opened_image.format or "").upper()
            if image_format not in SUPPORTED_INPUT_FORMATS:
                supported = ", ".join(sorted(SUPPORTED_INPUT_FORMATS))
                raise UnsupportedImageError(
                    f"Unsupported image format '{image_format or 'unknown'}' for '{path}'. "
                    f"Use one of: {supported}."
                )
            opened_image.load()
            return opened_image.convert("RGBA")
    except UnsupportedImageError:
        raise
    except (
        UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError
    ) as exc:
        raise ImageLoadError(
            f"Could not read '{path}' as a valid image. Check that the file is not corrupt "
            "or excessively large."
        ) from exc


@lru_cache(maxsize=1)
def _get_rembg_session() -> object:
    """Create and cache one inference session for the configured model."""
    from rembg import new_session

    return new_session(model_name=DEFAULT_REMBG_MODEL)


def _run_rembg(image_data: bytes) -> object:
    """Call rembg lazily so the other utilities and mocked tests need no model."""
    try:
        from rembg import remove

        return remove(image_data, session=_get_rembg_session())
    except ImportError as exc:
        raise BackgroundRemovalError(
            "The rembg CPU dependencies are missing. Install them with "
            "'python -m pip install -r requirements.txt' and try again."
        ) from exc
    except Exception as exc:
        raise BackgroundRemovalError(
            "AI background removal failed. Check the dependencies and model availability, "
            f"then retry. Details: {exc}"
        ) from exc


def _as_rgba_image(result: object) -> Image.Image:
    """Normalize common rembg result types into a Pillow RGBA image."""
    try:
        if isinstance(result, Image.Image):
            return result.convert("RGBA")
        if isinstance(result, (bytes, bytearray)):
            with Image.open(BytesIO(result)) as image:
                image.load()
                return image.convert("RGBA")
        if isinstance(result, np.ndarray):
            array = result
            if array.dtype != np.uint8:
                array = np.clip(array, 0, 255).astype(np.uint8)
            return Image.fromarray(array).convert("RGBA")
    except (OSError, ValueError, TypeError, Image.DecompressionBombError) as exc:
        raise BackgroundRemovalError("The model returned an invalid image.") from exc
    raise BackgroundRemovalError("The model returned an unsupported result type.")


def remove_background(source: ImageSource) -> Image.Image:
    """Remove a background and return an RGBA Pillow image with alpha preserved."""
    image = load_image(source)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    result = _as_rgba_image(_run_rembg(buffer.getvalue()))
    if result.size != image.size:
        raise BackgroundRemovalError(
            f"The model returned unexpected dimensions ({result.width}x{result.height}); "
            f"expected {image.width}x{image.height}."
        )
    return result


def parse_hex_color(color: str) -> RGBColor:
    """Parse a #RRGGBB color or raise an actionable validation error."""
    if not isinstance(color, str):
        raise ColorValidationError("Color must be a hex string such as '#2563EB'.")
    value = color.strip()
    if len(value) != 7 or not value.startswith("#"):
        raise ColorValidationError(
            f"Invalid color '{color}'. Use '#RRGGBB', for example '#2563EB'."
        )
    try:
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
    except ValueError as exc:
        raise ColorValidationError(
            f"Invalid color '{color}'. Digits must be 0-9 or A-F."
        ) from exc


def replace_background_with_solid_color(
    foreground: Image.Image,
    color: str = DEFAULT_SOLID_BACKGROUND_COLOR,
) -> Image.Image:
    """Composite an RGBA foreground over an opaque solid-color canvas."""
    foreground = foreground.convert("RGBA")
    red, green, blue = parse_hex_color(color)
    canvas = np.empty((foreground.height, foreground.width, 4), dtype=np.uint8)
    canvas[:, :, 0] = red
    canvas[:, :, 1] = green
    canvas[:, :, 2] = blue
    canvas[:, :, 3] = 255
    background = Image.fromarray(canvas, mode="RGBA")
    background.alpha_composite(foreground)
    return background


def replace_background_with_image(
    foreground: Image.Image,
    background_source: ImageSource,
) -> Image.Image:
    """Fit and center-crop the replacement image before compositing the subject.

    If the replacement image itself has transparency, those transparent pixels
    are flattened over white so the finished replacement has an opaque canvas.
    """
    foreground = foreground.convert("RGBA")
    replacement = load_image(background_source)
    white = Image.new("RGBA", replacement.size, (255, 255, 255, 255))
    replacement = Image.alpha_composite(white, replacement)
    fitted = ImageOps.fit(
        replacement,
        foreground.size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    fitted.alpha_composite(foreground)
    return fitted


def save_image(image: Image.Image, output_path: str | Path) -> Path:
    """Save the image, creating parent directories and protecting transparency."""
    destination = Path(output_path).expanduser()
    output_format = SUPPORTED_OUTPUT_FORMATS.get(destination.suffix.lower())
    if output_format is None:
        supported = ", ".join(sorted(SUPPORTED_OUTPUT_FORMATS))
        raise OutputSaveError(
            f"Unsupported output extension '{destination.suffix or '(none)'}'. Use: {supported}."
        )

    output = image
    if output_format == "JPEG":
        transparent = (
            output.mode in ("RGBA", "LA")
            and output.getchannel("A").getextrema() != (255, 255)
        )
        if transparent:
            raise OutputSaveError(
                "JPEG cannot preserve transparency. Use a .png output, or choose "
                "--mode solid/--mode image."
            )
        output = output.convert("RGB")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        output.save(destination, format=output_format)
    except (OSError, ValueError) as exc:
        raise OutputSaveError(
            f"Could not save '{destination}'. Check folder permissions and disk space. "
            f"Details: {exc}"
        ) from exc
    return destination

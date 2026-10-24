"""Default configuration for the VerityAgent background remover."""

from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("outputs")
DEFAULT_REMBG_MODEL = "u2net"
DEFAULT_SOLID_BACKGROUND_COLOR = "#FFFFFF"
SUPPORTED_MODES = ("transparent", "solid", "image")
SUPPORTED_INPUT_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "BMP", "TIFF"})
SUPPORTED_OUTPUT_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
    ".bmp": "BMP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
}

"""Command-line interface for the VerityAgent AI Background Remover."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from background_remover import (
    BackgroundRemoverError,
    remove_background,
    replace_background_with_image,
    replace_background_with_solid_color,
    save_image,
)
from config import DEFAULT_OUTPUT_DIR, DEFAULT_SOLID_BACKGROUND_COLOR, SUPPORTED_MODES


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Remove an image background with AI, export a transparent PNG, or "
            "replace the background with a solid color or another image."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python app.py --input sample_images/person.jpg --output outputs/person.png\n"
            "  python app.py --input sample_images/person.jpg --output outputs/blue.png "
            "--mode solid --color '#2563EB'\n"
            "  python app.py --input sample_images/person.jpg --output outputs/scene.png "
            "--mode image --background sample_images/background.jpg"
        ),
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to the source image.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path; defaults to outputs/<input-name>_no_bg.png.",
    )
    parser.add_argument(
        "--mode", choices=SUPPORTED_MODES, default="transparent",
        help="Output mode: transparent (default), solid, or image.",
    )
    parser.add_argument(
        "--color", default=DEFAULT_SOLID_BACKGROUND_COLOR,
        help=f"Solid background #RRGGBB value (default: {DEFAULT_SOLID_BACKGROUND_COLOR}).",
    )
    parser.add_argument(
        "--background", type=Path,
        help="Replacement image; required when --mode image is selected.",
    )
    return parser


def _default_output_path(input_path: Path) -> Path:
    """Create a portable default path from the input filename."""
    return DEFAULT_OUTPUT_DIR / f"{input_path.stem}_no_bg.png"


def run_application(args: argparse.Namespace) -> Path:
    """Process one image according to parsed command-line options."""
    output_path: Path = args.output or _default_output_path(args.input)

    if args.mode == "transparent" and output_path.suffix.lower() != ".png":
        raise BackgroundRemoverError(
            "Transparent mode must be saved as PNG to preserve alpha. "
            "Choose an output filename ending in '.png'."
        )
    if args.mode == "image" and args.background is None:
        raise BackgroundRemoverError(
            "Image mode requires --background PATH. Provide a replacement image, "
            "or choose --mode transparent or --mode solid."
        )
    if args.mode != "image" and args.background is not None:
        raise BackgroundRemoverError(
            "--background is only used with --mode image. Change the mode or remove this option."
        )

    print(f"Input:  {args.input}")
    print(f"Mode:   {args.mode}")
    print("Loading image and running AI background removal...")
    foreground = remove_background(args.input)

    if args.mode == "solid":
        result = replace_background_with_solid_color(foreground, args.color)
    elif args.mode == "image":
        result = replace_background_with_image(foreground, args.background)
    else:
        result = foreground

    saved_path = save_image(result, output_path)
    print(f"Image size: {result.width} x {result.height}")
    print(f"Saved: {saved_path}")
    print("Done.")
    return saved_path


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and report expected errors without a traceback."""
    args = build_parser().parse_args(argv)
    try:
        run_application(args)
    except BackgroundRemoverError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

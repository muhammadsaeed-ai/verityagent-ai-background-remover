"""Unit tests that use mock model output and never download AI weights."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import contextlib
import io
import unittest
from unittest.mock import patch

from PIL import Image

import background_remover
from app import main
from background_remover import (
    BackgroundRemovalError,
    ColorValidationError,
    ImageLoadError,
    OutputSaveError,
    UnsupportedImageError,
    load_image,
    parse_hex_color,
    remove_background,
    replace_background_with_image,
    replace_background_with_solid_color,
    save_image,
)


def png_bytes(image: Image.Image) -> bytes:
    """Encode a small generated image as PNG bytes."""
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class BackgroundRemoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.input_path = self.root / "input.png"
        Image.new("RGB", (4, 3), (220, 30, 40)).save(self.input_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_image_returns_independent_rgba_copy(self) -> None:
        source = Image.open(self.input_path)
        result = load_image(source)
        source.close()
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.size, (4, 3))
        self.assertEqual(result.getpixel((0, 0)), (220, 30, 40, 255))

    def test_missing_input_file_has_helpful_error(self) -> None:
        with self.assertRaisesRegex(ImageLoadError, "not found"):
            load_image(self.root / "missing.png")

    def test_directory_input_is_rejected(self) -> None:
        with self.assertRaisesRegex(ImageLoadError, "not a file"):
            load_image(self.root)

    def test_unsupported_and_corrupt_images_are_rejected(self) -> None:
        gif_path = self.root / "unsupported.gif"
        Image.new("RGB", (2, 2)).save(gif_path, format="GIF")
        with self.assertRaises(UnsupportedImageError):
            load_image(gif_path)
        corrupt_path = self.root / "corrupt.png"
        corrupt_path.write_bytes(b"not an image")
        with self.assertRaises(ImageLoadError):
            load_image(corrupt_path)

    def test_removal_returns_rgba_and_preserves_model_alpha(self) -> None:
        model = Image.new("RGBA", (4, 3), (10, 20, 30, 120))
        with patch.object(background_remover, "_run_rembg", return_value=png_bytes(model)):
            result = remove_background(self.input_path)
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.size, (4, 3))
        self.assertEqual(result.getpixel((0, 0)), (10, 20, 30, 120))

    def test_wrong_model_dimensions_are_rejected(self) -> None:
        with patch.object(
            background_remover, "_run_rembg",
            return_value=png_bytes(Image.new("RGBA", (1, 1))),
        ):
            with self.assertRaisesRegex(BackgroundRemovalError, "unexpected dimensions"):
                remove_background(self.input_path)

    def test_invalid_model_result_is_reported(self) -> None:
        with patch.object(background_remover, "_run_rembg", return_value=b"bad data"):
            with self.assertRaises(BackgroundRemovalError):
                remove_background(self.input_path)

    def test_color_parsing_and_invalid_values(self) -> None:
        self.assertEqual(parse_hex_color("#2563EB"), (37, 99, 235))
        for value in ("blue", "#FFF", "2563EB", "#12GG00", "#12345678"):
            with self.subTest(value=value):
                with self.assertRaises(ColorValidationError):
                    parse_hex_color(value)

    def test_solid_background_composites_alpha_and_is_opaque(self) -> None:
        foreground = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
        result = replace_background_with_solid_color(foreground, "#0000FF")
        red, _, blue, alpha = result.getpixel((0, 0))
        self.assertEqual(result.size, (2, 2))
        self.assertEqual(result.mode, "RGBA")
        self.assertGreater(red, 0)
        self.assertGreater(blue, 0)
        self.assertEqual(alpha, 255)

    def test_custom_background_fits_canvas_and_composites(self) -> None:
        foreground = Image.new("RGBA", (8, 5), (255, 0, 0, 0))
        background = Image.new("RGB", (3, 20), (0, 0, 255))
        result = replace_background_with_image(foreground, background)
        self.assertEqual(result.size, (8, 5))
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 255, 255))

    def test_transparent_replacement_background_is_flattened(self) -> None:
        foreground = Image.new("RGBA", (2, 2), (255, 0, 0, 0))
        background = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        result = replace_background_with_image(foreground, background)
        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255, 255))

    def test_missing_replacement_background_is_rejected(self) -> None:
        with self.assertRaises(ImageLoadError):
            replace_background_with_image(Image.new("RGBA", (2, 2)), self.root / "missing.jpg")

    def test_save_preserves_alpha_and_creates_parent_folder(self) -> None:
        output_path = self.root / "new-folder" / "output.png"
        save_image(Image.new("RGBA", (3, 2), (1, 2, 3, 100)), output_path)
        with Image.open(output_path) as result:
            self.assertEqual(result.mode, "RGBA")
            self.assertEqual(result.size, (3, 2))
            self.assertEqual(result.getpixel((0, 0)), (1, 2, 3, 100))

    def test_transparency_cannot_be_saved_as_jpeg(self) -> None:
        with self.assertRaises(OutputSaveError):
            save_image(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), self.root / "output.jpg")

    def test_unknown_output_extension_is_rejected(self) -> None:
        with self.assertRaises(OutputSaveError):
            save_image(Image.new("RGB", (1, 1)), self.root / "output.abc")

    def test_cli_rejects_invalid_mode(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["--input", str(self.input_path), "--mode", "invalid"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_cli_rejects_transparent_non_png_output(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main(["--input", str(self.input_path), "--output", str(self.root / "out.jpg")])
        self.assertEqual(result, 2)
        self.assertIn("must be saved as PNG", stderr.getvalue())

    def test_cli_transparent_mode_preserves_alpha(self) -> None:
        model = Image.new("RGBA", (4, 3), (40, 80, 120, 160))
        output_path = self.root / "outputs" / "result.png"
        stdout = io.StringIO()
        with patch.object(background_remover, "_run_rembg", return_value=png_bytes(model)):
            with contextlib.redirect_stdout(stdout):
                result = main([
                    "--input", str(self.input_path),
                    "--output", str(output_path),
                    "--mode", "transparent",
                ])
        self.assertEqual(result, 0)
        with Image.open(output_path) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0)), (40, 80, 120, 160))
        self.assertIn("Done.", stdout.getvalue())

    def test_cli_solid_mode_writes_opaque_png(self) -> None:
        model = Image.new("RGBA", (4, 3), (255, 0, 0, 128))
        output_path = self.root / "outputs" / "solid.png"
        with patch.object(background_remover, "_run_rembg", return_value=png_bytes(model)):
            with contextlib.redirect_stdout(io.StringIO()):
                result = main([
                    "--input", str(self.input_path),
                    "--output", str(output_path),
                    "--mode", "solid",
                    "--color", "#0000FF",
                ])
        self.assertEqual(result, 0)
        with Image.open(output_path) as image:
            self.assertEqual(image.size, (4, 3))
            self.assertEqual(image.getpixel((0, 0))[3], 255)

    def test_cli_image_mode_requires_background(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main(["--input", str(self.input_path), "--mode", "image"])
        self.assertEqual(result, 2)
        self.assertIn("requires --background", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

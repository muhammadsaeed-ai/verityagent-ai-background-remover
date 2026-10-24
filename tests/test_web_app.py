"""Local web interface tests; all AI inference is mocked."""
from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from PIL import Image

import web_app


def png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class CutoutStudioWebTests(unittest.TestCase):
    def setUp(self):
        web_app.app.config.update(TESTING=True)
        self.client = web_app.app.test_client()
        self.source_bytes = png_bytes(Image.new("RGBA", (2, 2), (30, 60, 90, 255)))
        self.foreground = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        self.foreground.putpixel((1, 1), (230, 40, 70, 255))

    def post(self, **fields):
        payload = {"image": (io.BytesIO(self.source_bytes), "source.png"), **fields}
        return self.client.post(
            "/api/remove-background",
            data=payload,
            content_type="multipart/form-data",
            base_url="http://127.0.0.1:5000",
        )

    def test_homepage_and_health(self):
        page = self.client.get("/", base_url="http://127.0.0.1:5000")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Cutout Studio", page.data)
        health = self.client.get("/healthz", base_url="http://127.0.0.1:5000")
        self.assertEqual(health.get_json()["status"], "ok")

    def test_missing_source_is_actionable(self):
        response = self.client.post(
            "/api/remove-background",
            data={"mode": "transparent"},
            content_type="multipart/form-data",
            base_url="http://127.0.0.1:5000",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Choose a source image", response.get_json()["error"])

    def test_transparent_png_result_preserves_alpha(self):
        with patch.object(web_app, "perform_removal", return_value=self.foreground):
            response = self.post(mode="transparent")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.headers["X-Output-Width"], "2")
        with Image.open(io.BytesIO(response.data)) as output:
            self.assertEqual(output.mode, "RGBA")
            self.assertEqual(output.getpixel((0, 0))[3], 0)
            self.assertEqual(output.getpixel((1, 1)), (230, 40, 70, 255))

    def test_solid_color_is_applied_before_inference_is_exported(self):
        with patch.object(web_app, "perform_removal", return_value=self.foreground):
            response = self.post(mode="color", color="#112233")
        self.assertEqual(response.status_code, 200)
        with Image.open(io.BytesIO(response.data)) as output:
            self.assertEqual(output.getpixel((0, 0)), (17, 34, 51, 255))
            self.assertEqual(output.getpixel((1, 1)), (230, 40, 70, 255))

    def test_custom_background_is_composited(self):
        background = png_bytes(Image.new("RGB", (4, 2), (25, 180, 90)))
        with patch.object(web_app, "perform_removal", return_value=self.foreground):
            response = self.client.post(
                "/api/remove-background",
                data={
                    "image": (io.BytesIO(self.source_bytes), "source.png"),
                    "mode": "image",
                    "background": (io.BytesIO(background), "backdrop.png"),
                },
                content_type="multipart/form-data",
                base_url="http://127.0.0.1:5000",
            )
        self.assertEqual(response.status_code, 200)
        with Image.open(io.BytesIO(response.data)) as output:
            self.assertEqual(output.size, (2, 2))
            self.assertEqual(output.getpixel((0, 0)), (25, 180, 90, 255))

    def test_invalid_color_is_rejected_before_inference(self):
        with patch.object(web_app, "perform_removal", side_effect=AssertionError("must not run")):
            response = self.post(mode="color", color="invalid")
        self.assertEqual(response.status_code, 400)

    def test_cross_origin_request_is_rejected(self):
        response = self.client.post(
            "/api/remove-background",
            data={
                "image": (io.BytesIO(self.source_bytes), "source.png"),
                "mode": "transparent",
            },
            content_type="multipart/form-data",
            base_url="http://127.0.0.1:5000",
            headers={"Origin": "https://untrusted.example"},
        )
        self.assertEqual(response.status_code, 403)

    def test_bad_image_bytes_are_rejected(self):
        with patch.object(web_app, "perform_removal", side_effect=AssertionError("must not run")):
            # Use the same route with malformed content to assert validation occurs before AI.
            result = self.client.post(
                "/api/remove-background",
                data={"image": (io.BytesIO(b"not-an-image"), "broken.png"), "mode": "transparent"},
                content_type="multipart/form-data",
                base_url="http://127.0.0.1:5000",
            )
        self.assertEqual(result.status_code, 400)


if __name__ == "__main__":
    unittest.main()

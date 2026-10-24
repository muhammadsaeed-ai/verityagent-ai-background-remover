from __future__ import annotations

import io

import pytest
from PIL import Image

import app as cutout_app


def image_bytes(image: Image.Image, format_name: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=format_name)
    return buffer.getvalue()


@pytest.fixture()
def client():
    cutout_app.app.config.update(TESTING=True)
    with cutout_app.app.test_client() as test_client:
        yield test_client
    cutout_app.app.config.update(TESTING=False)


@pytest.fixture()
def sample_source() -> bytes:
    return image_bytes(Image.new("RGBA", (2, 2), (30, 60, 90, 255)))


@pytest.fixture()
def sample_foreground() -> bytes:
    image = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    image.putpixel((1, 1), (230, 40, 70, 255))
    return image_bytes(image)


def post_image(client, image_bytes_value: bytes, **form_fields):
    data = {
        "image": (io.BytesIO(image_bytes_value), "source.png"),
        **form_fields,
    }
    return client.post(
        "/api/remove-background",
        data=data,
        content_type="multipart/form-data",
        base_url="http://127.0.0.1:5000",
    )


def mock_model(monkeypatch, foreground_bytes: bytes) -> None:
    def fake_remove(_source_bytes, *, session):
        assert session == "test-session"
        return foreground_bytes

    monkeypatch.setattr(cutout_app, "get_model_session", lambda: "test-session")
    monkeypatch.setattr(cutout_app, "remove", fake_remove)


def test_homepage_renders_studio(client):
    response = client.get("/", base_url="http://127.0.0.1:5000")
    assert response.status_code == 200
    assert b"Cutout Studio" in response.data
    assert b"Output settings" in response.data


def test_health_check_does_not_load_model(client, monkeypatch):
    def unexpected_model_load():
        pytest.fail("Health checks must not initialize the AI model.")

    monkeypatch.setattr(cutout_app, "get_model_session", unexpected_model_load)
    response = client.get("/healthz", base_url="http://127.0.0.1:5000")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "cutout-studio"}


def test_missing_source_returns_actionable_error(client):
    response = client.post(
        "/api/remove-background",
        data={"mode": "transparent"},
        content_type="multipart/form-data",
        base_url="http://127.0.0.1:5000",
    )
    assert response.status_code == 400
    assert "Choose a source image" in response.get_json()["error"]


def test_transparent_mode_preserves_alpha_and_dimensions(
    client, monkeypatch, sample_source, sample_foreground
):
    mock_model(monkeypatch, sample_foreground)
    response = post_image(client, sample_source, mode="transparent")

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Output-Width"] == "2"
    assert response.headers["X-Output-Height"] == "2"
    with Image.open(io.BytesIO(response.data)) as result:
        assert result.mode == "RGBA"
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((1, 1)) == (230, 40, 70, 255)


def test_solid_color_is_composited_behind_foreground(
    client, monkeypatch, sample_source, sample_foreground
):
    mock_model(monkeypatch, sample_foreground)
    response = post_image(
        client, sample_source, mode="color", color="#112233"
    )

    assert response.status_code == 200
    with Image.open(io.BytesIO(response.data)) as result:
        assert result.getpixel((0, 0)) == (17, 34, 51, 255)
        assert result.getpixel((1, 1)) == (230, 40, 70, 255)


def test_custom_background_is_resized_to_output_canvas(
    client, monkeypatch, sample_source, sample_foreground
):
    mock_model(monkeypatch, sample_foreground)
    green_background = image_bytes(Image.new("RGB", (4, 2), (25, 180, 90)))
    response = client.post(
        "/api/remove-background",
        data={
            "image": (io.BytesIO(sample_source), "source.png"),
            "mode": "image",
            "background": (io.BytesIO(green_background), "background.png"),
        },
        content_type="multipart/form-data",
        base_url="http://127.0.0.1:5000",
    )

    assert response.status_code == 200
    with Image.open(io.BytesIO(response.data)) as result:
        assert result.size == (2, 2)
        assert result.getpixel((0, 0)) == (25, 180, 90, 255)
        assert result.getpixel((1, 1)) == (230, 40, 70, 255)


def test_invalid_color_is_rejected_before_model_inference(
    client, monkeypatch, sample_source
):
    def unexpected_inference(*_args, **_kwargs):
        pytest.fail("Invalid color should be rejected before inference.")

    monkeypatch.setattr(cutout_app, "remove", unexpected_inference)
    response = post_image(client, sample_source, mode="color", color="not-a-color")
    assert response.status_code == 400
    assert "valid 6-digit HEX" in response.get_json()["error"]


def test_cross_origin_post_is_rejected(client, sample_source):
    response = client.post(
        "/api/remove-background",
        data={"image": (io.BytesIO(sample_source), "source.png"), "mode": "transparent"},
        content_type="multipart/form-data",
        base_url="http://127.0.0.1:5000",
        headers={"Origin": "https://untrusted.example"},
    )
    assert response.status_code == 403
    assert "Cross-origin" in response.get_json()["error"]


def test_invalid_image_data_is_rejected(client):
    response = post_image(client, b"not actually an image", mode="transparent")
    assert response.status_code == 400
    assert "could not be decoded" in response.get_json()["error"]

"""Tests for uploaded image validation and resource limits."""

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from werkzeug.datastructures import FileStorage

from app import create_app
from services.images import cleanup_saved_images, save_images


def image_bytes(size=(8, 8), image_format="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", size, "white").save(stream, format=image_format)
    return stream.getvalue()


class ImageUploadValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(root / "test.db"),
            "UPLOAD_FOLDER": str(root / "uploads"),
            "THUMB_FOLDER": str(root / "thumbs"),
            "SECRET_KEY": "test-secret",
            "MAX_FILE_MB": 2,
            "MAX_IMAGE_PIXELS": 100,
        })
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        self.context.pop()
        self.temp_dir.cleanup()

    def upload(self, data, filename="photo.png"):
        return FileStorage(stream=io.BytesIO(data), filename=filename)

    def test_rejects_corrupt_image_with_allowed_extension(self):
        saved, errors = save_images([self.upload(b"this is not an image")])

        self.assertEqual(saved, [])
        self.assertTrue(any("valid, complete image" in error for error in errors))
        self.assertEqual(list((Path(self.temp_dir.name) / "uploads").glob("*/*")), [])

    def test_rejects_image_over_pixel_limit_before_saving(self):
        data = image_bytes((11, 10))  # 110 pixels; test limit is 100.
        saved, errors = save_images([self.upload(data)])

        self.assertEqual(saved, [])
        self.assertTrue(any("dimensions are too large" in error for error in errors))
        self.assertEqual(list((Path(self.temp_dir.name) / "uploads").glob("*/*")), [])

    def test_accepts_valid_image_and_creates_thumbnail(self):
        saved, errors = save_images([self.upload(image_bytes())])

        self.assertEqual(errors, [])
        self.assertEqual(len(saved), 1)
        self.assertTrue((Path(self.temp_dir.name) / "uploads" /
                         saved[0]["filename"][:2] / saved[0]["filename"]).is_file())
        self.assertIsNotNone(saved[0]["thumb"])
        cleanup_saved_images(saved)


if __name__ == "__main__":
    unittest.main()

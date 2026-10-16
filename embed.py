"""Shared image-embedding code (DINOv2-small, CPU friendly)."""
import numpy as np
import torch
from PIL import Image, ImageOps
from transformers import AutoImageProcessor, AutoModel

MODEL_NAME = "facebook/dinov2-small"
_proc = None
_model = None


def _load():
    global _proc, _model
    if _model is None:
        _proc = AutoImageProcessor.from_pretrained(MODEL_NAME)
        _model = AutoModel.from_pretrained(MODEL_NAME).eval()
    return _proc, _model


def open_image(src) -> Image.Image:
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)  # phone photos carry rotation in EXIF
    return img.convert("RGB")


@torch.inference_mode()
def embed(images: list[Image.Image]) -> np.ndarray:
    proc, model = _load()
    inputs = proc(images=images, return_tensors="pt")
    out = model(**inputs).pooler_output  # (N, 384)
    out = torch.nn.functional.normalize(out, dim=-1)
    return out.cpu().numpy()

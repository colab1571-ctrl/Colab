"""media-svc schemas — re-exported from routers/media.py for test imports."""

from app.routers.media import (
    UploadUrlRequest,
    UploadUrlResponse,
    ConfirmRequest,
    ConfirmResponse,
    SignedUrlResponse,
)

__all__ = [
    "UploadUrlRequest",
    "UploadUrlResponse",
    "ConfirmRequest",
    "ConfirmResponse",
    "SignedUrlResponse",
]

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse


MAX_IMAGE_SIZE = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class GeneralUser:
    user_id: str
    name: str = "Guest"
    email: str = ""

    def upload_image(self) -> None:
        pass

    def request_analysis(self) -> None:
        pass

    def view_result(self) -> None:
        pass

    def send_feedback(self) -> None:
        pass


@dataclass
class Administrator:
    admin_id: str
    name: str = "Administrator"
    email: str = ""

    def view_system_status(self) -> None:
        pass

    def review_feedback(self) -> None:
        pass

    def save_review_result(self) -> None:
        pass


@dataclass
class ImageInput:
    input_id: str
    input_type: str
    created_at: str

    def validate_input(self) -> tuple[bool, str]:
        return True, ""


@dataclass
class UploadedImage(ImageInput):
    file_name: str
    file_type: str
    file_size: int
    file_bytes: bytes

    def validate_file_format(self) -> tuple[bool, str]:
        extension = _extension_from_name(self.file_name)
        if extension not in SUPPORTED_EXTENSIONS:
            return False, "JPG 또는 PNG 파일만 업로드할 수 있습니다."
        if self.file_type and self.file_type not in SUPPORTED_MIME_TYPES:
            return False, "지원하지 않는 이미지 MIME 타입입니다."
        if extension in {".jpg", ".jpeg"} and not self.file_bytes.startswith(b"\xff\xd8\xff"):
            return False, "JPEG 이미지 파일 형식이 올바르지 않습니다."
        if extension == ".png" and not self.file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return False, "PNG 이미지 파일 형식이 올바르지 않습니다."
        return True, ""

    def validate_file_size(self) -> tuple[bool, str]:
        if self.file_size <= 0:
            return False, "선택한 이미지 파일을 불러올 수 없습니다."
        if self.file_size > MAX_IMAGE_SIZE:
            return False, "이미지 파일 용량은 10MB 이하여야 합니다."
        return True, ""

    def validate_input(self) -> tuple[bool, str]:
        valid, message = self.validate_file_size()
        if not valid:
            return valid, message
        return self.validate_file_format()


@dataclass
class ImageURL(ImageInput):
    url_address: str
    is_accessible: bool = False

    def validate_url_format(self) -> tuple[bool, str]:
        parsed = urlparse(self.url_address)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False, "올바른 이미지 URL을 입력해 주세요."
        extension = _extension_from_name(parsed.path)
        if extension not in SUPPORTED_EXTENSIONS:
            return False, "URL은 JPG 또는 PNG 이미지 주소여야 합니다."
        return True, ""

    def load_image_from_url(self) -> tuple[bool, str]:
        self.is_accessible = True
        return True, ""

    def validate_input(self) -> tuple[bool, str]:
        valid, message = self.validate_url_format()
        if not valid:
            return valid, message
        return self.load_image_from_url()


@dataclass
class AnalysisRequest:
    request_id: str
    image_input: ImageInput
    request_status: str
    requested_at: str

    def update_status(self, status: str) -> None:
        self.request_status = status


@dataclass
class HeatmapEvidence:
    heatmap_id: str
    heatmap_x: int
    heatmap_y: int
    heatmap_size: int
    description: str

    def load_heatmap(self) -> dict[str, int | str]:
        return {
            "heatmap_id": self.heatmap_id,
            "heatmap_x": self.heatmap_x,
            "heatmap_y": self.heatmap_y,
            "heatmap_size": self.heatmap_size,
            "description": self.description,
        }


@dataclass
class AnalysisResult:
    result_id: str
    request_id: str
    ai_probability: float
    result_label: str
    result_summary: str
    completed_at: str
    heatmap: HeatmapEvidence
    model_version: str

    def get_result_summary(self) -> str:
        return self.result_summary


@dataclass
class MisclassificationFeedback:
    feedback_id: str
    result_id: str
    feedback_type: str
    comment: str
    submitted_at: str
    status: str = "검토 대기"

    def register_feedback(self) -> None:
        self.status = "검토 대기"


@dataclass
class FeedbackReview:
    review_id: str
    feedback_id: str
    review_result: str
    admin_comment: str
    reviewed_at: str

    def save_review(self) -> None:
        pass


@dataclass
class SystemStatus:
    daily_request_count: int
    average_processing_time: float
    success_count: int
    failure_count: int
    processing_count: int
    system_state: str

    def get_status_summary(self) -> dict[str, int | float | str]:
        return {
            "daily_request_count": self.daily_request_count,
            "average_processing_time": self.average_processing_time,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "processing_count": self.processing_count,
            "system_state": self.system_state,
        }


def _extension_from_name(file_name: str) -> str:
    from pathlib import PurePosixPath

    return PurePosixPath(file_name).suffix.lower()

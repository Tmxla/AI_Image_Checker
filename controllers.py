import re
from pathlib import Path

from detection_engine import DetectionEngine
from models import (
    AnalysisRequest,
    FeedbackReview,
    ImageURL,
    MisclassificationFeedback,
    UploadedImage,
    new_id,
    utc_now_iso,
)
from storage import SQLiteStorage


class AnalysisController:
    def __init__(self, storage: SQLiteStorage, detection_engine: DetectionEngine, upload_dir: str = "static/uploads"):
        self.storage = storage
        self.detection_engine = detection_engine
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def receive_image_input(self, file_part: dict | None, url_value: str) -> tuple[object | None, str]:
        has_file = bool(file_part and file_part.get("filename") and file_part.get("content"))
        has_url = bool(url_value.strip())
        if not has_file and not has_url:
            return None, "이미지 파일을 업로드하거나 URL을 입력해 주세요."
        if has_file and has_url:
            return None, "이미지 파일과 URL을 동시에 입력할 수 없습니다. 하나의 방식만 선택해 주세요."
        if has_file:
            content = file_part["content"]
            uploaded = UploadedImage(
                input_id=new_id("input"),
                input_type="uploaded_file",
                created_at=utc_now_iso(),
                file_name=file_part["filename"],
                file_type=file_part.get("content_type", ""),
                file_size=len(content),
                file_bytes=content,
            )
            valid, message = uploaded.validate_input()
            return (uploaded, "") if valid else (None, message)
        image_url = ImageURL(
            input_id=new_id("input"),
            input_type="image_url",
            created_at=utc_now_iso(),
            url_address=url_value.strip(),
        )
        valid, message = image_url.validate_input()
        return (image_url, "") if valid else (None, message)

    def create_analysis_request(self, image_input: object) -> AnalysisRequest:
        return AnalysisRequest(
            request_id=new_id("request"),
            image_input=image_input,
            request_status="waiting",
            requested_at=utc_now_iso(),
        )

    def start_detection(self, image_input: object) -> tuple[bool, str, str | None]:
        request = self.create_analysis_request(image_input)
        image_path = None
        image_url = None
        source_name = "URL image"
        source_bytes = None
        source_hint = ""
        try:
            if isinstance(image_input, UploadedImage):
                safe_name = self._safe_file_name(image_input.file_name)
                storage_name = f"{request.request_id}_{safe_name}"
                target_path = self.upload_dir / storage_name
                target_path.write_bytes(image_input.file_bytes)
                image_path = str(target_path)
                source_name = image_input.file_name
                source_bytes = image_input.file_bytes
                source_hint = image_input.file_name
            elif isinstance(image_input, ImageURL):
                image_url = image_input.url_address
                source_name = image_input.url_address
                source_hint = image_input.url_address
            else:
                return False, "알 수 없는 이미지 입력입니다.", None

            self.storage.create_analysis_request(request, source_name, image_path, image_url)
            output = self.detection_engine.run_detection(request, source_bytes, source_hint)
            self.storage.save_analysis_result(output.result, output.processing_time_ms)
            return True, "", output.result.result_id
        except Exception as exc:
            self.storage.mark_request_failed(request.request_id, str(exc))
            return False, "분석 요청 처리 중 오류가 발생했습니다.", None

    def show_result(self, result_id: str):
        return self.storage.get_result_detail(result_id)

    def _safe_file_name(self, file_name: str) -> str:
        name = Path(file_name).name
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        return name or "uploaded_image"


class FeedbackController:
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def open_feedback_interface(self, result_id: str):
        return self.storage.get_result_detail(result_id)

    def validate_feedback(self, feedback_type: str, comment: str) -> tuple[bool, str]:
        if feedback_type not in {"real_photo", "ai_generated", "uncertain"}:
            return False, "피드백 유형을 선택해 주세요."
        if len(comment) > 1000:
            return False, "추가 의견은 1000자 이하로 입력해 주세요."
        return True, ""

    def submit_feedback(self, result_id: str, feedback_type: str, comment: str) -> tuple[bool, str]:
        valid, message = self.validate_feedback(feedback_type, comment)
        if not valid:
            return False, message
        if not self.storage.get_result_detail(result_id):
            return False, "분석 결과를 찾을 수 없습니다."
        feedback = MisclassificationFeedback(
            feedback_id=new_id("feedback"),
            result_id=result_id,
            feedback_type=self._label_feedback_type(feedback_type),
            comment=comment.strip(),
            submitted_at=utc_now_iso(),
        )
        self.storage.save_feedback(feedback)
        return True, "오판별 피드백이 접수되었습니다."

    def _label_feedback_type(self, feedback_type: str) -> str:
        if feedback_type == "real_photo":
            return "실제 사진입니다"
        if feedback_type == "uncertain":
            return "판별 결과가 애매합니다"
        return "AI 생성 이미지입니다"


class AdminController:
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def load_system_status(self):
        return self.storage.get_system_status()

    def load_feedback_list(self):
        return self.storage.list_feedbacks()

    def load_feedback_detail(self, feedback_id: str):
        return self.storage.get_feedback_detail(feedback_id)

    def save_feedback_review(self, feedback_id: str, review_result: str, admin_comment: str) -> tuple[bool, str]:
        if review_result not in {"모델 개선 후보", "단순 참고", "검토 제외"}:
            return False, "검토 결과를 선택해 주세요."
        if not self.storage.get_feedback_detail(feedback_id):
            return False, "피드백 정보를 찾을 수 없습니다."
        review = FeedbackReview(
            review_id=new_id("review"),
            feedback_id=feedback_id,
            review_result=review_result,
            admin_comment=admin_comment.strip(),
            reviewed_at=utc_now_iso(),
        )
        self.storage.save_review(review)
        return True, "검토 결과가 저장되었습니다."

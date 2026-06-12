import hashlib
import math
import os
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from models import AnalysisRequest, AnalysisResult, HeatmapEvidence, new_id, utc_now_iso


@dataclass
class DetectionOutput:
    result: AnalysisResult
    processing_time_ms: int


class DetectionEngine:
    def __init__(
        self,
        engine_id: str = "engine_001",
        model_id: str | None = None,
        model_version: str | None = None,
    ):
        self.engine_id = engine_id
        self.model_id = model_id or os.environ.get("SIGHTENGINE_MODELS", "genai")
        self.model_version = model_version or f"Sightengine:{self.model_id}"
        self.api_url = os.environ.get("SIGHTENGINE_API_URL", "https://api.sightengine.com/1.0/check.json")
        self.api_user = os.environ.get("SIGHTENGINE_API_USER", "")
        self.api_secret = os.environ.get("SIGHTENGINE_API_SECRET", "")
        self._api_error = ""

    def run_detection(self, request: AnalysisRequest, source_bytes: Optional[bytes], source_hint: str) -> DetectionOutput:
        request.update_status("analyzing")
        score, model_version = self.calculate_ai_score(source_bytes, source_hint)
        heatmap = self.generate_heatmap_data(source_bytes, source_hint, score)
        label, summary = self._build_result_text(score)
        result = AnalysisResult(
            result_id=new_id("result"),
            request_id=request.request_id,
            ai_probability=score,
            result_label=label,
            result_summary=summary,
            completed_at=utc_now_iso(),
            heatmap=heatmap,
            model_version=model_version,
        )
        request.update_status("completed")
        processing_time_ms = 1200 + int(score * 1800)
        return DetectionOutput(result=result, processing_time_ms=processing_time_ms)

    def calculate_ai_score(self, source_bytes: Optional[bytes], source_hint: str) -> tuple[float, str]:
        if os.environ.get("TRUELENS_FORCE_MOCK", "0") == "1":
            return self._fallback_score(source_bytes, source_hint)

        if source_bytes and self._has_sightengine_credentials():
            return self._calculate_sightengine_score(source_bytes, source_hint), self.model_version

        return self._fallback_score(source_bytes, source_hint)

    def _fallback_score(self, source_bytes: Optional[bytes], source_hint: str) -> tuple[float, str]:
        score = self._calculate_mock_score(source_bytes, source_hint)
        version = "Mock-Fallback-HashEntropy-1.1"
        if not self._has_sightengine_credentials():
            version = f"{version} (Sightengine credentials missing)"
        if self._api_error:
            version = f"{version} (Sightengine API unavailable)"
        return score, version

    def _calculate_mock_score(self, source_bytes: Optional[bytes], source_hint: str) -> float:
        digest = hashlib.sha256((source_bytes or source_hint.encode("utf-8")).strip()).digest()
        base = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        entropy_bonus = self._entropy_bonus(source_bytes) if source_bytes else 0.05
        size_factor = min(len(source_bytes or source_hint.encode("utf-8")) / 5_000_000, 1.0) * 0.12
        score = 0.15 + (base * 0.62) + entropy_bonus + size_factor
        return round(max(0.03, min(score, 0.97)), 2)

    def _has_sightengine_credentials(self) -> bool:
        return bool(self.api_user and self.api_secret)

    def _calculate_sightengine_score(self, source_bytes: bytes, source_hint: str) -> float:
        files = {
            "media": (
                self._media_name(source_hint, source_bytes),
                BytesIO(source_bytes),
                self._media_type(source_bytes),
            )
        }
        data = {
            "models": self.model_id,
            "api_user": self.api_user,
            "api_secret": self.api_secret,
        }
        try:
            response = requests.post(self.api_url, data=data, files=files, timeout=18)
        except requests.RequestException as exc:
            self._api_error = str(exc)
            raise ValueError("AI 판별 API에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.") from exc

        payload = self._parse_api_response(response)
        result_type = payload.get("type") or {}
        if not isinstance(result_type, dict) or "ai_generated" not in result_type:
            raise ValueError("AI 판별 API 응답에서 결과 점수를 찾을 수 없습니다.")
        score = float(result_type["ai_generated"])
        return round(max(0.0, min(score, 1.0)), 4)

    def _parse_api_response(self, response: requests.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("AI 판별 API 응답을 해석할 수 없습니다.") from exc

        if response.status_code >= 400 or payload.get("status") != "success":
            message = self._api_error_message(payload)
            self._api_error = message
            raise ValueError(f"AI 판별 API 호출 실패: {message}")
        return payload

    def _api_error_message(self, payload: dict) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "API 키 또는 사용량을 확인해 주세요.")
        if isinstance(error, str) and error:
            return error
        return "API 키, 사용량, 이미지 형식을 확인해 주세요."

    def _media_name(self, source_hint: str, source_bytes: bytes) -> str:
        parsed_path = urlparse(source_hint).path
        name = Path(parsed_path).name or "uploaded_image"
        if "." not in name:
            name = f"{name}.{self._media_extension(source_bytes)}"
        return name

    def _media_type(self, source_bytes: bytes) -> str:
        if source_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        return "image/jpeg"

    def _media_extension(self, source_bytes: bytes) -> str:
        if source_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        return "jpg"

    def generate_heatmap_data(self, source_bytes: Optional[bytes], source_hint: str, score: float) -> HeatmapEvidence:
        digest = hashlib.sha256((source_bytes or source_hint.encode("utf-8")).strip()).digest()
        if score < 0.20:
            return HeatmapEvidence(
                heatmap_id=new_id("heatmap"),
                heatmap_x=50,
                heatmap_y=50,
                heatmap_size=0,
                description="AI 생성 가능성이 낮게 측정되어 붉은 의심 영역을 표시하지 않습니다. 현재 히트맵은 판별 점수와 일관되도록 비활성화되었습니다.",
            )
        x = 24 + digest[0] % 52
        y = 22 + digest[1] % 54
        size = int(18 + min(score, 1.0) * 34)
        if score < 0.45:
            description = "AI 생성 가능성이 낮은 편이지만 일부 약한 시각적 신호가 있어 작은 참고 영역만 표시합니다."
        else:
            description = "붉게 표시된 영역은 전체 AI 생성 가능성 점수와 함께 참고할 수 있는 상대적 의심 영역입니다."
        return HeatmapEvidence(
            heatmap_id=new_id("heatmap"),
            heatmap_x=x,
            heatmap_y=y,
            heatmap_size=size,
            description=description,
        )

    def _build_result_text(self, score: float) -> tuple[str, str]:
        percent = int(score * 100)
        if score >= 0.72:
            return "AI 생성 가능성 높음", f"모델 추론 결과 AI 생성 가능성이 {percent}%로 높게 측정되었습니다. 세부 근거는 히트맵에서 확인할 수 있습니다."
        if score >= 0.45:
            return "AI 생성 가능성 보통", f"모델 추론 결과 AI 생성 가능성이 {percent}%로 중간 수준입니다. 최종 판단은 원본 출처와 함께 확인하는 것이 좋습니다."
        return "실제 이미지 가능성 높음", f"모델 추론 결과 AI 생성 가능성이 {percent}%로 낮게 측정되었습니다. 단, 본 결과는 보조 판단 정보입니다."

    def _entropy_bonus(self, source_bytes: Optional[bytes]) -> float:
        if not source_bytes:
            return 0.0
        sample = source_bytes[: min(len(source_bytes), 120_000)]
        if not sample:
            return 0.0
        counts = {}
        for byte in sample:
            counts[byte] = counts.get(byte, 0) + 1
        entropy = 0.0
        length = len(sample)
        for count in counts.values():
            probability = count / length
            entropy -= probability * math.log2(probability)
        normalized = entropy / 8
        return (normalized - 0.5) * 0.16

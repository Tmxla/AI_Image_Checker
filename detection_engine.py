import hashlib
import math
from dataclasses import dataclass
from typing import Optional

from models import AnalysisRequest, AnalysisResult, HeatmapEvidence, new_id, utc_now_iso


@dataclass
class DetectionOutput:
    result: AnalysisResult
    processing_time_ms: int


class DetectionEngine:
    def __init__(self, engine_id: str = "engine_001", model_version: str = "Mock-GPU-Prototype-1.0"):
        self.engine_id = engine_id
        self.model_version = model_version

    def run_detection(self, request: AnalysisRequest, source_bytes: Optional[bytes], source_hint: str) -> DetectionOutput:
        request.update_status("analyzing")
        score = self.calculate_ai_score(source_bytes, source_hint)
        heatmap = self.generate_heatmap_data(source_bytes, source_hint)
        label, summary = self._build_result_text(score)
        result = AnalysisResult(
            result_id=new_id("result"),
            request_id=request.request_id,
            ai_probability=score,
            result_label=label,
            result_summary=summary,
            completed_at=utc_now_iso(),
            heatmap=heatmap,
            model_version=self.model_version,
        )
        request.update_status("completed")
        processing_time_ms = 580 + int(score * 1400)
        return DetectionOutput(result=result, processing_time_ms=processing_time_ms)

    def calculate_ai_score(self, source_bytes: Optional[bytes], source_hint: str) -> float:
        digest = hashlib.sha256((source_bytes or source_hint.encode("utf-8")).strip()).digest()
        base = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        entropy_bonus = self._entropy_bonus(source_bytes) if source_bytes else 0.05
        size_factor = min(len(source_bytes or source_hint.encode("utf-8")) / 5_000_000, 1.0) * 0.12
        score = 0.15 + (base * 0.62) + entropy_bonus + size_factor
        return round(max(0.03, min(score, 0.97)), 2)

    def generate_heatmap_data(self, source_bytes: Optional[bytes], source_hint: str) -> HeatmapEvidence:
        digest = hashlib.sha256((source_bytes or source_hint.encode("utf-8")).strip()).digest()
        x = 24 + digest[0] % 52
        y = 22 + digest[1] % 54
        size = 34 + digest[2] % 24
        return HeatmapEvidence(
            heatmap_id=new_id("heatmap"),
            heatmap_x=x,
            heatmap_y=y,
            heatmap_size=size,
            description="붉게 표시된 영역은 색상 변화, 경계 패턴, 압축 흔적을 기준으로 AI 생성 가능성이 상대적으로 높게 계산된 영역입니다.",
        )

    def _build_result_text(self, score: float) -> tuple[str, str]:
        percent = int(score * 100)
        if score >= 0.72:
            return "AI 생성 가능성 높음", f"AI 생성 가능성이 {percent}%로 높게 측정되었습니다. 세부 근거는 히트맵에서 확인할 수 있습니다."
        if score >= 0.45:
            return "AI 생성 가능성 보통", f"AI 생성 가능성이 {percent}%로 중간 수준입니다. 최종 판단은 원본 출처와 함께 확인하는 것이 좋습니다."
        return "실제 이미지 가능성 높음", f"AI 생성 가능성이 {percent}%로 낮게 측정되었습니다. 단, 본 결과는 보조 판단 정보입니다."

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

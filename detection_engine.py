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
        self.backend = os.environ.get("TRUELENS_DETECTOR_BACKEND", "hybrid").strip().lower()
        self.local_model_repo = model_id or os.environ.get("TRUELENS_LOCAL_MODEL_REPO", "onnx-community/ai-image-detection-ONNX")
        self.local_model_file = os.environ.get("TRUELENS_LOCAL_MODEL_FILE", "onnx/model_q4.onnx")
        self.local_model_path = Path(
            os.environ.get("TRUELENS_LOCAL_MODEL_PATH", f"data/models/{Path(self.local_model_file).name}")
        )
        self.model_version = model_version or f"ONNX:{self.local_model_repo}/{self.local_model_file}"
        self.sightengine_model_id = os.environ.get("SIGHTENGINE_MODELS", "genai")
        self.api_url = os.environ.get("SIGHTENGINE_API_URL", "https://api.sightengine.com/1.0/check.json")
        self.api_user = os.environ.get("SIGHTENGINE_API_USER", "")
        self.api_secret = os.environ.get("SIGHTENGINE_API_SECRET", "")
        self._onnx_session = None
        self._onnx_input_name = ""
        self._api_error = ""
        self._local_model_error = ""

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

        local_result = None
        sightengine_result = None
        if source_bytes:
            if self.backend in {"local", "hybrid", "auto"}:
                try:
                    local_result = (self._calculate_local_onnx_score(source_bytes), self.model_version)
                except Exception as exc:
                    self._local_model_error = str(exc)

            if self.backend in {"sightengine", "hybrid", "auto"} and self._has_sightengine_credentials():
                try:
                    sightengine_result = (
                        self._calculate_sightengine_score(source_bytes, source_hint),
                        f"Sightengine:{self.sightengine_model_id}",
                    )
                except Exception as exc:
                    self._api_error = str(exc)

        if self.backend == "local" and local_result:
            return local_result
        if self.backend == "sightengine" and sightengine_result:
            return sightengine_result
        if self.backend == "sightengine" and local_result:
            score, version = local_result
            return score, f"{version} (Sightengine unavailable)"

        if local_result and sightengine_result:
            local_score, local_version = local_result
            sightengine_score, sightengine_version = sightengine_result
            sightengine_weight = self._sightengine_weight(local_score, sightengine_score)
            score = round((local_score * (1.0 - sightengine_weight)) + (sightengine_score * sightengine_weight), 4)
            return score, f"Hybrid:{local_version}+{sightengine_version}"
        if local_result:
            return local_result
        if sightengine_result:
            return sightengine_result

        return self._fallback_score(source_bytes, source_hint)

    def _fallback_score(self, source_bytes: Optional[bytes], source_hint: str) -> tuple[float, str]:
        score = self._calculate_mock_score(source_bytes, source_hint)
        version = "Mock-Fallback-HashEntropy-1.1"
        if self._local_model_error:
            version = f"{version} (local ONNX model unavailable)"
        if not self._has_sightengine_credentials():
            version = f"{version} (Sightengine credentials missing)"
        if self._api_error:
            version = f"{version} (Sightengine API unavailable)"
        return score, version

    def _sightengine_weight(self, local_score: float, sightengine_score: float) -> float:
        if sightengine_score <= 0.15 or sightengine_score >= 0.85:
            return 0.80
        if abs(local_score - sightengine_score) >= 0.40:
            return 0.68
        return 0.55

    def _calculate_mock_score(self, source_bytes: Optional[bytes], source_hint: str) -> float:
        digest = hashlib.sha256((source_bytes or source_hint.encode("utf-8")).strip()).digest()
        base = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        entropy_bonus = self._entropy_bonus(source_bytes) if source_bytes else 0.05
        size_factor = min(len(source_bytes or source_hint.encode("utf-8")) / 5_000_000, 1.0) * 0.12
        score = 0.15 + (base * 0.62) + entropy_bonus + size_factor
        return round(max(0.03, min(score, 0.97)), 2)

    def _has_sightengine_credentials(self) -> bool:
        return bool(self.api_user and self.api_secret)

    def _calculate_local_onnx_score(self, source_bytes: bytes) -> float:
        session, input_name = self._ensure_onnx_session()
        tensor = self._preprocess_for_vit(source_bytes)
        logits = session.run(None, {input_name: tensor})[0][0]
        probabilities = self._softmax(logits)
        fake_score = float(probabilities[1])
        return round(max(0.0, min(fake_score, 1.0)), 4)

    def _ensure_onnx_session(self):
        if self._onnx_session is not None:
            return self._onnx_session, self._onnx_input_name

        import onnxruntime as ort

        model_path = self._ensure_local_model_file()
        options = ort.SessionOptions()
        options.intra_op_num_threads = int(os.environ.get("TRUELENS_ONNX_THREADS", "1"))
        options.inter_op_num_threads = 1
        self._onnx_session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._onnx_input_name = self._onnx_session.get_inputs()[0].name
        return self._onnx_session, self._onnx_input_name

    def _ensure_local_model_file(self) -> Path:
        if self.local_model_path.exists() and self.local_model_path.stat().st_size > 1_000_000:
            return self.local_model_path

        self.local_model_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{self.local_model_repo}/resolve/main/{self.local_model_file}"
        temp_path = self.local_model_path.with_suffix(f"{self.local_model_path.suffix}.tmp")
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with temp_path.open("wb") as target:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        target.write(chunk)
        temp_path.replace(self.local_model_path)
        return self.local_model_path

    def _preprocess_for_vit(self, source_bytes: bytes):
        import numpy as np
        from PIL import Image, ImageOps

        image = Image.open(BytesIO(source_bytes))
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = image.resize((224, 224), Image.Resampling.BILINEAR)
        array = np.asarray(image).astype(np.float32) / 255.0
        array = (array - 0.5) / 0.5
        array = np.transpose(array, (2, 0, 1))
        return array[None, :, :, :]

    def _softmax(self, logits):
        import numpy as np

        values = np.asarray(logits, dtype=np.float32)
        values = values - np.max(values)
        exp_values = np.exp(values)
        return exp_values / np.sum(exp_values)

    def _calculate_sightengine_score(self, source_bytes: bytes, source_hint: str) -> float:
        files = {
            "media": (
                self._media_name(source_hint, source_bytes),
                BytesIO(source_bytes),
                self._media_type(source_bytes),
            )
        }
        data = {
            "models": self.sightengine_model_id,
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
        if score < 0.20:
            return HeatmapEvidence(
                heatmap_id=new_id("heatmap"),
                heatmap_x=50,
                heatmap_y=50,
                heatmap_size=0,
                description="AI 생성 가능성이 낮게 측정되어 붉은 의심 영역을 표시하지 않습니다. 현재 히트맵은 판별 점수와 일관되도록 비활성화되었습니다.",
            )

        localized = self._localize_visual_evidence(source_bytes, score)
        if localized:
            x, y, size, description = localized
            return HeatmapEvidence(
                heatmap_id=new_id("heatmap"),
                heatmap_x=x,
                heatmap_y=y,
                heatmap_size=size,
                description=description,
            )

        digest = hashlib.sha256((source_bytes or source_hint.encode("utf-8")).strip()).digest()
        x = 24 + digest[0] % 52
        y = 22 + digest[1] % 54
        size = int(18 + min(score, 1.0) * 34)
        if score < 0.45:
            description = "AI 생성 가능성이 낮은 편이지만 일부 약한 시각적 신호가 있어 작은 참고 영역만 표시합니다. 원본 이미지 패치 분석을 수행하지 못해 위치 근거는 제한적입니다."
        else:
            description = "붉게 표시된 영역은 전체 AI 생성 가능성 점수와 함께 참고할 수 있는 상대적 의심 영역입니다. 원본 이미지 패치 분석을 수행하지 못해 위치 근거는 제한적입니다."
        return HeatmapEvidence(
            heatmap_id=new_id("heatmap"),
            heatmap_x=x,
            heatmap_y=y,
            heatmap_size=size,
            description=description,
        )

    def _localize_visual_evidence(self, source_bytes: Optional[bytes], score: float) -> tuple[int, int, int, str] | None:
        if not source_bytes:
            return None
        try:
            from PIL import Image, ImageOps

            image = Image.open(BytesIO(source_bytes))
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((260, 260))
        except Exception:
            return None

        width, height = image.size
        if width < 32 or height < 32:
            return None

        gray = image.convert("L")
        gray_pixels = gray.load()
        color_pixels = image.load()
        best_patch = None
        cols, rows = 5, 4
        for row in range(rows):
            for col in range(cols):
                x0 = int(col * width / cols)
                x1 = int((col + 1) * width / cols)
                y0 = int(row * height / rows)
                y1 = int((row + 1) * height / rows)
                metrics = self._patch_visual_metrics(gray_pixels, color_pixels, x0, y0, x1, y1)
                patch_score = (
                    metrics["edge"] * 0.34
                    + metrics["high_frequency"] * 0.34
                    + metrics["color_variance"] * 0.22
                    + metrics["block_boundary"] * 0.10
                )
                if best_patch is None or patch_score > best_patch["score"]:
                    best_patch = {
                        "score": patch_score,
                        "x": (x0 + x1) / 2 / width,
                        "y": (y0 + y1) / 2 / height,
                        "metrics": metrics,
                    }

        if not best_patch:
            return None

        metrics = best_patch["metrics"]
        labels = {
            "edge": "경계 변화",
            "high_frequency": "고주파 질감",
            "color_variance": "색상 분산",
            "block_boundary": "압축 블록 경계",
        }
        strongest = sorted(metrics.items(), key=lambda item: item[1], reverse=True)[:2]
        reasons = ", ".join(f"{labels[key]} {int(value * 100)}%" for key, value in strongest)
        x_percent = int(best_patch["x"] * 100)
        y_percent = int(best_patch["y"] * 100)
        size = int(20 + min(score, 1.0) * 30)
        description = (
            f"붉은 영역은 이미지 패치 분석에서 {reasons} 지표가 상대적으로 높게 측정된 위치입니다. "
            "현재 판별 모델은 위치별 attention map을 직접 제공하지 않으므로, 이 히트맵은 전체 AI 생성 확률을 보조 설명하기 위한 시각적 참고 자료입니다."
        )
        return x_percent, y_percent, size, description

    def _patch_visual_metrics(self, gray_pixels, color_pixels, x0: int, y0: int, x1: int, y1: int) -> dict[str, float]:
        edge_total = 0.0
        high_total = 0.0
        boundary_total = 0.0
        internal_total = 0.0
        sample_count = 0
        boundary_count = 0
        internal_count = 0
        color_values: list[tuple[int, int, int]] = []
        step = 2

        for y in range(max(y0 + 1, 1), max(y0 + 2, y1 - 1), step):
            for x in range(max(x0 + 1, 1), max(x0 + 2, x1 - 1), step):
                center = gray_pixels[x, y]
                left = gray_pixels[x - 1, y]
                right = gray_pixels[x + 1, y]
                up = gray_pixels[x, y - 1]
                down = gray_pixels[x, y + 1]
                dx = abs(center - left)
                dy = abs(center - up)
                edge_total += dx + dy
                high_total += abs((4 * center) - left - right - up - down) / 4
                sample_count += 1
                if x % 8 == 0 or y % 8 == 0:
                    boundary_total += dx + dy
                    boundary_count += 1
                else:
                    internal_total += dx + dy
                    internal_count += 1
                if sample_count % 3 == 0:
                    color_values.append(color_pixels[x, y])

        if sample_count == 0:
            return {"edge": 0.0, "high_frequency": 0.0, "color_variance": 0.0, "block_boundary": 0.0}

        edge = min((edge_total / (sample_count * 2)) / 48, 1.0)
        high_frequency = min((high_total / sample_count) / 42, 1.0)
        color_variance = self._color_variance_score(color_values)
        boundary_avg = boundary_total / max(boundary_count, 1)
        internal_avg = internal_total / max(internal_count, 1)
        block_boundary = min(max((boundary_avg / (internal_avg + 1.0)) - 1.0, 0.0) / 1.5, 1.0)
        return {
            "edge": edge,
            "high_frequency": high_frequency,
            "color_variance": color_variance,
            "block_boundary": block_boundary,
        }

    def _color_variance_score(self, values: list[tuple[int, int, int]]) -> float:
        if not values:
            return 0.0
        count = len(values)
        means = [sum(pixel[channel] for pixel in values) / count for channel in range(3)]
        variances = []
        for channel, mean in enumerate(means):
            variances.append(sum((pixel[channel] - mean) ** 2 for pixel in values) / count)
        stddev = math.sqrt(sum(variances) / 3)
        return min(stddev / 72, 1.0)

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

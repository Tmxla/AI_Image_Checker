# AI_Image_Checker / TrueLens

AI Image Checker(TrueLens)는 이미지 파일 또는 이미지 URL을 입력받아 AI 생성 가능성을 계산하고, 결과/보조 시각 근거/오판별 피드백/관리자 검토 흐름을 제공하는 과제용 구현 프로젝트입니다.

## 실행 방법

실제 AI 이미지 판별은 기본적으로 Hugging Face에 공개된 ONNX 사전학습 모델을 로컬에서 실행합니다. Sightengine API 키가 설정되어 있으면 보조 검증 신호로 함께 사용합니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

실행 후 브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8000
```

서버 종료는 터미널에서 `Ctrl+C`를 누르면 됩니다.

## 구현 기능

- 이미지 파일 업로드 및 드래그 앤 드롭 분석
- 이미지 URL 입력 분석
- 입력값 검증
  - 파일 미입력/동시 입력 방지
  - JPG, PNG 형식 확인
  - 10MB 이하 용량 제한
  - URL 형식 확인
- AnalysisRequest 생성 및 상태 저장
- ONNX 사전학습 모델 기반 AI 생성 확률 계산
- Sightengine AI Image Detection API 보조 검증 연동
- 분석 결과 화면 제공
- 원본 이미지와 보조 시각 근거 비교 화면 제공
  - AI 확률이 낮으면 의심 영역을 표시하지 않음
  - AI 확률이 높으면 이미지 패치의 경계 변화, 고주파 질감, 색상 분산, 압축 블록 경계 지표를 비교하여 참고 영역 표시
- 오판별 피드백 제출
- 관리자 대시보드
  - 관리자 비밀번호 인증
  - 일일 요청 수
  - 평균 처리 시간
  - 성공/실패/처리 중 건수
  - 피드백 목록 조회
  - 피드백 상세 검토 및 결과 저장

## 구현 구조

```text
app.py              # 표준 라이브러리 기반 HTTP 서버 및 라우팅
models.py           # 설계 문서의 Entity 클래스
controllers.py      # AnalysisController, FeedbackController, AdminController
detection_engine.py # DetectionEngine 서비스
storage.py          # SQLite 기반 데이터 저장소
views.py            # HTML 화면 렌더링
static/style.css    # 화면 스타일
static/script.js    # 드래그 앤 드롭, 파일명 표시, 입력 초기화
static/uploads/     # 업로드 이미지 저장 위치
data/truelens.db    # 실행 중 생성되는 SQLite DB
```

## 관리자 로그인

관리자 화면은 비밀번호 인증 후 접근할 수 있습니다. 기본 개발용 비밀번호는 `admin1234`입니다.

비밀번호를 바꾸고 실행하려면 다음처럼 환경변수를 지정합니다.

```bash
TRUELENS_ADMIN_PASSWORD=your-password python3 app.py
```

## Render 배포 설정

Render에서 Web Service를 만들 때 아래 값으로 설정합니다.

```text
Language: Python 3
Branch: main
Root Directory: 비워두기
Build Command: pip install -r requirements.txt
Start Command: python app.py
```

Environment Variables에는 아래 값을 등록합니다.

```text
SIGHTENGINE_API_USER=Sightengine에서 발급받은 API user
SIGHTENGINE_API_SECRET=Sightengine에서 발급받은 API secret
TRUELENS_DETECTOR_BACKEND=hybrid
TRUELENS_ADMIN_PASSWORD=관리자 로그인 비밀번호
TRUELENS_ADMIN_SECRET=긴 랜덤 문자열
```

`app.py`는 Render가 제공하는 `PORT` 환경변수를 읽고 `0.0.0.0`에 바인딩합니다.

## 설계 문서와의 연결

Design 문서의 주요 클래스와 기능 흐름을 코드에 반영했습니다.

- `AnalysisController`: 이미지 입력 수신, 분석 요청 생성, 분석 실행, 결과 조회
- `FeedbackController`: 오판별 피드백 검증 및 저장
- `AdminController`: 시스템 상태 조회, 피드백 목록/상세 조회, 검토 결과 저장
- `DetectionEngine`: AI 생성 확률 계산 및 히트맵 근거 생성
- `AnalysisRequest`, `AnalysisResult`, `HeatmapEvidence`, `MisclassificationFeedback`, `FeedbackReview`, `SystemStatus`: 데이터 관리 객체

## 참고 사항

현재 `DetectionEngine`은 기본적으로 `onnx-community/ai-image-detection-ONNX` 모델의 `onnx/model_q4.onnx` 파일을 실행합니다. 이 모델은 `capcheck/ai-image-detection`의 ONNX 변환본이며, 입력 이미지를 224x224 RGB 텐서로 전처리한 뒤 REAL/FAKE 확률을 계산합니다.

`TRUELENS_DETECTOR_BACKEND` 값은 다음처럼 사용할 수 있습니다.

```text
hybrid      로컬 ONNX 모델과 Sightengine API를 함께 사용합니다. 기본값입니다.
local       로컬 ONNX 모델만 사용합니다.
sightengine Sightengine API만 사용합니다.
```

시각 근거 화면의 붉은 영역은 모델 내부 attention map이 아닙니다. TrueLens는 업로드된 이미지를 로컬에서 패치 단위로 나누어 경계 변화, 고주파 질감, 색상 분산, 압축 블록 경계가 상대적으로 큰 영역을 보조 시각화로 표시합니다. 따라서 이 화면은 최종 판정을 단정하는 근거가 아니라 전체 판별 점수를 이해하기 위한 참고 자료입니다.

의도적으로 mock 모드를 쓰려면 다음처럼 실행합니다.

```bash
TRUELENS_FORCE_MOCK=1 .venv/bin/python app.py
```

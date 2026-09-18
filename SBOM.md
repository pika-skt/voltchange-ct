# 소프트웨어 구성 명세(SBOM)

- 대상 저장소: `voltchange-ct`
- 기준 커밋: `a4dcc8509256ad63f2aa910a0ca62f5f5c43d5d7`
- 작성 기준일: 2026-08-27
- 배포 기준 이미지: `python:3.13.11-slim-bookworm@sha256:20080e807bfc404f8450b185cf0fc95d553462673598549613735f70a5b4d5d0`
- 포함 범위: 최종 컨테이너의 Python 패키지, 이미지 빌드 전용 패키지, 저장소 내 오프라인 학습·검증 도구가 직접 import하는 제3자 라이브러리
- 제외 범위: Python 표준 라이브러리, 베이스 이미지의 Debian 시스템 패키지, 저장소 내부 모듈

| 라이브러리명 | 버전 | 라이선스 | 공식 저장소 URL(GitHub 등) | 사용 목적 및 주요 기능 |
| --- | --- | --- | --- | --- |
| mecab-ko (`pymecab-ko`) | 1.0.2 | BSD-3-Clause 선택 (대안: GPL-2.0-only 또는 LGPL-2.1-only) | https://github.com/NoUnique/pymecab-ko | **런타임·최종 이미지 포함.** MeCab-ko의 Python 바인딩으로, 한국어 프롬프트를 형태소와 품사 단위로 분석한다. `tokenizer_impl/tokenizer.py`에서 하이브리드 토큰을 생성하는 핵심 토크나이저로 사용한다. |
| mecab-ko-dic | 1.0.0 | Apache-2.0 | https://github.com/LuminosoInsight/mecab-ko-dic | **런타임·최종 이미지 포함.** MeCab-ko가 한국어 형태소를 분리하고 품사를 판별하는 데 사용하는 사전 데이터와 설정을 제공한다. `mecab-ko`의 런타임 사전 의존성이다. |
| mmh3 | 5.2.0 | MIT | https://github.com/hajimes/mmh3 | **런타임·최종 이미지 포함.** MurmurHash3 비암호화 해시를 제공한다. `router_impl/blended_gain.py`에서 문자열 특징을 scikit-learn과 호환되는 부호 있는 32비트 해시로 변환하고 1,024개 특징 버킷에 배치하는 데 사용한다. |
| setuptools | 80.9.0 | MIT | https://github.com/pypa/setuptools | **빌드 전용·최종 이미지 미포함.** `--no-build-isolation` 방식으로 런타임 패키지를 설치할 때 Python 패키지 빌드·설치 기반을 제공한다. Docker 빌드의 의존성 단계에서만 설치되며 런타임 단계에서 제거된다. |
| NumPy | 미고정 (호스트 환경 의존) | BSD-3-Clause | https://github.com/numpy/numpy | **오프라인 학습·검증 전용·최종 이미지 미포함.** `tools/export_mecab_blended.py`와 `tools/verify_mecab_training_parity.py`에서 배열 연산, 모델 계수·평균·표준편차 처리 및 결과 비교에 사용한다. |
| SciPy | 미고정 (호스트 환경 의존) | BSD-3-Clause | https://github.com/scipy/scipy | **오프라인 학습 전용·최종 이미지 미포함.** `tools/export_mecab_blended.py`에서 희소 CSR 행렬 생성과 특징 행렬 결합에 사용한다. |
| scikit-learn | 미고정 (호스트 환경 의존) | BSD-3-Clause | https://github.com/scikit-learn/scikit-learn | **오프라인 학습·검증 전용·최종 이미지 미포함.** 특징 해싱, 정규화, 표준화와 Ridge 회귀 학습에 사용하며, 런타임 `mmh3` 해싱 결과와 학습 파이프라인의 일치 여부도 검증한다. |

## 확인 근거

- 고정 런타임 버전: `router_impl/requirements.txt`, `tokenizer_impl/requirements.txt`, `artifact-manifest.json`
- 빌드 전용 버전과 제거 여부: `build-requirements.txt`, `Dockerfile`
- 라이선스와 공식 저장소: `THIRD_PARTY_NOTICES.md` 및 각 프로젝트의 공식 패키지·소스 메타데이터
- 실제 사용처: `tokenizer_impl/tokenizer.py`, `router_impl/blended_gain.py`, `tools/export_mecab_blended.py`, `tools/verify_mecab_training_parity.py`

> 참고: NumPy, SciPy, scikit-learn은 저장소 코드에서 사용하지만 이 저장소의 요구사항 파일에는 버전이 고정되어 있지 않다. 재현 가능한 오프라인 학습·검증 SBOM이 필요하면 해당 세 패키지와 전이 의존성을 별도 lock 파일로 고정해야 한다. 베이스 이미지의 Debian 패키지까지 포함하는 완전한 컨테이너 SBOM은 최종 OCI 이미지를 빌드한 뒤 이미지 스캐너로 생성해야 한다.

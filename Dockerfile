# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13.11-slim-bookworm@sha256:20080e807bfc404f8450b185cf0fc95d553462673598549613735f70a5b4d5d0

FROM ${PYTHON_IMAGE} AS dependencies

ARG ROUTER_IMPL=router_impl
ARG TOKENIZER_IMPL=tokenizer_impl

COPY ${ROUTER_IMPL}/requirements.txt /tmp/router-requirements.txt
COPY ${TOKENIZER_IMPL}/requirements.txt /tmp/tokenizer-requirements.txt

RUN mkdir -p /runtime-deps && \
    python3 -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --no-compile \
      --prefix=/runtime-deps \
      --require-hashes \
      --requirement /tmp/router-requirements.txt \
      --requirement /tmp/tokenizer-requirements.txt

FROM ${PYTHON_IMAGE} AS runtime

ARG ROUTER_IMPL=router_impl
ARG TOKENIZER_IMPL=tokenizer_impl
ARG SOURCE_MANIFEST_SHA256

RUN test "${#SOURCE_MANIFEST_SHA256}" -eq 64 && \
    case "${SOURCE_MANIFEST_SHA256}" in \
      *[!0-9a-f]*) exit 1 ;; \
      *) exit 0 ;; \
    esac

LABEL org.opencontainers.image.licenses="Apache-2.0" \
      io.sktelecom.ossp.source-manifest-sha256="${SOURCE_MANIFEST_SHA256}" \
      io.voltchange.router-implementation="${ROUTER_IMPL}" \
      io.voltchange.tokenizer-implementation="${TOKENIZER_IMPL}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    PYTHONPATH=/opt/router \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1

RUN python3 -m pip uninstall --yes pip setuptools wheel

COPY --from=dependencies /runtime-deps/ /usr/local/
COPY --chown=65532:65532 runtime/ /opt/router/runtime/
COPY --chown=65532:65532 ossp_router/ /opt/router/ossp_router/
COPY --chown=65532:65532 ${ROUTER_IMPL}/ /opt/router/router_impl/
COPY --chown=65532:65532 ${TOKENIZER_IMPL}/ /opt/router/tokenizer_impl/
COPY --chown=65532:65532 LICENSE THIRD_PARTY_NOTICES.md /opt/router/

WORKDIR /opt/router

USER 65532:65532

STOPSIGNAL SIGTERM

ENTRYPOINT ["python3", "-m", "runtime.entrypoint"]

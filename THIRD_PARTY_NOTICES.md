# Third-party notices

The stable adapter and `voltchange`-derived integration code are distributed under
Apache-2.0; see `LICENSE`.

The following files originate from the OSSP 2026 LLM Router Challenge repository
at commit `3cccbf602077a846c13b2cb1356eee1559a631db` and retain their SPDX headers:

- `ossp_router/protocol.py`
- `ossp_router/heuristic.py`
- `ossp_router/__init__.py`
- `ossp_router/resources/__init__.py`
- `ossp_router/resources/routing-policy.v1.json`
- `router_impl/hash_regex.py`
- `router_impl/hash-regex-public.v1.json`
- `tokenizer_impl/tokenizer.py` (tokenization logic extracted from `hash_regex.py`)
- `tests/data/toy-inputs.json`

Those files are Copyright 2026 SK TELECOM CO., LTD. and licensed under
Apache-2.0.

The container base is Docker Official Image
`python:3.13.11-slim-bookworm` pinned to OCI index digest
`sha256:20080e807bfc404f8450b185cf0fc95d553462673598549613735f70a5b4d5d0`.
Python's license text and Debian package copyright records remain present in the
base image. A replacement router is responsible for pinning and documenting every
additional runtime dependency and artifact license.

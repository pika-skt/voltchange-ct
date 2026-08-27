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
- `tests/data/toy-inputs.json`

Those files are Copyright 2026 SK TELECOM CO., LTD. and licensed under
Apache-2.0.

The container base is Docker Official Image
`python:3.13.11-slim-bookworm` pinned to OCI index digest
`sha256:20080e807bfc404f8450b185cf0fc95d553462673598549613735f70a5b4d5d0`.
Python's license text and Debian package copyright records remain present in the
base image.

The selected MeCab blended router adds these hash-pinned runtime packages:

- `mecab-ko==1.0.2` (`pymecab-ko`), including MeCab by Taku Kudo and Nippon
  Telegraph and Telephone Corporation. MeCab is offered under GPL, LGPL, or
  the three-clause BSD license; this distribution selects the BSD terms.
  Source: <https://github.com/NoUnique/pymecab-ko>.
- `mecab-ko-dic==1.0.0`, Apache-2.0.
  Source: <https://github.com/LuminosoInsight/mecab-ko-dic>.
- `mmh3==5.2.0`, Copyright 2011-2025 Hajime Senuma, MIT.
  Source: <https://github.com/hajimes/mmh3>.

Their package license records remain under the installed Python distribution
metadata. `router_impl/requirements.txt` and `tokenizer_impl/requirements.txt`
contain the accepted release hashes, including the CPython 3.13 ARM64 wheels.

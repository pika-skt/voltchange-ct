# voltchange container runtime

This directory is a runtime-only, swappable container scaffold for the OSSP 2026
prompt router. It implements the official `router-run` interface and defaults to the
license-compatible MeCab-ko version of the latest blended linear router from
`voltchange`.

The research repository at `../voltchange` is not modified, and its notebooks,
outcomes, training code, caches, and local paths are not copied into the image.

## Shipping boundary

The stable layer owns protocol parsing, content-only normalization, strict output
validation, and atomic output writes. The implementation layer owns only model
prediction and batch allocation:

```text
official inputs.json
        |
runtime/entrypoint.py
        |
runtime/adapter.py       strips IDs/split/challenge metadata and sorts by content
        |
router_impl/router.py    swappable model/allocator implementation
        +--> tokenizer_impl/   independently swappable tokenize(text)
        |
validated, atomically written submission.json
```

The adapter never passes `episode_id`, `challenge_id`, `split`, or evaluator input
order to the router. It also rejects wrong-length results, unknown model IDs, and
different choices for identical prompt content.

The default implementation loads the unchanged official hash-regex score/cost heads
and a frozen MeCab-ko hybrid gain artifact. It verifies both SHA-256 digests and the
paired tokenizer ID, then blends the two Light-relative gain predictions using the
latest research weights and fixed safety ratios. No training data or outcomes are in
the image.

## Measured performance

The complete shipping configuration reproduces this public Dev result with the
unchanged `voltchange/main` safety policy:

| Tier | Quality | Actual cost ratio | Budget passed |
| --- | ---: | ---: | :---: |
| Fast | 0.663920 | 1.197378 | yes |
| Balanced | 0.702841 | 1.905316 | yes |
| Premium | 0.747443 | 3.867218 | yes |
| **Weighted final** | **0.700653409091** | — | **all** |

The MeCab swap was trained once on public Train with 1,024 hybrid hash bins, 14
structural features, and split Ridge penalties `30 / 3`. Public Dev was used only to
verify the already-fixed policy. MeCab-ko is distributed under the selectable
three-clause BSD terms, its dictionary is Apache-2.0, and mmh3 is MIT; all are in the
challenge allow-list and recorded in `THIRD_PARTY_NOTICES.md`.

## Component swap contracts

### Router/model

An implementation directory contains:

```text
candidate_router/
├── router.py
├── requirements.txt
├── artifact-manifest.json
└── model artifacts, if any
```

`router.py` exports exactly this callable:

```python
def route(episodes, tier, policy):
    """Return one allowed model ID for every content-only episode."""
```

The return order matches `episodes`. Allowed values are `ax31-light`, `ax31`, and
`axk1-think`. The implementation must not write files, use the network, train, or
invoke an LLM at runtime.

Build another implementation by selecting its repository-relative directory:

```bash
SOURCE_MANIFEST_SHA256="$(python3 tools/source_manifest.py \
  --implementation examples/always_light)"

docker build --pull --platform linux/arm64 \
  --build-arg ROUTER_IMPL=examples/always_light \
  --build-arg SOURCE_MANIFEST_SHA256="$SOURCE_MANIFEST_SHA256" \
  --tag voltchange-router:always-light .
```

`examples/always_light` is a minimal swap test. Pin every direct and transitive
dependency with hashes in a candidate's `requirements.txt`; the Dockerfile enforces
pip's hash-checking mode. Add each dependency's license and artifact provenance to the
candidate manifest and `THIRD_PARTY_NOTICES.md`.

### Tokenizer

A tokenizer directory is selected independently from the router/model directory:

```text
candidate_tokenizer/
├── tokenizer.py
├── tokenizer-manifest.json
└── requirements.txt
```

`tokenizer.py` exports a stable semantic ID and a callable:

```python
TOKENIZER_ID = "my-tokenizer-v1"

def tokenize(text: str):
    """Return an iterable of non-empty token strings."""
```

The tokenizer receives prompt text only, never evaluator IDs or split metadata. The
runtime validates its manifest and output. The router manifest declares the exact
`TOKENIZER_ID` it was trained with; a mismatched combination exits before prediction
instead of silently producing invalid features.

If a replacement produces exactly the same token sequence for every input, it may
retain the same semantic ID and the model does not need retraining. If segmentation,
normalization, POS decoration, or any emitted token can change, retrain the feature
standardization and prediction heads with that tokenizer, then export a router
manifest naming its new ID. The tier allocator should also be recalibrated because
changed predictions can change aggregate cost. A router that ignores lexical features,
such as `examples/always_light`, does not have this coupling.

`examples/tokenizers/whitespace_v1` is an intentionally incompatible tokenizer
example. It demonstrates the directory contract; the default trained model correctly
refuses it. Build a real paired model/tokenizer like this:

```bash
SOURCE_MANIFEST_SHA256="$(python3 tools/source_manifest.py \
  --implementation candidate_router \
  --tokenizer candidate_tokenizer)"

docker build --pull --platform linux/arm64 \
  --build-arg ROUTER_IMPL=candidate_router \
  --build-arg TOKENIZER_IMPL=candidate_tokenizer \
  --build-arg SOURCE_MANIFEST_SHA256="$SOURCE_MANIFEST_SHA256" \
  --tag voltchange-router:candidate .
```

Both components have separate hash-pinned requirements files. The source-manifest
digest and OCI labels record both selected directories.

## Build the default image

The Python base is a Docker Official Image pinned by full OCI index digest and includes
an ARM64 manifest. The final stage removes pip/setuptools/wheel, runs as numeric
`65532:65532`, declares no `VOLUME`, and contains only runtime code, policy, artifact,
and notices.

```bash
SOURCE_MANIFEST_SHA256="$(python3 tools/source_manifest.py)"

docker build --pull --platform linux/arm64 \
  --build-arg SOURCE_MANIFEST_SHA256="$SOURCE_MANIFEST_SHA256" \
  --tag voltchange-router:check .
```

For a final submission, build from the public evaluation commit, push the ARM64 image,
and record the immutable image digest together with that full commit SHA. Do not submit
a mutable tag as the image identity.

## Official runtime limits

The scaffold follows `../ossp-2026-llm-router-challenge/docs/RUNTIME.md` and
`docs/CHALLENGE_RULES.md`:

| Boundary | Limit |
| --- | ---: |
| Platform | `linux/arm64` |
| CPU | 2 cores |
| Memory | 2 GiB, no extra swap |
| Processes and threads | 32 total |
| Runtime | 90 seconds per tier |
| `/tmp` | 256 MiB |
| Output | 4 MiB, 64 inodes |
| stdout and stderr | 1 MiB each |
| Compressed OCI layers | 1 GiB |
| Merged root filesystem | 2 GiB |

The evaluator runs one full input batch per tier with no network, GPU, IPC, Linux
capabilities, writable root filesystem, or host devices. Only `/tmp` and the constrained
output mount are writable. The output mount must contain exactly
`submission.json` after success.

The image entry point accepts the official invocation directly:

```bash
router-run \
  --input /challenge/input/inputs.json \
  --tier fast \
  --output /challenge/output/submission.json
```

In the image, `router-run` is represented by the fixed JSON entry point, so a smoke run
passes only the arguments:

```bash
mkdir -p build/output

docker run --rm --platform linux/arm64 \
  --network none \
  --read-only \
  --user 65532:65532 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --cpus 2 \
  --memory 2g \
  --memory-swap 2g \
  --pids-limit 32 \
  --ipc none \
  --ulimit core=0:0 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=256m \
  --mount type=bind,src="$PWD/tests/data",dst=/challenge/input,readonly \
  --mount type=bind,src="$PWD/build/output",dst=/challenge/output \
  voltchange-router:check \
  --input /challenge/input/toy-inputs.json \
  --tier fast \
  --output /challenge/output/submission.json
```

The bind-mounted output in that command is only a developer smoke test. The official
runner additionally enforces the 4 MiB and inode limits.

## Verification

Install the hash-pinned runtime dependencies, then run the self-contained protocol,
feature-hash, swap-boundary, ID/order, manifest, and atomic-output tests:

```bash
python3 -m pip install --require-hashes \
  -r router_impl/requirements.txt -r tokenizer_impl/requirements.txt
python3 -m unittest discover -s tests -p 'test_*.py'
```

Run all tiers on any prompt-only input and report elapsed time, output size, decision
digests, and process peak RSS:

```bash
PYTHONPATH=. python3 tools/preflight.py \
  --input tests/data/toy-inputs.json
```

Verify that the unchanged official score/cost predictions still match the direct
official baseline path:

```bash
PYTHONPATH=. python3 tools/verify_default_parity.py \
  --input tests/data/toy-inputs.json \
  --official-repo ../ossp-2026-llm-router-challenge
```

For an offline training/runtime audit, `tools/verify_mecab_training_parity.py`
compares MeCab tokens, every emitted hybrid feature, all 1,024 normalized hash bins,
and all structural values against the frozen `voltchange` training implementation.

After building, use the authoritative checker from the official repository for the
full public Train/Dev inputs and actual isolation/resource controls:

```bash
PYTHONPATH=../ossp-2026-llm-router-challenge/src \
python3 ../ossp-2026-llm-router-challenge/tools/check_runtime.py \
  --image voltchange-router:check \
  --report build/runtime-check-report.json
```

Current verification is recorded in `verification-report.json`. Public Dev reproduces
`0.700653409091` with all budgets passing. Host and official ARM64 container timings,
RSS, image size, and decision digests are updated only from fresh measurements.

Before a final push, also inspect the selected platform, image size, config, user,
entry point, labels, and absence of `Volumes`. `artifact-manifest.json`,
`BASE_IMAGE.md`, `THIRD_PARTY_NOTICES.md`, and `test-vector.json` preserve the export
provenance called for by the `voltchange` design notes. Once repository URL, final
commit, registry name, and image digest exist, create and validate the official
`submission-ossp-skt.json`; this scaffold does not fabricate those unknown values.

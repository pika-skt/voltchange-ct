# voltchange container runtime

This directory is a runtime-only, swappable container scaffold for the OSSP 2026
prompt router. It implements the official `router-run` interface and defaults to the
public artifact-backed hash/regex router already integrated by `voltchange`.

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

The default implementation is intentionally dependency-free at runtime. It loads
`router_impl/hash-regex-public.v1.json`, verifies the artifact SHA-256 against its
manifest, verifies that the selected tokenizer ID matches the trained artifact,
predicts with the frozen linear heads, and uses the official batch-level allocator.

## Measured performance

The default is dependency-free, but it is not tokenizer-free: it uses the small
stdlib-only tokenizer in `tokenizer_impl/`. The complete shipping configuration
reproduces this public Dev result:

| Tier | Quality | Actual cost ratio | Budget passed |
| --- | ---: | ---: | :---: |
| Fast | 0.663068 | 1.235989 | yes |
| Balanced | 0.693750 | 1.961506 | yes |
| Premium | 0.740057 | 3.985205 | yes |
| **Weighted final** | **0.695369318182** | — | **all** |

For the controlled experiment in `../voltchange` that held the rest of the training
pipeline constant, regex scored `0.688949` and Kiwi scored `0.687955`. Do not compare
that ablation directly with `0.695369`: the shipping artifact also uses the official
256-bin feature setup and Dev-calibrated routing safety policy.

## Why the current blended research model is not the default

`../voltchange` currently identifies `BlendedPosHashRegexStrategy` as its active
research strategy. That implementation imports `kiwipiepy`; the installed package
metadata identifies it and its model package as LGPL-3.0. The challenge's published
submission rules require prior approval for a directly used library outside the
listed license set. For that reason this scaffold does not silently put Kiwi into the
shipping image.

Once that dependency is approved or replaced, export only the fitted inference
artifact and runtime feature logic into a new implementation directory. Training and
public outcomes must remain outside the final image.

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

Run the self-contained protocol, swap-boundary, ID/order audit, manifest, and atomic
output tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Run all tiers on any prompt-only input and report elapsed time, output size, decision
digests, and process peak RSS:

```bash
PYTHONPATH=. python3 tools/preflight.py \
  --input tests/data/toy-inputs.json
```

For the default implementation, verify that the content-only sorting adapter produces
exactly the same choices as the direct official baseline path:

```bash
PYTHONPATH=. python3 tools/verify_default_parity.py \
  --input tests/data/toy-inputs.json
```

After building, use the authoritative checker from the official repository for the
full public Train/Dev inputs and actual isolation/resource controls:

```bash
PYTHONPATH=../ossp-2026-llm-router-challenge/src \
python3 ../ossp-2026-llm-router-challenge/tools/check_runtime.py \
  --image voltchange-router:check \
  --report build/runtime-check-report.json
```

Current host verification is recorded in `verification-report.json`: all unit tests
and lint pass; the adapted router has zero mismatches across 5,280 Train and 2,640 Dev
tier decisions; public Dev reproduces `0.695369318182` with all budgets passing. On
Python 3.13.11/x86-64, full Train peaks near 82 MiB RSS and the slowest tier takes
5.69 seconds. These are encouraging host measurements, not substitutes for the
official ARM64 container check.

Before a final push, also inspect the selected platform, image size, config, user,
entry point, labels, and absence of `Volumes`. `artifact-manifest.json`,
`BASE_IMAGE.md`, `THIRD_PARTY_NOTICES.md`, and `test-vector.json` preserve the export
provenance called for by the `voltchange` design notes. Once repository URL, final
commit, registry name, and image digest exist, create and validate the official
`submission-ossp-skt.json`; this scaffold does not fabricate those unknown values.

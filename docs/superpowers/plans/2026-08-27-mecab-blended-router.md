# MeCab Blended Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The user explicitly requested inline execution, one final commit, and no TDD-first workflow.

**Goal:** Ship the latest `voltchange` blended linear router with MeCab-ko in the official ARM64 container format while preserving the measured public Dev score and every budget.

**Architecture:** Keep the existing content-only adapter, official hash-regex score/cost artifact, and allocator boundary. Replace the selected tokenizer with MeCab-ko, add a frozen MeCab hybrid-gain artifact exported from public Train, blend its two Light-relative gains with official gains using the latest `voltchange/main` weights, and disable the old Premium fill because the research model did not use it.

**Tech Stack:** Python 3.13, MeCab-ko, stdlib JSON/math/hashlib, `mmh3` for exact scikit-learn-compatible MurmurHash3 feature bins, Docker/OCI `linux/arm64`.

---

### Task 1: Export the frozen MeCab gain artifact

**Files:**
- Create: `tools/export_mecab_blended.py`
- Create: `router_impl/mecab-blended-gain.v1.json`

- [ ] Add an offline exporter that accepts `--lab-root`, `--challenge-root`, `--materialized-root`, and `--output`.
- [ ] Load public Train through `router_lab`, use the exact `MecabTokenizer` and hybrid feature functions from commit `fe300cb`, fit StandardScaler plus Ridge `alpha=(30, 3)` with normalized generation weights, and serialize structural mean/scale, both intercept/coefficient vectors, tier blend weights, tier safety ratios, policy digest, tokenizer ID, and provenance.
- [ ] Run the exporter with MeCab-ko `1.0.2` and dictionary `1.0.0`; require 1,038 coefficients per head and a deterministic SHA-256.

### Task 2: Implement exact runtime feature inference

**Files:**
- Create: `router_impl/hybrid_features.py`
- Create: `router_impl/blended_gain.py`
- Modify: `router_impl/router.py`

- [ ] Port the content-only structural and hybrid token feature functions used by `voltchange/main`, with MeCab token strings decoded into `form` and `tag`.
- [ ] Hash each feature exactly like scikit-learn FeatureHasher: signed MurmurHash3 x86-32, `abs(hash) % 1024`, collision summation, then L2 normalization.
- [ ] Validate and load the gain artifact, standardize the 14 structural values, append the 1,024 hash bins, and evaluate the two linear gain heads.
- [ ] Preserve the official regex tokenizer for official score/cost prediction, blend only Light-relative gains using Fast `(0.60, 0.075)`, Balanced `(0.50, 0.25)`, Premium `(0.20, 0.15)`, and route with fixed safety `0.9108333333 / 0.8916666667 / 0.9` without Premium fill.

### Task 3: Make MeCab-ko the selected submission tokenizer

**Files:**
- Modify: `tokenizer_impl/tokenizer.py`
- Modify: `tokenizer_impl/tokenizer-manifest.json`
- Modify: `tokenizer_impl/requirements.txt`
- Modify: `router_impl/requirements.txt`

- [ ] Protect Latin/alphanumeric spans exactly as the training adapter, parse only unprotected spans with `mecab_ko.Tagger`, and emit reversible non-empty `tag + unit-separator + form` strings under tokenizer ID `mecab-ko-hybrid-pos-v1`.
- [ ] Pin MeCab-ko, MeCab-ko dictionary, and `mmh3` with hashes accepted by Docker `pip --require-hashes` on CPython 3.13 ARM64.

### Task 4: Update provenance, licenses, and frozen vectors

**Files:**
- Modify: `artifact-manifest.json`
- Modify: `router_impl/artifact-manifest.json`
- Modify: `THIRD_PARTY_NOTICES.md`
- Modify: `README.md`
- Modify: `test-vector.json`
- Modify: `tests/test_runtime.py`

- [ ] Bind both official and MeCab gain artifact digests, tokenizer ID, source commit `fe300cb`, package versions, licenses, and training hashes in manifests/notices.
- [ ] Replace the default tokenizer/vector assertions with MeCab semantics and add parity assertions for exact MurmurHash bins and artifact dimensions.
- [ ] Regenerate toy decisions and document the expected public Dev target `0.700653409091` with unchanged main safety.

### Task 5: Verify host parity and official container limits

**Files:**
- Update: `verification-report.json`

- [ ] Run `python3 -m unittest discover -s tests -p 'test_*.py'` and `PYTHONPATH=. python3 tools/preflight.py`.
- [ ] Route public Dev through the submission runtime, score it with the official scorer, and require final `0.700653409091` plus Fast/Balanced/Premium cost ratios `1.197378 / 1.905316 / 3.867218` within numeric tolerance.
- [ ] Build `linux/arm64`, inspect platform/user/entrypoint/layers, then run the official `tools/check_runtime.py` with 2 CPU, 2 GiB, 32 PIDs, no network, read-only root, and 90 seconds per tier.
- [ ] Record per-tier elapsed time, peak RSS, output size, image size, decision digests, quality, cost ratios, and budget pass/fail. Commit only after all required checks have fresh output.

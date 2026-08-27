# Base image provenance

The container uses the Docker Official Image `python:3.13.11-slim-bookworm`, pinned
to the immutable multi-platform OCI index:

```text
sha256:20080e807bfc404f8450b185cf0fc95d553462673598549613735f70a5b4d5d0
```

The index contains the required `linux/arm64` manifest:

```text
sha256:a4997dee8fbd74dd6464782b13f5696140f691ff7efc0098bb0b796fce883049
```

Its OCI annotations identify Docker Library Python source revision
`40b30bb99b8ec66eb1412711daa66827022f2593` and base
`debian:bookworm-slim` ARM64 digest
`sha256:1c5d4fd0caad88eb6cb62bcdbc2f580ef2523ab69e86abc2bd2a94703aac9f96`.

The final image removes pip, setuptools, and wheel. Python's license and Debian
package copyright records remain in the base filesystem. The default router adds no
third-party Python package.

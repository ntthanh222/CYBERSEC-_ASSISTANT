# syntax=docker/dockerfile:1
# Debian slim (glibc) instead of Alpine (musl): Phase 2.6 adds fastembed,
# which depends on onnxruntime. onnxruntime publishes zero musllinux wheels
# on PyPI for any release (verified against the PyPI JSON API for the latest
# release, 2026-07-30) - it is a manylinux/glibc-only distribution upstream,
# not a packaging gap this project can route around. Building onnxruntime
# from source against musl is not supported by the upstream project and is
# out of proportion for a dependency this project does not maintain.
#
# trixie (Debian 13), not bookworm (Debian 12): re-measured with Trivy
# 2026-08-04, trixie already carries 2 fewer CRITICALs (libsqlite3-0,
# zlib1g both patched there) than bookworm for the same package set. The
# remaining base-rootfs findings on either release have no fixed version
# upstream and are closed out below by removing the packages themselves
# (see the runtime-package purge), not by waiting on a patch.
#
# Multi-stage: build wheels with the compiler toolchain present, then copy
# only the installed site-packages into a compiler-free runtime image.
FROM python:3.12-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# gcc/build tools stay confined to this build stage; the runtime stage below
# never gets a compiler. libgomp1 is onnxruntime's OpenMP runtime dependency
# for CPU inference and is required at both build (for pip's build backends
# that probe it) and run time - installed again, runtime-only, below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r backend/requirements.txt

FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_CACHE_DIR=/app/.cache/fastembed \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# ca-certificates: TLS for the Hugging Face model download and outbound
# HTTPS providers. libgomp1: onnxruntime's CPU-inference OpenMP runtime
# (import-time dependency, not just a build-time one). No compiler, and no
# curl/bash - the healthcheck and entrypoint below use Python's stdlib and
# POSIX /bin/sh (dash, already present in the base image) respectively, so
# neither curl nor bash is ever installed here in the first place.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY backend/ ./backend/
RUN sed -i 's/\r$//' backend/entrypoint.sh \
    && chmod +x backend/entrypoint.sh

# The fastembed model cache (EMBEDDING_CACHE_DIR) and huggingface_hub's own
# cache/lockfiles (HF_HOME - written by its xet download client even when
# EMBEDDING_CACHE_DIR points elsewhere) are both written at first embed()
# call, not baked into the image (see backend/providers/embeddings/local.py),
# and must be writable by the non-root runtime user even though the rest of
# the filesystem is mounted read-only by docker-compose.yml
# (`read_only: true`) - compose maps a dedicated named volume onto this
# whole /app/.cache tree, so the directories created and chowned here become
# the volume's initial (writable, non-root-owned) content instead of empty
# root-owned space. /app/.local-secret gets the identical treatment for the
# Docker-local demo-auth signing secret (backend/core/local_auth_secret.py) -
# a second dedicated named volume, generated once and reused across restarts.
RUN groupadd -g 10001 appuser \
    && useradd -m -u 10001 -g appuser appuser \
    && mkdir -p /app/.cache/fastembed /app/.cache/huggingface /app/.local-secret \
    && chown -R appuser:appuser /app

# Trivy (2026-08-04) found 24 remaining HIGH/CRITICAL findings after the
# base-image switch to trixie, every one in a base-rootfs package this
# Dockerfile never asked for and this application never calls at runtime:
# perl-base (interpreter, unused - no script here is Perl), gzip (Python's
# stdlib gzip module is used instead), bash (superseded by /bin/sh/dash
# above - dash itself has no such findings and is kept), the login/
# util-linux family (mount, su, fdisk-adjacent tooling - a container never
# mounts anything or logs in a user), ncurses/libtinfo (terminal UI support
# - uvicorn is not an interactive terminal program), and libacl1 (pulled in
# only by coreutils/tar/sed/passwd, none of which this container's
# Python-only entrypoint ever invokes). Each removal was individually
# verified first (`dpkg -L <pkg>` plus an `ldd` sweep of every .so under
# /usr/local confirms no Python interpreter, C extension, or site-package
# links against any of them).
#
# `dpkg --purge --force-depends --force-remove-essential
# --force-remove-protected`, not `apt-get purge`: apt's dependency solver
# refuses to stop at this exact list - asking it to remove libacl1 (or
# bash, or util-linux) pulls in coreutils, which pulls in tar/sed, which
# pulls in dpkg/apt themselves, and dpkg cannot safely remove its own
# supporting tools mid-transaction (reproduced: that form of this RUN
# aborted with `tar.prerm: update-alternatives: not found` once dpkg's own
# tools were gone before it finished processing the removal it was in the
# middle of). `--force-remove-protected` is required separately from
# `--force-remove-essential`: dpkg tracks "Essential: yes" and
# "Protected: yes" as distinct properties, and `login` carries the latter
# (reproduced: without this flag dpkg refuses it with "this is a protected
# package; it should not be removed", a different error from the
# essential-package warning the other packages here trigger).
# `dpkg --purge` on exactly the named packages, bypassing apt's solver,
# removes only those packages - and their dpkg registration, which is what
# Trivy actually reads (a plain `rm` of libacl1's .so file alone left the
# finding still reported, since the package was still "installed" per
# dpkg's database).
#
# libacl1 is purged in its own RUN, after this one, not folded into this
# list: `login`/`debianutils` defer some of their removal work to dpkg
# triggers that run once the packages named in a single dpkg invocation
# are gone, and `mv` (invoked by one of those triggers) is itself
# dynamically linked against libacl.so.1 - reproduced: purging libacl1 in
# the same batch removed it before that trigger ran, so the trigger's own
# `mv` call failed with "cannot open shared object file: No such file or
# directory" and aborted the whole RUN. Splitting it into a second,
# separate RUN (below) lets this batch's triggers finish first.
RUN dpkg --purge --force-depends --force-remove-essential --force-remove-protected \
        perl-base gzip bash \
        ncurses-bin ncurses-base libncursesw6 libtinfo6 \
        login liblastlog2-2 util-linux bsdutils mount \
        libblkid1 libmount1 libsmartcols1 libuuid1 \
    && rm -rf /var/lib/apt/lists/*

RUN dpkg --purge --force-depends --force-remove-essential --force-remove-protected libacl1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=10 --start-period=20s \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

ENTRYPOINT ["backend/entrypoint.sh"]

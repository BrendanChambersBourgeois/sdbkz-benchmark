# Base image ships MPFR 4.2.0 via Debian bookworm. Measured bit-identical
# to MPFR 4.2.1 at 250-bit precision across Intel 13900K / AWS Batch /
# AMD 9950X3D (paper §3.5; hash_verification.txt). Listed here so that a
# reader auditing the reproducibility chain can see the version drift is
# accounted for, not silent.
#
# Digest-pinned per ADR-004 (docs/design_decisions.md). The sha256 below
# was resolved from the Docker Hub registry on 2026-05-14; the tag
# python:3.12.3-bookworm last_updated 2024-05-14T18:08:59Z. Re-resolve
# from `curl -sL https://hub.docker.com/v2/repositories/library/python/tags/3.12.3-bookworm`
# if a future build needs verification.
FROM python:3.12.3-bookworm@sha256:25dee7f137aa44c4962d21346385737eb81954b6f06f519fcc348b67f6483d3c

# MPFR — required by fplll for arbitrary-precision floating point.
# Previously pinned to libmpfr-dev=4.2.1-1 explicitly, but Debian Bookworm
# rolled the package revision and the old apt version vanished from
# current mirrors. Re-pinning via snapshot.debian.org (ADR-004) freezes
# the apt resolution to a dated snapshot of the Debian archive rather
# than chasing per-package revision strings.
#
# Snapshot date 20240614T000000Z chosen one month after the base-image
# last_updated to ensure the libmpfr6 4.2.0 runtime that the digest pin
# bakes in matches the headers/dev package resolved from apt.
RUN printf 'Types: deb\nURIs: http://snapshot.debian.org/archive/debian/20240614T000000Z/\nSuites: bookworm bookworm-updates\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\nTypes: deb\nURIs: http://snapshot.debian.org/archive/debian-security/20240614T000000Z/\nSuites: bookworm-security\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n' \
        > /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
        libmpfr-dev \
        libgmp-dev \
        build-essential \
        autoconf \
        libtool \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Pin Python packages to exact versions used in the experiment.
# fpylll 0.6.4 bundles fplll 5.5.0 (libfplll.so.9.0.0) as a vendored library.
# matplotlib + render-touching transitive deps (pillow, fonttools, contourpy,
# kiwisolver, pyparsing, cycler) are pinned because the figure-SHA-byte-
# identity gate compares regen-PNG bytes against committed baseline; even
# patch-level matplotlib bumps (3.10.8 → 3.10.9) drift the SHA. Discovered
# 2026-05-03 when CI failed on commit ccc9674 against a baseline produced
# under matplotlib 3.10.8. scipy + pytest pinned for completeness.
RUN pip install --no-cache-dir \
        fpylll==0.6.4 \
        cysignals==1.12.6 \
        numpy==2.4.4 \
        scipy==1.17.1 \
        matplotlib==3.10.8 \
        pillow==12.2.0 \
        fonttools==4.62.1 \
        contourpy==1.3.3 \
        kiwisolver==1.5.0 \
        pyparsing==3.3.2 \
        cycler==0.12.1 \
        pytest==9.0.3

# Non-root runtime — match host UID/GID so bind-mounted ./results +
# ./logs do not produce root-owned host files (Incident #32 recurrence
# pattern; backlog
# backlog/2026-04-20_v3_dockerfile_scope.md §8).
# Defaults match the most common Linux desktop UID/GID; override at
# build time with --build-arg HOST_UID=$(id -u) --build-arg
# HOST_GID=$(id -g) on systems where they differ. The `getent` guards
# tolerate base images that already ship a user/group at the requested
# numeric ID.
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN if ! getent group ${HOST_GID} >/dev/null; then \
        groupadd -g ${HOST_GID} runner; \
    fi && \
    if ! getent passwd ${HOST_UID} >/dev/null; then \
        useradd --no-log-init -u ${HOST_UID} -g ${HOST_GID} -m runner; \
    fi

WORKDIR /experiment
# Copy the full scripts/ directory so wrapper scripts (run_q3329_n100_local,
# run_q3329_intermediate, run_3x_extended, etc.) can find their imports
# (e.g. q3329_verify) via the same scripts/-relative paths used in the
# host repo. The repo restructure on 2026-04-08 moved all the runnable
# scripts into scripts/; the Dockerfile previously only copied two
# individual files at the old top-level paths and was silently broken
# for everything else until a fresh build attempt by a collaborator
# surfaced it on 2026-04-09.
COPY --chown=${HOST_UID}:${HOST_GID} scripts/ scripts/

# Ship config/ (sweep.toml) so campaign runs are self-contained: a collaborator
# can `docker run <img> python3 scripts/run_campaign.py --campaign ...` with no
# host checkout. Without this, run_campaign needs config/sweep.toml bind-mounted.
COPY --chown=${HOST_UID}:${HOST_GID} config/ config/

# Self-contained image: ship analysis/, tests/, and paper-cited results
# JSONs so a reviewer can run `pytest tests/` or
# `python3 analysis/paper_figures.py` against the image with no host
# bind-mount. Bulk seed data stays out of the image (excluded via
# .dockerignore); these are the small artifacts that the paper figures
# + claim ledger reference directly. Per backlog
# backlog/2026-04-20_v3_dockerfile_scope.md §1
# (fresh-VM reproducibility, INC-36).
COPY --chown=${HOST_UID}:${HOST_GID} analysis/ analysis/
COPY --chown=${HOST_UID}:${HOST_GID} tests/ tests/
COPY --chown=${HOST_UID}:${HOST_GID} results/paper_claims/ results/paper_claims/
COPY --chown=${HOST_UID}:${HOST_GID} \
     results/summary.json results/runtime_table.json \
     results/profile_decomposition.json results/convergence_headroom.json \
     results/dGSA_summary.json results/seed_manifest.json \
     results/hash_verification.txt results/

# Ensure /experiment + the to-be-created results/ + logs/ subdirs are
# writable by the runtime user (verify.sh writes results/, sweep
# scripts write logs/).
RUN chown -R ${HOST_UID}:${HOST_GID} /experiment

USER ${HOST_UID}:${HOST_GID}

# Default: run the full local sweep
CMD ["python3", "scripts/sweep_parallel.py"]

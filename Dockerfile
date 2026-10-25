# Base image ships MPFR 4.2.0 (Debian bookworm); measured bit-identical to
# MPFR 4.2.1 at 250-bit precision across three hosts (paper §3.5,
# results/hash_verification.txt). Digest-pinned per ADR-004.
FROM python:3.12.3-bookworm@sha256:25dee7f137aa44c4962d21346385737eb81954b6f06f519fcc348b67f6483d3c

# Apt pinned to a dated snapshot.debian.org archive so the libmpfr headers
# match the runtime lib baked into the base-image digest.
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

# Exact versions used in the experiment. fpylll 0.6.4 bundles fplll 5.5.0.
# matplotlib and its render-touching deps are pinned because the figure
# byte-identity gate compares regenerated PNG bytes; patch-level bumps drift.
RUN pip install --no-cache-dir \
        fpylll==0.6.4 \
        cysignals==1.12.6 \
        numpy==2.4.4 \
        scipy==1.17.1 \
        sympy==1.14.0 \
        mpmath==1.3.0 \
        matplotlib==3.10.8 \
        pillow==12.2.0 \
        fonttools==4.62.1 \
        contourpy==1.3.3 \
        kiwisolver==1.5.0 \
        pyparsing==3.3.2 \
        cycler==0.12.1 \
        pytest==9.0.3

# Non-root runtime matching the host UID/GID so bind-mounted results/ and
# logs/ stay host-owned; override with --build-arg HOST_UID/HOST_GID.
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN if ! getent group ${HOST_GID} >/dev/null; then \
        groupadd -g ${HOST_GID} runner; \
    fi && \
    if ! getent passwd ${HOST_UID} >/dev/null; then \
        useradd --no-log-init -u ${HOST_UID} -g ${HOST_GID} -m runner; \
    fi

WORKDIR /experiment
COPY --chown=${HOST_UID}:${HOST_GID} scripts/ scripts/

# config/ (sweep.toml) so campaign runs need no host checkout.
COPY --chown=${HOST_UID}:${HOST_GID} config/ config/

# analysis/, tests/ and the paper-cited results JSONs so `pytest tests/` and
# `python3 analysis/paper_figures.py` run in-image. Bulk seed data stays out
# (.dockerignore).
COPY --chown=${HOST_UID}:${HOST_GID} analysis/ analysis/
COPY --chown=${HOST_UID}:${HOST_GID} tests/ tests/
COPY --chown=${HOST_UID}:${HOST_GID} results/paper_claims/ results/paper_claims/
COPY --chown=${HOST_UID}:${HOST_GID} \
     results/summary.json results/runtime_table.json \
     results/profile_decomposition.json results/convergence_headroom.json \
     results/dGSA_summary.json results/seed_manifest.json \
     results/hash_verification.txt results/
# verify.sh reads this golden reference in-image.
COPY --chown=${HOST_UID}:${HOST_GID} \
     results/validation/verify_reference.json results/validation/verify_reference.json

RUN chown -R ${HOST_UID}:${HOST_GID} /experiment

USER ${HOST_UID}:${HOST_GID}

CMD ["python3", "scripts/sweep_parallel.py"]

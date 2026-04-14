FROM python:3.12.3-bookworm

# MPFR 4.2.1 — required by fplll for arbitrary-precision floating point.
# Previously pinned to libmpfr-dev=4.2.1-1 for reproducibility, but Debian
# Bookworm bumped the package revision (still upstream MPFR 4.2.1, just a
# Debian packaging update) and the old apt version is no longer available
# on current mirrors. The cloud Dockerfile has always been unpinned and
# produces SHA-256-bit-identical results to the locally-built image, so
# unpinning here is safe in practice. The verify.sh reproducibility check
# is the safety net — any new build that diverges will be caught there
# before real seeds are computed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmpfr-dev \
        libgmp-dev \
        build-essential \
        autoconf \
        libtool \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Pin Python packages to exact versions used in the experiment
# fpylll 0.6.4 bundles fplll 5.5.0 (libfplll.so.9.0.0) as a vendored library
RUN pip install --no-cache-dir \
        fpylll==0.6.4 \
        cysignals==1.12.6 \
        numpy==2.4.4

WORKDIR /experiment
# Copy the full scripts/ directory so wrapper scripts (run_q3329_n100_local,
# run_q3329_intermediate, run_3x_extended, etc.) can find their imports
# (e.g. q3329_verify) via the same scripts/-relative paths used in the
# host repo. The repo restructure on 2026-04-08 moved all the runnable
# scripts into scripts/; the Dockerfile previously only copied two
# individual files at the old top-level paths and was silently broken
# for everything else until a fresh build attempt by a collaborator
# surfaced it on 2026-04-09.
COPY scripts/ scripts/

# Default: run the full local sweep
CMD ["python3", "scripts/sweep_parallel.py"]

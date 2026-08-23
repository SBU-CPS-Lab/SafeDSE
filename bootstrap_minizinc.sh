#!/usr/bin/env bash
# Bootstrap MiniZinc + Gecode + Chuffed + OR-Tools CP-SAT.
# Run once per session (the container filesystem resets between sessions).
set -euo pipefail
MZN_VERSION="${MZN_VERSION:-2.10.0}"
PREFIX="${PREFIX:-/opt/mzn210}"
URL="https://github.com/MiniZinc/MiniZincIDE/releases/download/${MZN_VERSION}/MiniZincIDE-${MZN_VERSION}-bundle-linux-x86_64.tgz"

# `-x` alone is not enough to call an install good. An interrupted extraction
# leaves a bin/minizinc that exists, is executable, and segfaults -- and because
# tools/solve.py probed with a plain existence test, every solve then returned
# NOSOL and the whole suite failed as though the MODEL were broken. That is the
# silent-failure mode this project is built to avoid, so the check is "does it
# actually run", and the extraction is atomic so the half-written state is never
# visible under PREFIX in the first place.
if [ -x "${PREFIX}/bin/minizinc" ] && "${PREFIX}/bin/minizinc" --version >/dev/null 2>&1; then
  echo "MiniZinc already present and working at ${PREFIX}"
else
  if [ -e "${PREFIX}" ]; then
    echo "Removing a broken or partial install at ${PREFIX}"
    rm -rf "${PREFIX}"
  fi
  echo "Downloading MiniZinc ${MZN_VERSION} ..."
  curl -sS -L --max-time 900 -o /tmp/mzn.tgz.part "${URL}"
  mv /tmp/mzn.tgz.part /tmp/mzn.tgz
  STAGE="$(mktemp -d "${PREFIX}.stage.XXXXXX")"
  trap 'rm -rf "${STAGE}"' EXIT
  echo "Extracting ..."
  tar xzf /tmp/mzn.tgz -C "${STAGE}" --strip-components=1
  "${STAGE}/bin/minizinc" --version >/dev/null   # fail here, not three hours later
  mv "${STAGE}" "${PREFIX}"
  trap - EXIT
  rm -f /tmp/mzn.tgz
fi

export PATH="${PREFIX}/bin:${PATH}"
# NOTE: do NOT export LD_LIBRARY_PATH globally -- the bundled libselinux
# shadows the system one and breaks coreutils. minizinc works without it.
echo
minizinc --version
echo
minizinc --solvers | sed -n '2,20p'
echo
echo 'Add to your shell:  export PATH='"${PREFIX}"'/bin:$PATH'

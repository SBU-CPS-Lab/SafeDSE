#!/usr/bin/env bash
# Bootstrap MiniZinc + Gecode + Chuffed + OR-Tools CP-SAT.
# Run once per session (the container filesystem resets between sessions).
set -euo pipefail
MZN_VERSION="${MZN_VERSION:-2.8.7}"
PREFIX="${PREFIX:-/opt/mzn}"
URL="https://github.com/MiniZinc/MiniZincIDE/releases/download/${MZN_VERSION}/MiniZincIDE-${MZN_VERSION}-bundle-linux-x86_64.tgz"

if [ -x "${PREFIX}/bin/minizinc" ]; then
  echo "MiniZinc already present at ${PREFIX}"
else
  echo "Downloading MiniZinc ${MZN_VERSION} ..."
  curl -sS -L --max-time 900 -o /tmp/mzn.tgz "${URL}"
  mkdir -p "${PREFIX}"
  tar xzf /tmp/mzn.tgz -C "${PREFIX}" --strip-components=1
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

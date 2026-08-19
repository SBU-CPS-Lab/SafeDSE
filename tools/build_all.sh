#!/usr/bin/env bash
# Rebuild every .dzn in out/ from its XML sources. Run after any front-end
# change, otherwise older instances lack the newest parameters and the model
# fails with "variable X must be defined".
set -e
cd "$(dirname "$0")/.."
B="python3 tools/build_dzn.py"
M="--platform data/platform/mixed.xml --wcets data/WCETs_mixed.xml --constraints data/desConst.xml --cost-model data/cost_model.xml"
R="--platform data/rosvall/platform.xml --wcets data/rosvall/WCETs.xml --constraints data/rosvall/desConst.xml --cost-model data/cost_model.xml"

# --- Rosvall ToDAES benchmark ---
for a in a_sobel b_susan c_rasta d_jpegEnc1; do
  $B --app data/rosvall/$a.hsdf.xml $R -o out/r_$a.dzn
done
APPS=""
for a in a_sobel b_susan c_rasta d_jpegEnc1; do APPS="$APPS --app data/rosvall/$a.hsdf.xml"; done
$B $APPS $R -o out/r_all.dzn
$B $APPS $R --period-mode partitioned -o out/r_all_part.dzn
$B --app data/rosvall/a_sobel.hsdf.xml --app data/rosvall/c_rasta.hsdf.xml $R \
   --latency data/rosvall/latency.xml --period-mode partitioned -o out/r_lat.dzn

# --- card-based platform ---
$B --app data/apps/c_rasta.hsdf.xml     $M --safety data/safety_rasta.xml -o out/rasta.dzn
$B --app data/apps/d_jpegEnc1.sdf.xml   $M -o out/jpeg_sdf.dzn
$B --app data/apps/jpeg_r3.sdf.xml      $M -o out/jpeg_r3.dzn
$B --app data/apps/d_jpegEnc1.hsdf.xml  $M -o out/jpeg.dzn

# --- C.5 measurement: identical inventory, different FCR granularity ---
for pf in mixed mixed_flat; do
  $B --app data/apps/d_jpegEnc1.sdf.xml --platform data/platform/$pf.xml \
     --wcets data/WCETs_mixed.xml --constraints data/desConst.xml \
     --cost-model data/cost_model.xml -o out/m_$pf.dzn
done

# --- Phase 3: safety ---
NI="--platform data/platform/mixed_noiso.xml --wcets data/WCETs_mixed.xml --constraints data/desConst.xml --cost-model data/cost_model.xml"
CO="--platform data/platform/mixed_costly.xml --wcets data/WCETs_mixed.xml --constraints data/desConst.xml --cost-model data/cost_model.xml"
for prof in myklebust2015 klosterman do178b; do
  $B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta.xml \
     --cost-profile $prof -o out/s_$prof.dzn
  $B --app data/apps/c_rasta.hsdf.xml $CO --safety data/safety_rasta.xml \
     --cost-profile $prof -o out/x_$prof.dzn
done
$B --app data/apps/c_rasta.hsdf.xml $M --safety data/safety_rasta.xml -o out/s_rasta.dzn
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta_nopromo.xml -o out/s_nopromo.dzn

# --- Phase 4: pattern superposition ---
PAT="--patterns data/patterns.yaml"
$B --app data/apps/c_rasta.hsdf.xml $M --safety data/safety_rasta.xml $PAT -o out/p_rasta.dzn
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta.xml $PAT -o out/p_rasta_noiso.dzn
# regression: same inputs as the Phase-3 instance, but through the pattern
# machinery with every actor forced to `none`. Must reproduce it exactly.
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta.xml $PAT \
   --force-no-patterns -o out/p_none.dzn
# systematic-fault variant: selects a different pattern set entirely
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta_sw.xml $PAT \
   -o out/p_sw.dzn

# --- Phase 4 demonstration: two structurally identical patterns that differ
#     ONLY in placement, selected by the fault model ---
ST="--patterns data/patterns_strict.yaml"
for fm in random_hw systematic_sw; do
  sed "s/fault_model=\"[a-z_]*\"/fault_model=\"$fm\"/" data/safety_rasta.xml \
    | sed 's|sil="3"|sil="2"|g' > data/safety_rasta_$fm.xml
  $B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta_$fm.xml $ST \
     -o out/d_$fm.dzn
done
echo "rebuilt $(ls out/*.dzn | wc -l) instances"

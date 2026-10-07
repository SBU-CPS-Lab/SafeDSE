#!/usr/bin/env bash
# Rebuild every .dzn in out/ from its XML sources. Run after any front-end
# change, otherwise older instances lack the newest parameters and the model
# fails with "variable X must be defined".
set -e
cd "$(dirname "$0")/.."

# Clear out/ first. Without this an instance that is renamed or dropped from
# this script survives in out/ forever, and because tests/run_tests.py globs
# out/*.dzn it keeps being solved against a model that has since grown new
# parameters. That is how out/c_sobel.dzn -- superseded by c_a_sobel.dzn --
# came to be a standing "NOSOL" failure in the crosscheck group: not a
# modelling bug, an unswept artefact masquerading as one.
rm -f out/*.dzn

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

# --- identical inventory, different FCR granularity (symmetry-breaking cost) ---
for pf in mixed mixed_flat; do
  $B --app data/apps/d_jpegEnc1.sdf.xml --platform data/platform/$pf.xml \
     --wcets data/WCETs_mixed.xml --constraints data/desConst.xml \
     --cost-model data/cost_model.xml -o out/m_$pf.dzn
done

# --- safety without patterns: isolation, promotion, cost profiles ---
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

# --- pattern superposition ---
PAT="--patterns data/patterns.yaml"
$B --app data/apps/c_rasta.hsdf.xml $M --safety data/safety_rasta.xml $PAT -o out/p_rasta.dzn
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta.xml $PAT -o out/p_rasta_noiso.dzn
# regression: same inputs as the pattern-free instance, but through the pattern
# machinery with every actor forced to `none`. Must reproduce it exactly.
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta.xml $PAT \
   --force-no-patterns -o out/p_none.dzn
# systematic-fault variant: selects a different pattern set entirely
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta_sw.xml $PAT \
   -o out/p_sw.dzn

# --- demonstration: two structurally identical patterns that differ
#     ONLY in placement, selected by the fault model ---
ST="--patterns data/patterns.yaml"
for fm in random_hw systematic_sw; do
  sed "s/fault_model=\"[a-z_]*\"/fault_model=\"$fm\"/" data/safety_rasta.xml \
    | sed 's|sil="3"|sil="2"|g' > data/safety_rasta_$fm.xml
  $B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta_$fm.xml $ST \
     -o out/d_$fm.dzn
done

# --- full Koopman catalogue under each fault model ---
python3 tools/mkwcets.py --app data/apps/c_rasta.hsdf.xml --platform data/platform/mixed_3type.xml --patterns data/patterns.yaml -o data/WCETs_3type.xml >/dev/null
T3="--platform data/platform/mixed_3type.xml --wcets data/WCETs_3type.xml --constraints data/desConst.xml --cost-model data/cost_model.xml"
for fm in random_hw systematic_sw both; do
  sed "s/fault_model=\"[a-z_]*\"/fault_model=\"$fm\"/" data/safety_rasta.xml > data/safety_fm_$fm.xml
done
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_fm_random_hw.xml $PAT -o out/f_random_hw.dzn
$B --app data/apps/c_rasta.hsdf.xml $T3 --safety data/safety_fm_systematic_sw.xml $PAT -o out/f_sw3.dzn
$B --app data/apps/c_rasta.hsdf.xml $T3 --safety data/safety_fm_both.xml $PAT -o out/f_both3.dzn
for fm in random_hw systematic_sw; do
  $B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta_$fm.xml $PAT -o out/d_$fm.dzn
done
$B --app data/rosvall/a_sobel.hsdf.xml --app data/rosvall/c_rasta.hsdf.xml $R -o out/r_2app.dzn
$B --app data/rosvall/a_sobel.hsdf.xml --app data/rosvall/b_susan.hsdf.xml \
   --app data/rosvall/c_rasta.hsdf.xml $R -o out/r_3app.dzn

# --- TDMA communication ---
for a in a_sobel b_susan c_rasta; do
  $B --app data/rosvall/$a.hsdf.xml $R --comm tdma -o out/c_$a.dzn
done
$B --app data/apps/c_rasta.hsdf.xml $NI --safety data/safety_rasta.xml $PAT --comm tdma -o out/c_pat.dzn
echo "rebuilt $(ls out/*.dzn | wc -l) instances"
# patterns AND communication together -- the composition that did not work
# before communication actors were removed from the processor static order
$B --app data/rosvall/a_sobel.hsdf.xml --platform data/rosvall/platform.xml \
   --wcets data/rosvall/WCETs_pat.xml --constraints data/rosvall/desConst.xml \
   --cost-model data/cost_model.xml --safety data/safety_sobel3.xml \
   $PAT --comm tdma -o out/pc_sobel.dzn
echo "rebuilt $(ls out/*.dzn | wc -l) instances"

# Explicit voter (docs/design.md#voters). Built from a SEPARATE catalogue:
# nvp_three_version is not in data/patterns.yaml because it is expensive enough
# to move every existing regression optimum, which is a decision independent of
# making it work. mixed_4type is needed because N mutually diverse components
# need N core types EACH certifiable at their SIL, and the 3-type platform has
# only two above SIL 2.
python3 tools/mkwcets.py --app data/apps/c_rasta.hsdf.xml \
   --platform data/platform/mixed_4type.xml \
   --patterns data/patterns_explicit_voter_demo.yaml \
   -o data/WCETs_4type.xml >/dev/null
$B --app data/apps/c_rasta.hsdf.xml --platform data/platform/mixed_4type.xml \
   --wcets data/WCETs_4type.xml --constraints data/desConst.xml \
   --cost-model data/cost_model.xml --safety data/safety_fm_both.xml \
   --patterns data/patterns_explicit_voter_demo.yaml -o out/v_nvp.dzn

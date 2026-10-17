// SPDX-License-Identifier: Apache-2.0
#include "wifi_feature_flags.h"
#include <cstdio>
using namespace aidl::android::hardware::wifi;
int main(){
    feature_flags::WifiFeatureFlags flags;
    auto modes=flags.getChipModes(true);
    // The actual AOSP dynamic-matrix replacement uses kV3. Keeping that ID
    // from initial enumeration prevents configureChip() from becoming stale.
    if(modes.size()!=1||modes[0].id!=feature_flags::chip_mode_ids::kV3){
        fprintf(stderr,"WIFI_MODE_INVARIANT_FAIL: initial mode must survive dynamic V3 reload\n");return 1;
    }
    if(modes[0].availableCombinations.size()!=1||modes[0].availableCombinations[0].limits.size()!=1){return 2;}
    auto limit=modes[0].availableCombinations[0].limits[0];
    if(limit.maxIfaces!=1||limit.types.size()!=1||limit.types[0]!=IfaceConcurrencyType::STA)return 3;
    puts("M1_WIFI_MODE_INVARIANT_PASS: initial mode ID matches actual dynamic V3 replacement; initial limit=one STA");return 0;
}

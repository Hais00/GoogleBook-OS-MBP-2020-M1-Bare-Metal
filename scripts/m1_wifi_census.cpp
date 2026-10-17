// SPDX-License-Identifier: Apache-2.0
#include "m1_wifi_linux.h"
#include <cstdio>
int main(){
    googlebook::wifi::Interface primary;googlebook::wifi::Phy phy;
    int error=googlebook::wifi::nativeRadio(primary,phy);if(error){printf("M1_WIFI_CENSUS_ERROR=%d\n",error);return 1;}
    printf("M1_WIFI_PRIMARY name=%s ifindex=%u wiphy=%u iftypes=%llx\n",primary.name.c_str(),primary.index,primary.phy,(unsigned long long)phy.types);
    for(auto c:phy.channels)printf("CHANNEL mhz=%u disabled=%d noInitiate=%d\n",c.mhz,c.disabled,c.noInitiate);
    for(auto v:phy.ciphers)printf("CIPHER=%08x\n",v);
    for(auto v:phy.akms)printf("AKM=%08x\n",v);
    for(auto c:phy.combinations){printf("COMBINATION max=%u channels=%u",c.maximum,c.channels);for(auto l:c.limits)printf(" limit=%u/%llx",l.maximum,(unsigned long long)l.types);puts("");}
    printf("EXT_FEATURES=");for(auto v:phy.extendedFeatures)printf("%02x",v);puts("");return 0;
}

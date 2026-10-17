#!/usr/bin/env python3
"""Correct existing power hints using the actual M1 cpufreq owner census."""
import hashlib
import json
from pathlib import Path
import re
from project_paths import WORK, LARGE_WORK


def main():
    evidence = LARGE_WORK/'trial-native-egl-kernel21-audio-gpio/owner-inventory-shell.txt'
    text = evidence.read_text()
    base = WORK/'vendor-codec-stage/etc/powerhint.json'
    target = WORK/'vendor-linux-cleanup-stage/etc/powerhint.json'
    original = base.read_bytes()
    profile = json.loads(original)
    policies = {}
    for number in (0, 4):
        root = f'/sys/devices/system/cpu/cpufreq/policy{number}'
        def observed(name):
            matches = re.findall(r'^GOS_OWNER_FILE path='+re.escape(root+'/'+name)+r' rc=0 value=([^\n\[]+)', text, re.M)
            assert len(matches) == 1, 'Missing/ambiguous actual owner field '+name
            return matches[0].strip()
        assert observed('scaling_driver') == 'apple-cpufreq'
        freq = [int(x) for x in observed('scaling_available_frequencies').split()]
        assert freq == sorted(set(freq)) and freq
        assert min(freq) == int(observed('cpuinfo_min_freq'))
        assert max(freq) == int(observed('cpuinfo_max_freq'))
        assert {'performance', 'schedutil'} <= set(observed('scaling_available_governors').split())
        policies[number] = {'path': root, 'frequencies_khz': freq}
    names = {n['Name']: n for n in profile['Nodes']}
    names['ScalingGovernor']['Values'] = ['performance', 'schedutil']
    names['ScalingGovernor']['DefaultIndex'] = 1
    for prefix, number in [('CPULittleCluster', 0), ('CPUBigCluster', 4)]:
        policy = policies[number]
        values = [str(n) for n in reversed(policy['frequencies_khz'])]
        for bound in ['Min', 'Max']:
            node = names[prefix+bound+'Freq']
            node.pop('Paths', None)
            node['Path'] = policy['path']+'/scaling_'+bound.lower()+'_freq'
            node['Values'] = values
            node['DefaultIndex'] = len(values)-1 if bound == 'Min' else 0
    # An explicit initial board policy, not an assertion of measured energy savings.
    # This OPP is actually exported by the M1 performance cluster.
    low_power_max = 2388000
    assert low_power_max in policies[4]['frequencies_khz']
    for action in profile['Actions']:
        if action['PowerHint'] == 'LOW_POWER':
            assert action['Node'] == 'CPUBigClusterMaxFreq'
            action['Value'] = str(low_power_max)
        assert action['Value'] in names[action['Node']]['Values']
    result = (json.dumps(profile, indent=2)+'\n').encode()
    assert target.read_bytes() in (original, result), 'Unrelated power profile edits: refusing overwrite'
    target.write_bytes(result)
    receipt = {'evidence': str(evidence), 'evidence_sha256': hashlib.sha256(evidence.read_bytes()).hexdigest(),
               'policies': policies, 'staged': str(target), 'source_sha256': hashlib.sha256(original).hexdigest(),
               'staged_sha256': hashlib.sha256(result).hexdigest(), 'physical_device_written': False,
               'fixed': ['absent cpu8 path', 'non-M1 OPP tables', 'unsupported walt/powersave governor defaults'],
               'initial_policy': {'low_power_performance_max_khz': low_power_max},
               'scope': 'Existing libperfmgr config only. Physical hint execution, energy/thermal characterization and other OEM power services still require qualification.'}
    (WORK/'m1-power-profile.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('M1_POWER_PROFILE_STAGED_FROM_ACTUAL_OWNER', target)


if __name__ == '__main__':
    main()

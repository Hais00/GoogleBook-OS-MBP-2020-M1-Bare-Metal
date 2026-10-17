#!/usr/bin/env python3
"""Remove unavailable Qualcomm codecs from the M1 vendor product configuration."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from project_paths import WORK, SYSTEM_ORIGINAL


def apply(stage):
    stage = stage.resolve()
    assert stage.parent == WORK.resolve() and stage.name in (
        'vendor-codec-stage', 'vendor-linux-cleanup-stage')
    framework = ET.parse(SYSTEM_ORIGINAL/'etc/vintf/manifest/manifest_media_c2_software.xml')
    assert any(h.findtext('name') == 'android.hardware.media.c2' and
               h.get('format') == 'aidl' and
               h.findtext('fqname') == 'IComponentStore/software'
               for h in framework.getroot().findall('hal'))
    removed = []
    # The old service is disabled, but this fragment still makes clients wait
    # indefinitely for IComponentStore/default before trying the software store.
    for name in ('etc/vintf/manifest/c2_manifest_aidlv2_vendor.xml',
                 'etc/init-disabled/vendor.qti.media.c2@1.0-service.rc.disabled',
                 'bin/hw/vendor.qti.media.c2@1.0-service'):
        for relative in (name, name+'.fsv_meta'):
            p = stage/relative
            if p.exists():
                removed.append({'path': relative, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
                p.unlink()
    changed = []
    for path in sorted((stage/'etc').glob('media_codecs*.xml')):
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        tree = ET.parse(path, parser=parser)
        count = 0
        for parent in tree.iter():
            for node in list(parent):
                name = node.get('name', '')
                if node.tag == 'MediaCodec' and name.lower().startswith(
                        ('omx.qcom.', 'omx.qti.', 'c2.qti.', 'c2.qcom.')):
                    parent.remove(node)
                    count += 1
        if count:
            tree.write(path, encoding='utf-8', xml_declaration=True)
            changed.append({'path': str(path.relative_to(stage)), 'removed_codecs': count})
    # Select the supplied AOSP software definitions rather than the legacy OMX
    # product list. Reuse the file inode so its Android security label is kept.
    main = stage/'etc/media_codecs.xml'
    text = main.read_text()
    header = text[:text.index('<MediaCodecs>')]
    main.write_text(header+'<MediaCodecs>\n    <Include href="media_codecs_google_c2.xml" />\n</MediaCodecs>\n')
    for path in (stage/'etc').glob('media_codecs*.xml'):
        tree = ET.parse(path)
        for node in tree.iter('MediaCodec'):
            assert not node.get('name', '').lower().startswith(
                ('omx.qcom.', 'omx.qti.', 'c2.qti.', 'c2.qcom.'))
    for path in (stage/'etc/vintf').rglob('*.xml'):
        for h in ET.parse(path).getroot().findall('hal'):
            assert h.findtext('name') != 'android.hardware.media.c2', path
    software_names = []
    for name in ('audio', 'video'):
        path = stage/f'etc/media_codecs_google_c2_{name}.xml'
        for codec in ET.parse(path).iter('MediaCodec'):
            assert codec.get('name', '').startswith('c2.android.'), codec.attrib
            software_names.append(codec.get('name'))
    note = {'stage': str(stage), 'removed': removed, 'changed': changed,
            'software_codec_names': sorted(set(software_names)),
            'software_provider': 'android.hardware.media.c2.IComponentStore/software',
            'framework_software_manifest_unchanged': True,
            'software_runtime_and_media_decode_qualified': False,
            'full_vintf_compatibility_qualified': False,
            'physical_installation_performed': False}
    (WORK/(stage.name+'-software-codecs.json')).write_text(json.dumps(note, indent=2)+'\n')
    print(json.dumps(note, indent=2))


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', type=Path)
    apply(p.parse_args().stage)

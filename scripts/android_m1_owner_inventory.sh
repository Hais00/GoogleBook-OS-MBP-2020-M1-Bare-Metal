#!/system/bin/sh
# Read-only owner metadata. No PCM playback, interface changes or PMGR access.
echo GOS_M1_OWNER_INVENTORY_BEGIN
id
uname -a

gos_read_owner_file() {
    for gos_owner_path in "$@"; do
        # stat itself may be denied. Preserve cat's actual error rather than
        # silently treating an unreadable owner attribute as an absent device.
        gos_owner_value=$(cat "$gos_owner_path" 2>&1)
        gos_owner_rc=$?
        printf 'GOS_OWNER_FILE path=%s rc=%s value=%s\n' "$gos_owner_path" "$gos_owner_rc" "$gos_owner_value"
    done
}

gos_read_owner_file /proc/asound/cards /proc/asound/pcm /proc/asound/version
for gos_card in /sys/class/sound/card*; do
    [ -d "$gos_card" ] || continue
    printf 'GOS_ALSA_CARD path=%s device=%s driver=%s\n' "$gos_card" \
        "$(readlink "$gos_card/device" 2>&1)" "$(readlink "$gos_card/device/driver" 2>&1)"
    gos_read_owner_file "$gos_card/id"
done
ls -lZ /dev/snd 2>&1
gos_read_owner_file /sys/module/*macaudio*/parameters/please_blow_up_my_speakers

for gos_policy in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -d "$gos_policy" ] || continue
    gos_read_owner_file "$gos_policy/related_cpus" "$gos_policy/affected_cpus" \
        "$gos_policy/scaling_driver" "$gos_policy/cpuinfo_min_freq" \
        "$gos_policy/cpuinfo_max_freq" "$gos_policy/scaling_available_frequencies" \
        "$gos_policy/scaling_available_governors" "$gos_policy/scaling_governor"
done

for gos_netdev in /sys/class/net/*; do
    [ -e "$gos_netdev/phy80211" ] || continue
    printf 'GOS_WIFI_OWNER path=%s phy=%s driver=%s\n' "$gos_netdev" \
        "$(readlink "$gos_netdev/phy80211" 2>&1)" "$(readlink "$gos_netdev/device/driver" 2>&1)"
    gos_read_owner_file "$gos_netdev/ifindex" "$gos_netdev/operstate" "$gos_netdev/type"
done
gos_read_owner_file /sys/class/typec/port*/data_role /sys/class/typec/port*/power_role \
    /sys/class/typec/port*/port_type /sys/class/udc/*/current_speed /sys/class/udc/*/state

for gos_input in /sys/class/input/event*; do
    [ -d "$gos_input" ] || continue
    gos_read_owner_file "$gos_input/device/name" "$gos_input/device/inhibited"
done
echo GOS_M1_OWNER_INVENTORY_END

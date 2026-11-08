#!/usr/bin/env python3
"""build.sh: Tigris-Ladedienst ins Image einbauen (idempotent)."""
import os
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = os.path.join(R, "build.sh"); s = open(p).read()
if "patch_charge" not in s:
    s = s.replace('''    patch_wifi "$mnt"''', '''    patch_wifi "$mnt"
    patch_charge "$mnt"''', 1)
    s = s.replace('''patch_phosh() {''', '''# Laden (iPhone 7): Ladechip Tigris steht ohne iOS-Treiber auf 90 mA USB-Eingangslimit –
# der Akku entlädt sich trotz Kabel. tigris-charge hebt das Limit (bis 900 mA, mit
# Spannungseinbruch-Kontrolle) und setzt es nach erneutem Anstecken wieder.
patch_charge() {
    local m="$1"
    c_info "Laden: tigris-charge-Dienst installieren …"
    sudo install -Dm755 "$SCRIPT_DIR/tools/tigris-charge.py" "$m/usr/local/sbin/tigris-charge"
    sudo install -Dm644 "$SCRIPT_DIR/tools/tigris-charge.service" "$m/etc/systemd/system/tigris-charge.service"
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    sudo ln -sf ../tigris-charge.service "$m/etc/systemd/system/multi-user.target.wants/tigris-charge.service"
    c_ok "tigris-charge eingerichtet."
}

patch_phosh() {''', 1)
    open(p, "w").write(s); print("build.sh: patch_charge ergänzt")

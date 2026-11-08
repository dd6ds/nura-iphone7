#!/bin/sh
# Auf dem iPhone (oder per chroot/Mount-Punkt $1) ausführen:
# Phosh für iPhone ohne Modem/WLAN/Touch/GPU entschlacken und Timeouts anheben.
R="${1:-}"
set -e

# 1) Benutzersitzung darf langsam starten (Netboot + Software-Rendering)
mkdir -p "$R/etc/systemd/system/user@.service.d"
printf '[Service]\nTimeoutStartSec=infinity\n' > "$R/etc/systemd/system/user@.service.d/iphone-timeout.conf"
mkdir -p "$R/etc/systemd/user/mobi.phosh.Shell.service.d" "$R/etc/systemd/user/mobi.phosh.OSK.service.d"
printf '[Service]\nTimeoutStartSec=600\n' > "$R/etc/systemd/user/mobi.phosh.Shell.service.d/timeout.conf"
printf '[Service]\nTimeoutStartSec=600\n' > "$R/etc/systemd/user/mobi.phosh.OSK.service.d/timeout.conf"

# 2) User-Dienste ohne passende Hardware maskieren
for u in cellbroadcastd.service mmsd-tng.service vvmd.service sm.puri.Chatty-daemon.service \
         obex.service usb-moded-notify.service mobi.phosh.PhoshTour-first-login.service \
         udiskie.service fbd-alert-slider.service localsearch-3.service \
         evolution-source-registry.service evolution-addressbook-factory.service \
         evolution-calendar-factory.service goa-daemon.service goa-identity-service.service; do
    ln -sf /dev/null "$R/etc/systemd/user/$u"
done
for u in ModemManager.service bluetooth.service eg25-manager.service; do
    ln -sf /dev/null "$R/etc/systemd/system/$u"
done

# 3) Autostart-Einträge ausblenden
for a in mmsd.desktop org.gnome.Calls-daemon.desktop org.gnome.Evolution-alarm-notify.desktop \
         org.kop316.vvmplayer-daemon.desktop vvmd.desktop sm.puri.Chatty-daemon.desktop \
         geoclue-demo-agent.desktop localsearch-3.desktop mobi.phosh.PhoshTour-first-login.desktop \
         mpris-proxy.desktop udiskie.desktop org.gnome.SettingsDaemon.Smartcard.desktop \
         org.gnome.SettingsDaemon.PrintNotifications.desktop org.gnome.SettingsDaemon.Wwan.desktop \
         org.gnome.SettingsDaemon.UsbProtection.desktop; do
    [ -e "$R/etc/xdg/autostart/$a" ] || continue
    if ! grep -q '^Hidden=true' "$R/etc/xdg/autostart/$a"; then
        printf '\nHidden=true\n' >> "$R/etc/xdg/autostart/$a"
    fi
done
echo "phosh-slim: fertig"

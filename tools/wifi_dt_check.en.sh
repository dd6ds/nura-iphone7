#!/bin/sh
# Check Wi-Fi entries in the running device tree (run on the iPhone)
N=/proc/device-tree/soc/pcie@610000000/pci@2,0/wifi@0,0
echo "Eigenschaften: $(ls $N | tr '\n' ' ')"
echo "board-type   : $(tr -d '\0' < $N/brcm,board-type)"
echo "antenna-sku  : $(tr -d '\0' < $N/apple,antenna-sku 2>/dev/null)"
echo "MAC          : $(od -An -tx1 $N/local-mac-address | tr -s ' ' ':' | sed 's/^://')"
[ -f $N/brcm,cal-blob ] && echo "cal-blob     : $(wc -c < $N/brcm,cal-blob) Bytes, Kopf $(head -c 4 $N/brcm,cal-blob)" || echo "cal-blob     : FEHLT"
echo "wifi0-Alias  : $(tr -d '\0' < /proc/device-tree/aliases/wifi0 2>/dev/null)"

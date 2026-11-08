# Interner Speicher iPhone 7 (d101) – Stand 2026-11-08

- Controller: Apple S3E/ANS2-NVMe, PCI 106b:2002, an apcie-Port 0 (ADT pci-bridge0/s3e, nvme-mode).
  PERST# GPIO 12, CLKREQ GPIO 16, max. Gen3, keine eigenen Versorgungs-GPIOs.
- DART: dart-apcie0 @0x601008000 (IRQ 271), vm 0x80000000.. (Größe 0x3C000000).
- NVMMU/SART: nvme-mmu0 @0x601004000 (IRQ 272), virtual-base 0x40000000, 64 Tags, 256 SGL-Einträge.
  Live-ADT: sart-region = PA 0x87EE00000, Größe 0x1200000; sart-virtual-base = 0xBC000000
  (= s3e nvme-scratch-virt-region). Der Bereich liegt oberhalb des Linux-RAM (endet 0x87d18xxxx).
- Sandcastle (Corellium, Linux 5.4): nvme/host/hx.c + pcie-hx.c (NVMMU "flat DMA",
  NVME_CMD_HX_FLATDMA = Bit 5 in cmd flags), Quirks HX|SINGLE_VECTOR|SHARED_TAGS. Quellen in src/sc/nvme.
- Stufe 1 (r111): Port 0 + SART im PCIe-Treiber (Patch 0015), nvme-pci-Quirk APPLE_EMBEDDED
  (Scratch-Übergabe vor CC.EN, max. 256 Sektoren, Patch 0016), DT Patch 0017.
  Bewusst OHNE NVMMU – Daten per Standard-PRP über das statische DART-Fenster (wie WLAN).
  Falls die ANS-Firmware PRPs ablehnt -> Stufe 2: NVMMU/TCB wie Sandcastle.
- Sicherheit: nvme-Modul per modprobe.d gesperrt, Test per tools/nvme_test.sh (setzt Namespaces RO).
  Notschalter: NVME_BOOT=0 ./build.sh payload  (-> pcie_apple_t8010.skip_ports=0x1).
- Partitionierung (später, unter iOS 15 mit palera1n): resize_apfs + gdisk aus HoolockLinux/docs.

## Testergebnisse
- r111 (PRP, ohne Quirks): GPT gelesen (nvme0n1 29,8 GB + p1, n2..n7 klein), dann Absturz bei parallelen
  Lesezugriffen (CSTS=0xffffffff). Nach Absturz kommt der Link nur per iPhone-Neustart wieder.
- r111 + quirks skip_cid_gen,identify_cns: 4-KiB-Einzelzugriffe überall ok, APFS-Magie "NXSB" korrekt.
- r112 (ohne SGL): 4 KiB ok, 32 KiB -> Absturz. => alles mit PRP2/PRP-Liste legt den ANS lahm.
- r113: NVMMU nach Sandcastle (TCB je Tag, Seitenliste physisch, Flag-Bit 5, PRP1 = 0x40000000+(tag<<23)).
  Modulparameter nvme.apple_nvmmu=0 schaltet zurück auf PRP (Vergleich ohne Neubau).
- r113 Lesen: alle Stufen ok, 2 GiB mit 202 MB/s, Prüfsummen stabil.
- iOS-Container per SSHRD-Ramdisk (iOS 15.8) + resize_apfs auf 4882812 Blöcke (20 GB) verkleinert,
  iOS startet danach normal. GPT noch unverändert (p1 6..7812494).
- Erster Schreibtest r113: 1 MiB mit bs 4 KiB und 128 KiB geschrieben und identisch zurückgelesen.
  Aber mit io_queue_depth=64: I/O-Tags 52/54 bekamen nie einen Interrupt ("timeout, completion polled",
  je 30 s) -> System zäh. Sandcastle nutzt nur 36 Tags. r114: q_depth <= 36 (I/O-Tags 32..35).
- Achtung: Modul nvme lässt sich nicht entladen (kein MODULE_UNLOAD) -> Parameter nur beim ersten Laden.
- Lange Befehle per ssh hängen bei NBD-Stockungen; Tests daher per systemd-run + Log in /dev/shm.

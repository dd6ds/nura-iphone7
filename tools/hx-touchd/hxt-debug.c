// SPDX-License-Identifier: GPL-2.0-or-later
/* Debug-Werkzeug: hx-touchd-Init + Rohpakete im Userspace lesen/ausgeben.
 * Aufruf: hxt-debug <pers> <mtprops> <syscfg> [sekunden] [noaf] */
#include <time.h>
#define main hxtd_main
#include "hx-touchd.c"
#undef main

static void hex(const char *t, const unsigned char *b, unsigned n)
{
    unsigned i;
    printf("%s [%u]:", t, n);
    for(i = 0; i < n; i++) printf("%s%02x", (i % 32) ? " " : "\n   ", b[i]);
    printf("\n"); fflush(stdout);
}

static unsigned tag;

static int read_frame(int fd)
{
    unsigned char p[16] = { 0xEB, 1 + tag }, d[512];
    unsigned len;
    p[14] = 0xEC + tag;
    ioctl(fd, HXT_IOC_SET_CS, 1); usleep(1000);
    if(write(fd, p, 16) != 16 || read(fd, p, 16) != 16) return -1;
    ioctl(fd, HXT_IOC_SET_CS, 0); usleep(1000);
    hex("  hdr-rsp", p, 16);
    memset(d, 0xA5, 64);
    ioctl(fd, HXT_IOC_SET_CS, 1); usleep(1000);
    if(write(fd, d, 64) != 64 || read(fd, d, 64) != 64) return -1;
    len = d[2] | (d[3] << 8);
    if((d[0] & 0xFE) == 0xEA && len > 59 && len < 400) {
        unsigned rest = len - 59;
        memset(d + 64, 0, rest);
        if(write(fd, d + 64, rest) != (int)rest || read(fd, d + 64, rest) != (int)rest) return -1;
        hex("  frame", d, 64 + rest);
    } else
        hex("  frame", d, 64);
    ioctl(fd, HXT_IOC_SET_CS, 0); usleep(1000);
    if((d[0] & 0xFE) == 0xEA) tag = !tag;
    return 0;
}

int main(int argc, char *argv[])
{
    int fd, secs = argc > 4 ? atoi(argv[4]) : 30, n = 0;
    unsigned char d9[64], buf[256];
    unsigned len, r;
    time_t t0;

    mt_firmware = mtfw_load_firmware(argv[1], argv[2], argv[3]);
    if(!mt_firmware) return 1;
    fd = open("/dev/hx-touch", O_RDWR);
    if(fd < 0) { perror("open"); return 1; }
    if(bootload(fd)) return 1;
    printf("bootload ok, mt_type=%u\n", mt_type);
    send_wake(fd);
    len = sizeof(d9);
    r = read_report(fd, 0xD9, d9, &len);
    printf("report D9 -> %u\n", r);
    if(!r) hex("  D9", d9, len < 64 ? len : 64);
    unsigned lo = getenv("RLO") ? strtoul(getenv("RLO"),0,0) : 0xA0, hi = getenv("RHI") ? strtoul(getenv("RHI"),0,0) : 0xFF;
    for(r = getenv("NOENUM") ? 0x100 : lo; r <= hi; r++) {  /* lesbare Reports auflisten */
        unsigned l = sizeof(buf);
        if(r == 0xE1 || (r >= 0xE2 && r <= 0xEE)) continue;
        if(read_report(fd, r, buf, &l) == 0) {
            char t[16]; snprintf(t, sizeof t, "  rpt %02X", r);
            hex(t, buf, l < 48 ? l : 48);
        }
    }
    if(getenv("DEVINFO")) {
        unsigned char c[16] = { MT_DEV_INFO }, rsp[16];
        send_z2(fd, c, rsp); hex("  E2 rsp1", rsp, 16);
        memset(c, 0, 16); c[0] = MT_CMD_LAST;
        send_z2(fd, c, rsp); hex("  E2 rsp2", rsp, 16);
        memset(c, 0, 16);
        send_z2(fd, c, rsp); hex("  E2 rsp3", rsp, 16);
    }
    if(getenv("PF")) {   /* Frames pollen ohne IRQ */
        int it, n = 0; unsigned char p[16], d[64];
        for(it = 0; it < atoi(getenv("PF")) * 5; it++) {
            memset(p, 0, 16); p[0] = 0xEB; p[1] = 1 + tag; p[14] = 0xEC + tag;
            ioctl(fd, HXT_IOC_SET_CS, 1); usleep(500);
            write(fd, p, 16); read(fd, p, 16);
            ioctl(fd, HXT_IOC_SET_CS, 0); usleep(500);
            memset(d, 0xA5, 64);
            ioctl(fd, HXT_IOC_SET_CS, 1); usleep(500);
            write(fd, d, 64); read(fd, d, 64);
            ioctl(fd, HXT_IOC_SET_CS, 0);
            if((d[0] & 0xFE) == 0xEA) {
                tag = !tag;
                if(n++ < 25) { char t[24]; snprintf(t, sizeof t, "t=%.1f frame", it / 5.0); hex(t, d, 48); }
            } else if(it % 25 == 0) { printf("t=%.1f leer: %02x %02x %02x %02x | hdr %02x %02x %02x\n", it / 5.0, d[0], d[1], d[2], d[3], p[0], p[1], p[2]); fflush(stdout); }
            usleep(200000);
        }
        printf("frames: %d\n", n);
        return 0;
    }
    if(getenv("EXP")) {   /* Experiment: Zustand vor/nach Aktion */
        unsigned char b[128]; unsigned l, k, sum, it; const char *e = getenv("EXP");
        for(it = 0; it < 8; it++) {
            if(!strcmp(e, "wake")) send_wake(fd);
            if(!strncmp(e, "rpt:", 4) && it == 1) {      /* rpt:RR:VV */
                unsigned rr = strtoul(e + 4, 0, 16), vv = strtoul(e + 7, 0, 16); unsigned char c = vv;
                printf("write %02X=%02X -> %d\n", rr, vv, write_report(fd, rr, &c, 1));
            }
            usleep(500000);
            l = sizeof(b); sum = 0;
            if(!read_report(fd, 0x20, b, &l)) for(k = 0; k < l && k < sizeof(b); k++) sum += b[k];
            l = sizeof(b);
            if(!read_report(fd, 0x72, b, &l)) {
                printf("it%u raw=%u st:", it, sum);
                for(k = 0; k < 4; k++) printf(" %u", b[8*k] | b[8*k+1] << 8 | b[8*k+2] << 16);
                printf("\n"); fflush(stdout);
            }
        }
        return 0;
    }
    if(getenv("AFV")) {
        int v = atoi(getenv("AFV"));
        if(v >= 0) { unsigned char c = v; printf("write AF=%02x -> %d\n", c, write_report(fd, 0xAF, &c, 1)); }
        sleep(3);
        { unsigned char b[64]; unsigned l = 64, k;
          if(!read_report(fd, 0x72, b, &l)) { printf("  72 ms/zaehler je Zustand:");
            for(k = 0; k < 6; k++) printf(" [%u]%u/%u", k, b[8*k] | b[8*k+1] << 8 | b[8*k+2] << 16, b[8*k+4]); printf("\n"); }
          l = 64; if(!read_report(fd, 0xAF, b, &l)) printf("  AF jetzt %02x\n", b[0]); }
        return 0;
    }
    if(argc <= 5 && mt_type == 2) {
        printf("write AF=00 -> %d\n", write_report(fd, 0xAF, (unsigned char *)"\x00", 1));
    }
    if(getenv("T1W")) {
        unsigned char b[64]; unsigned l;
        printf("write 9D -> %d\n", write_report(fd, 0x9D, (unsigned char *)"\x01\x00\x00\x00\x00\x00\x00\x00", 8));
        printf("write BF -> %d\n", write_report(fd, 0xBF, (unsigned char *)"\x9D\x81\x09\x00", 4));
        printf("write AF -> %d\n", write_report(fd, 0xAF, (unsigned char *)"\x00", 1));
        l = 64; if(!read_report(fd, 0xBF, b, &l)) hex("  BF jetzt", b, l);
        l = 64; if(!read_report(fd, 0x9D, b, &l)) hex("  9D jetzt", b, l);
        l = 64; if(!read_report(fd, 0x72, b, &l)) hex("  72 jetzt", b, l > 16 ? 16 : l);
    }
    if(getenv("POLL")) {
        static const unsigned char ids[] = { 0x72, 0x2D, 0x3A, 0x56, 0x7E, 0x28, 0x2A, 0x49, 0x20 };
        static unsigned char last[sizeof(ids)][128]; static unsigned lastl[sizeof(ids)];
        unsigned char b[128]; unsigned l, k, sum; int it;
        for(it = 0; it < atoi(getenv("POLL")) * 2; it++) {
            for(k = 0; k < sizeof(ids); k++) {
                l = sizeof(b);
                if(read_report(fd, ids[k], b, &l)) continue;
                if(l > sizeof(b)) l = sizeof(b);
                if(ids[k] == 0x20) {   /* Rohbild: nur Summe ausgeben */
                    for(sum = 0, r = 0; r < l; r++) sum += b[r];
                    printf("t=%.1f 20 sum=%u\n", it / 2.0, sum);
                    continue;
                }
                if(l != lastl[k] || memcmp(b, last[k], l)) {
                    char t[32]; snprintf(t, sizeof t, "t=%.1f rpt %02X", it / 2.0, ids[k]);
                    hex(t, b, l > 48 ? 48 : l);
                    memcpy(last[k], b, l); lastl[k] = l;
                }
            }
            fflush(stdout);
            usleep(300000);
        }
        return 0;
    }
    printf("warte %d s auf IRQs – jetzt Display berühren …\n", secs); fflush(stdout);
    t0 = time(NULL);
    while(time(NULL) - t0 < secs) {
        ioctl(fd, HXT_IOC_SETUP_IRQ);
        if(ioctl(fd, HXT_IOC_WAIT_IRQ, 1000) == 0) {
            printf("IRQ #%d (t=%lds)\n", ++n, (long)(time(NULL) - t0));
            read_frame(fd);
            if(n > 40) break;
        }
    }
    printf("fertig: %d IRQs\n", n);
    return 0;
}

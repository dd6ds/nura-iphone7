/*
 * hide_ext_capture.so – LD_PRELOAD-Shim für wayvnc auf phoc ohne GPU.
 *
 * phoc (llvmpipe, simpledrm, kein Render-Node) bietet über
 * ext_image_copy_capture_v1 keine Puffer-Formate an -> wayvnc 0.10 bricht ab
 * ("No supported buffer formats were found"). Der Shim blendet die
 * ext-image-capture-Globals aus, sodass wayvnc auf zwlr_screencopy_v1
 * zurückfällt, das funktioniert.
 *
 * Bewusst ohne libc gebaut (-nostdlib), damit er unter musl (Alpine/Nura)
 * und glibc gleichermaßen lädt. dlsym/wl_proxy_get_class werden zur
 * Laufzeit aus dem Prozess aufgelöst.
 */
#define RTLD_NEXT ((void *)-1l)

struct wl_proxy;
typedef void (*generic_fn)(void);

extern void *dlsym(void *handle, const char *symbol);
extern const char *wl_proxy_get_class(struct wl_proxy *proxy);

typedef void (*global_fn)(void *data, struct wl_proxy *reg, unsigned name,
                          const char *iface, unsigned version);
typedef void (*global_remove_fn)(void *data, struct wl_proxy *reg, unsigned name);

struct registry_listener {
    global_fn global;
    global_remove_fn global_remove;
};

#define MAX_REG 16
static struct { struct wl_proxy *reg; const struct registry_listener *orig; } regs[MAX_REG];

static int str_eq(const char *a, const char *b)
{
    if (!a || !b) return 0;
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static const struct registry_listener *lookup(struct wl_proxy *reg)
{
    for (int i = 0; i < MAX_REG; i++)
        if (regs[i].reg == reg) return regs[i].orig;
    return 0;
}

static void filt_global(void *data, struct wl_proxy *reg, unsigned name,
                        const char *iface, unsigned version)
{
    if (str_eq(iface, "ext_image_copy_capture_manager_v1") ||
        str_eq(iface, "ext_output_image_capture_source_manager_v1"))
        return; /* verstecken -> wayvnc nimmt zwlr_screencopy */
    const struct registry_listener *o = lookup(reg);
    if (o && o->global) o->global(data, reg, name, iface, version);
}

static void filt_global_remove(void *data, struct wl_proxy *reg, unsigned name)
{
    const struct registry_listener *o = lookup(reg);
    if (o && o->global_remove) o->global_remove(data, reg, name);
}

static const struct registry_listener filt = { filt_global, filt_global_remove };

typedef int (*add_listener_fn)(struct wl_proxy *, generic_fn *, void *);

int wl_proxy_add_listener(struct wl_proxy *proxy, generic_fn *impl, void *data)
{
    static add_listener_fn real;
    if (!real) real = (add_listener_fn)dlsym(RTLD_NEXT, "wl_proxy_add_listener");

    if (str_eq(wl_proxy_get_class(proxy), "wl_registry")) {
        for (int i = 0; i < MAX_REG; i++) {
            if (!regs[i].reg || regs[i].reg == proxy) {
                regs[i].reg = proxy;
                regs[i].orig = (const struct registry_listener *)impl;
                return real(proxy, (generic_fn *)&filt, data);
            }
        }
    }
    return real(proxy, impl, data);
}

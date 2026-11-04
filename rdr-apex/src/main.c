/**
 * Red Dead Revolver - Recompiled Game Entry Point
 *
 * This is the executable that hosts the recompiled game code, on Windows and
 * on POSIX hosts (macOS). One boot sequence, host_main, is shared; the parts
 * that differ by host (the crash handler, the fatal-error dialog, the window,
 * the entry points) sit under #if defined(_WIN32) / #else.
 * It performs the following initialization sequence:
 *
 * 1. Install the crash handler for diagnostics (VEH on Windows,
 *    SIGBUS/SIGSEGV elsewhere)
 * 2. Load the original XBE file from disk
 * 3. Initialize the Xbox memory layout (map data sections to original VAs)
 * 4. Initialize the Xbox kernel replacement layer
 * 5. Set up game file paths for I/O redirection
 * 6. Initialize the kernel bridge (thunk table in Xbox memory)
 * 7. Initialize the stack pointer
 * 8. Call the game's original entry point (recompiled)
 *
 * Customize this file for your game:
 *   - Set YOUR_GAME_ENTRY_POINT to the XBE entry point address
 *   - Set YOUR_GAME_XBE_PATH to where the XBE file lives
 *   - Set YOUR_GAME_DIR to the game data directory
 *   - Add any CRT global pre-initialization your game needs
 *   - Customize the crash report for game-specific crash diagnosis
 *
 * XBE Details (fill in from xbe_parser output):
 *   Title:       Red Dead Revolver
 *   Title ID:    0x00000000
 *   Base addr:   0x00010000
 *   Entry point: 0x00000000
 *   Code size:   ~??? KB (.text)
 *   Sections:    ?? (list them)
 *   Kernel imports: ??
 */

#include "recomp_env.h"

#if defined(_WIN32)
#include <windows.h>
#include <dbghelp.h>
#else
/* <signal.h> already provides ucontext_t and the Darwin mcontext; including
 * <ucontext.h> directly is an #error on macOS without _XOPEN_SOURCE. The NT
 * types used below (BOOL, LONG, CALLBACK...) come from the toolkit's kernel.h
 * through <xbox/xboxrecomp.h>. */
#include <signal.h>
#include <dlfcn.h>
#include <unistd.h>
#include <pthread.h>
#endif
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

/* xboxrecomp runtime headers */
#include <xbox/xboxrecomp.h>
#include "video/video_player.h"   /* xbox_HostWindowSetTitle, xbox_HostWindowMain */
#include "usb/ohci.h"              /* xbox_OhciInit: the pad's USB controller */
#include "input/keyboard.h"        /* xbox_InputBind: mouse buttons onto the pad */
#include "input/mouse.h"
#include "input/host_pad.h"     /* xbox_InputLastDevice */
#include "input/input_map.h"
#include "input/input_names.h"
#include "kernel/nv2a_backend_common.h"   /* nv2a_host_opts_set: render scale, aniso */
#include "kernel/nv2a_tex_pack.h"         /* the texture pack, without the enhance layer */
#include "d3d/host_menu.h"                /* xbox_MenuAdd: the pack's F2 rows */

static void pack_menu_init(void);  /* the F2 row "Texturas mejoradas" */
static void fast_mode_from_ini(void);  /* "Modo experimental", before the walker starts */
static void fast_menu_init(void);      /* its F2 row */
#ifdef RECOMP_ENV_HAVE_ENHANCE_KEYS   /* the toolkit's opt-in enhancements layer */
#include "enhance.h"
#include "enhance_cfg.h"
#endif

/*
 * If xboxrecomp.h is not an umbrella header in your setup, include
 * the individual headers directly:
 *
 * #include "kernel.h"
 * #include "xbox_memory_layout.h"
 * #include "d3d8_xbox.h"
 * #include "dsound_xbox.h"
 * #include "xinput_xbox.h"
 */

/* ── Global register state (defined in xbox_memory_layout.c) ── */

/* RECOMP_TLS is not optional here. The runtime defines these thread-local, and
 * a plain `extern` referencing a __declspec(thread) variable does not resolve
 * to the calling thread's copy -- it resolves to the image's TLS template. The
 * host side then writes g_esp somewhere the generated code never reads, so the
 * guest starts with every register at zero and faults immediately, having
 * apparently ignored the setup that visibly ran. */
extern RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp;
extern RECOMP_TLS uint32_t g_ebx, g_esi, g_edi;
extern RECOMP_TLS uint32_t g_seh_ebp;
/* x87 and SSE state. Global for the same reason the volatile GPRs are: one
 * guest routine can lift to several C functions, so a value written in one
 * body is read in the next. Defined in xbox_memory_layout.c like the rest of
 * the register file. */
extern RECOMP_TLS double g_fp_stack[8];
extern RECOMP_TLS int g_fp_top;
extern RECOMP_TLS uint16_t g_fp_control_word;
extern RECOMP_TLS uint32_t g_mxcsr;
extern RECOMP_TLS int g_fp_cmp;
extern RECOMP_TLS RecompXmm g_xmm0, g_xmm1, g_xmm2, g_xmm3;
extern RECOMP_TLS RecompXmm g_xmm4, g_xmm5, g_xmm6, g_xmm7;
extern ptrdiff_t g_xbox_mem_offset;

/* ── XBE Constants ─────────────────────────────────────────── */

/*
 * TODO: Set these from your xbe_parser output.
 * Run: py -3 -m tools.xbe_parser game/default.xbe
 *
 * YOUR_GAME_XBE_PATH and YOUR_GAME_DIR are the defaults for a developer run
 * from the project root. An installed game's launcher sets RECOMP_GAME_FILES
 * (the game files) and RECOMP_HDD_DIR (the emulated hard disk) instead, and
 * those win (host_main, step 2).
 */
#define YOUR_GAME_ENTRY_POINT   0x000116DF  /* XBE entry point VA */
/* Relative to rdr-apex (run.bat's working directory): game_files holds the
 * XBE the code was generated from, juego the game folder (or a link to it,
 * see README). */
#define YOUR_GAME_XBE_PATH      "..\\game_files\\default.xbe"
#define YOUR_GAME_DIR            "..\\juego"

/* ── Forward declarations ──────────────────────────────────── */

static BOOL load_xbe(const char *path, void **out_data, size_t *out_size);

/* Recompiled entry point (generated by recomp pipeline) */
extern void xbe_entry_point(void);

/* Flat dispatch table builder (generated, recomp_dispatch.c): declared here
 * because main.c does not include recomp_types.h, and Clang rejects the
 * implicit declaration MSVC only warned about. */
extern int recomp_dispatch_init(void);

/* The emulated APU.
 *
 * Two entry points that had no callers anywhere in the tree. apu_mmio_hook.c
 * documents apu_hook_handle_mmio as "called from VEH in main.c" and no main.c
 * called it; apu_decode_and_handle's first line is `if (!g_apu_state) return
 * false` and nothing assigned g_apu_state. So with RECOMP_AC97_READY set the
 * APU's registers were unmapped to be trapped, and every trap was then
 * declined and surfaced as an access violation on the first register
 * DirectSound touched. The crash handlers below now reach the APU model
 * through the toolkit's xbox_VehMmioFault (Windows) and xbox_PosixMmioFault
 * (POSIX).
 *
 * Declared rather than included so this does not depend on src/apu being on
 * the include path. */
typedef struct MCPXAPUState MCPXAPUState;
extern MCPXAPUState *mcpx_apu_init_standalone(uint8_t *ram_ptr);
extern MCPXAPUState *g_apu_state;

/* ── Crash reporting (shared by every host) ────────────────── */

/* Fault access kinds handed to report_crash. */
#define FAULT_READ     0
#define FAULT_WRITE    1
#define FAULT_UNKNOWN (-1)

/* Label for the host program counter in the [CRASH] line: the register's own
 * name, so the number can be pasted straight into a debugger. */
#if defined(__aarch64__) || defined(_M_ARM64)
#define HOST_PC_LABEL "PC"
#else
#define HOST_PC_LABEL "RIP"
#endif

/* All crash output goes through here.
 *
 * On POSIX this runs inside a signal handler, possibly while the faulting
 * thread holds stdio's lock, so it formats into a stack buffer and write()s
 * instead of going through fprintf. On Windows the VEH has always used
 * fprintf(stderr), and still does. */
static void crash_printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
#if defined(_WIN32)
    vfprintf(stderr, fmt, ap);
#else
    {
        char buf[512];
        int n = vsnprintf(buf, sizeof(buf), fmt, ap);
        if (n > 0) {
            size_t len = (size_t)n < sizeof(buf) ? (size_t)n : sizeof(buf) - 1;
            ssize_t r = write(STDERR_FILENO, buf, len);
            (void)r;
        }
    }
#endif
    va_end(ap);
}

/* Name the host symbol containing pc, as "name+0xoff". Returns false, with
 * "<unknown>" in out, when there is none.
 *
 * Windows: dbghelp against the PDB (SymInitialize runs at install time).
 * Elsewhere: dladdr, which on macOS reads the executable's own symbol table --
 * static functions included, no -export_dynamic needed -- as long as the
 * binary is not stripped. dli_sname has no leading underscore. */
static bool host_symbol_for(void *pc, char *out, size_t n)
{
#if defined(_WIN32)
    /* SYMBOL_INFO is variable-length: the name is written past the struct, so
     * it must be over-allocated with MaxNameLen set to the slack. */
    char buf[sizeof(SYMBOL_INFO) + 256];
    SYMBOL_INFO *sym = (SYMBOL_INFO *)buf;
    DWORD64 disp = 0;

    memset(buf, 0, sizeof(buf));
    sym->SizeOfStruct = sizeof(SYMBOL_INFO);
    sym->MaxNameLen = 255;
    if (SymFromAddr(GetCurrentProcess(), (DWORD64)(uintptr_t)pc, &disp, sym)) {
        snprintf(out, n, "%s+0x%llX", sym->Name, (unsigned long long)disp);
        return true;
    }
#else
    Dl_info info;

    if (dladdr(pc, &info) && info.dli_sname && info.dli_saddr) {
        snprintf(out, n, "%s+0x%llX", info.dli_sname,
                 (unsigned long long)((uintptr_t)pc - (uintptr_t)info.dli_saddr));
        return true;
    }
#endif
    snprintf(out, n, "<unknown>");
    return false;
}

/* Name the guest function a fault happened in, and recover the call chain.
 *
 * Recompiled code faults as ordinary native code, so the fault carries a host
 * PC and nothing else -- there is no guest program counter to report, and the
 * host address changes every build. Two things recover the guest view:
 *
 *   - every generated function is a real symbol in the image (sub_005A03C0
 *     and so on), so the symbol table (the linker's PDB on Windows) already
 *     maps host address back to guest function. host_symbol_for turns an
 *     anonymous PC into that name.
 *
 *   - every lifted call pushes its guest return address onto the guest stack
 *     before jumping, so the stack still holds the chain. Scanning up from esp
 *     for values inside the code sections recovers it.
 *
 * ponytail: the stack scan is a scan, not a frame walk -- these are FPO frames
 * with no reliable ebp chain, so there is nothing to walk. It over-reports,
 * since addresses from returned-from calls linger below esp, but naming the
 * guest function is the whole question at a fault.
 *
 * Requires an unstripped executable: on Windows, linking dbghelp and keeping
 * the .pdb beside the .exe.
 */
static void print_guest_context(void *pc)
{
    char name[300];

    if (host_symbol_for(pc, name, sizeof(name)))
        crash_printf("  in %s\n", name);

    if (g_xbox_mem_offset && g_esp) {
        const uint32_t *sp =
            (const uint32_t *)((uintptr_t)g_xbox_mem_offset + g_esp);
        int shown = 0, i;
        crash_printf("  guest stack (return addresses, innermost first):\n");
        for (i = 0; i < 256 && shown < 24; i++) {
            uint32_t v = sp[i];
            if (v > g_xbox_code_lo && v < g_xbox_code_hi) {
                crash_printf("    [esp+%-4d] 0x%08X\n", i * 4, v);
                shown++;
            }
        }
        /* When the frame is gone, say so, and fall back on what is left.
         *
         * A fault inside a block copy leaves no return address in range: the
         * copy is a host memmove and its caller's frame is further up than
         * this reaches. Worse, a copy that ran past its buffer overwrites the
         * stack itself, so the list comes out empty exactly when it is most
         * needed -- and an empty list under a promising heading reads like
         * "nothing to see" rather than "the evidence is destroyed". */
        if (!shown)
            crash_printf("    (no return addresses in range)\n");

        /* Everything below only pays for itself when the scan came back
         * empty. A crash where the chain was recovered already says what
         * happened, and burying that under another twenty lines makes the
         * common report worse to read. */
        if (!shown) {
            uint32_t k;

            /* The indirect-call history, which the stack cannot overwrite.
             * recomp_manual.c prints this too, but only from
             * recomp_icall_fail_log -- a page fault inside a block copy
             * never reaches that path, and this is the same information by
             * the route the fault actually took.
             *
             * Declared here rather than included: main.c does not pull in
             * recomp_types.h, and recomp_manual.c spells it the same way. */
            extern volatile uint32_t g_icall_trace[16];
            extern volatile uint32_t g_icall_trace_idx;

            crash_printf("  recent ICALL targets:");
            for (k = 0; k < 16; k++)
                crash_printf(" %08X",
                             g_icall_trace[(g_icall_trace_idx + k) & 15]);
            crash_printf("\n");

            /* The frame unfiltered. The pointers and lengths handed to
             * whatever faulted live here and look nothing like code, so the
             * filter above drops exactly what is wanted. On the crash this
             * was written for, one of these words was the end of the mapped
             * RAM mirror -- which is what identified the fault as a copy
             * running off its buffer rather than a stray pointer. */
            for (i = 0; i < 20; i++)
                crash_printf("    raw[esp+%-4d] 0x%08X\n", i * 4, sp[i]);
        }
    }
}

/*
 * The host-independent part of a crash report: what faulted, the guest
 * registers, and the guest function and call chain. Each host's handler
 * decodes its own fault record, calls this, then appends its native stack.
 * `what` is "Access violation" on Windows and the signal's name elsewhere.
 *
 * This is your primary debugging tool during bring-up. Customize it for your
 * game:
 *   - Add game-specific address checks (GPU register probes, etc.)
 *   - Add dumps of game-specific globals (heap handles, state flags)
 *   - Add SEH simulation if your game uses __try/__except
 */
static void report_crash(const char *what, void *host_pc, uintptr_t fault_addr,
                         int access)
{
    uintptr_t va = fault_addr - (uintptr_t)g_xbox_mem_offset;

    crash_printf("[CRASH] %s at " HOST_PC_LABEL "=0x%llX, fault addr=0x%llX (%s)\n",
        what,
        (unsigned long long)(uintptr_t)host_pc,
        (unsigned long long)fault_addr,
        access == FAULT_WRITE ? "write"
        : access == FAULT_READ ? "read" : "unknown");
    crash_printf("  Xbox regs: eax=0x%08X ecx=0x%08X edx=0x%08X esp=0x%08X\n",
        g_eax, g_ecx, g_edx, g_esp);
    crash_printf("  Xbox regs: ebx=0x%08X esi=0x%08X edi=0x%08X\n",
        g_ebx, g_esi, g_edi);
#if !defined(_WIN32)
    /* A signal can come from a host pointer (a toolkit bug, a NULL) as well
     * as from guest memory; a "guest VA" for that would be noise. */
    if (va > 0xFFFFFFFFu)
        crash_printf("  Xbox VA of fault: (host address, outside guest memory)\n");
    else
#endif
    crash_printf("  Xbox VA of fault: 0x%08X\n", (uint32_t)va);
    print_guest_context(host_pc);

    /*
     * TODO: Add game-specific diagnostics here. Examples:
     *
     * Dump CRT heap handle:
     *   uint32_t heap = *(uint32_t *)((uint8_t *)g_xbox_mem_offset + HEAP_HANDLE_VA);
     *   crash_printf("  CRT heap handle: 0x%08X\n", heap);
     *
     * Dump game state:
     *   uint32_t state = *(uint32_t *)((uint8_t *)g_xbox_mem_offset + GAME_STATE_VA);
     *   crash_printf("  Game state: %u\n", state);
     */
}

#if defined(_WIN32)

/* ── Windows: VEH crash handler ────────────────────────────── */

/*
 * Vectored Exception Handler for crash diagnostics.
 *
 * When the recompiled game hits an access violation, this handler prints
 * the faulting address, all Xbox register values, and a native stack trace.
 */
static LONG CALLBACK veh_handler(PEXCEPTION_POINTERS ep)
{
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
        uintptr_t fault_addr = ep->ExceptionRecord->ExceptionInformation[1];

        /*
         * GPU register probe at 0xFD000000 range.
         * Some games probe NV2A registers directly. On real hardware this
         * returns GPU state; here we just skip the instruction.
         * TODO: Implement mini x86-64 decoder for instruction skipping,
         * or connect to the xbox_nv2a library for proper handling.
         */
        if (fault_addr >= 0xFD000000 && fault_addr < 0xFE000000) {
            return EXCEPTION_CONTINUE_SEARCH;
        }

        /* Trapped hardware registers (APU, USB OHCI) -> their models.
         *
         * The other half of RECOMP_AC97_READY: reporting the codec ready is
         * what lets DirectSoundCreate past its first gate, and from there it
         * drives the APU directly, so the registers have to fault to be seen.
         * "Handled" means the access was decoded and the instruction stepped
         * over, so execution resumes instead of unwinding. */
        if (xbox_VehMmioFault(ep))
            return EXCEPTION_CONTINUE_EXECUTION;

        report_crash("Access violation", (void *)ep->ContextRecord->Rip,
                     fault_addr,
                     ep->ExceptionRecord->ExceptionInformation[0]
                         ? FAULT_WRITE : FAULT_READ);

        /* Print native stack return addresses for debugging */
        {
            uintptr_t *sp = (uintptr_t *)ep->ContextRecord->Rsp;
            fprintf(stderr, "  Native stack (first 8 return addrs):\n");
            for (int i = 0; i < 64 && sp[i]; i++) {
                if (sp[i] >= 0x140000000ULL && sp[i] < 0x150000000ULL) {
                    fprintf(stderr, "    [%d] 0x%llX\n", i, (unsigned long long)sp[i]);
                }
            }
        }
        fflush(stderr);
    }

    return EXCEPTION_CONTINUE_SEARCH;
}

/* ── RDR_ZWATCH: who reads the depth buffer? ─────────────────────────────
 *
 * Diagnostic for the aiming bug (shots land at the top right, not under the
 * crosshair). The D3D11 backend keeps colour and depth on the host GPU and
 * never writes them back to guest memory, so a title that reads its depth
 * buffer under the crosshair would read zeroes. RDR_ZWATCH=<va>,<bytes>
 * (default the 640x480 zeta at 0x80B14000) arms PAGE_GUARD on that range
 * every 50 ms and logs each distinct host instruction that touches it, with
 * the generated function it is in and the guest return addresses on the
 * stack. Silent when nothing reads it. */
extern RECOMP_TLS uint32_t g_esp;
static uint8_t *s_zw_base;
static size_t   s_zw_size;

static LONG CALLBACK zwatch_veh(PEXCEPTION_POINTERS ep)
{
    enum { SITES = 32 };
    static uintptr_t seen[SITES];
    static int nseen;
    const EXCEPTION_RECORD *er = ep->ExceptionRecord;
    uintptr_t addr, rip;
    int i;

    if (er->ExceptionCode != STATUS_GUARD_PAGE_VIOLATION || er->NumberParameters < 2)
        return EXCEPTION_CONTINUE_SEARCH;
    addr = (uintptr_t)er->ExceptionInformation[1];
    if (addr < (uintptr_t)s_zw_base || addr >= (uintptr_t)s_zw_base + s_zw_size)
        return EXCEPTION_CONTINUE_SEARCH;
    rip = (uintptr_t)ep->ContextRecord->Rip;
    for (i = 0; i < nseen && seen[i] != rip; i++)
        ;
    if (i == nseen && nseen < SITES) {
        char buf[sizeof(SYMBOL_INFO) + 128];
        SYMBOL_INFO *si = (SYMBOL_INFO *)buf;
        DWORD64 disp = 0;
        uint32_t esp = g_esp, k, shown = 0;

        seen[nseen++] = rip;
        memset(buf, 0, sizeof buf);
        si->SizeOfStruct = sizeof(SYMBOL_INFO);
        si->MaxNameLen = 127;
        fprintf(stderr, "[ZWATCH] %s guest 0x%08X (+0x%X into the buffer) from %s+0x%llX\n",
                er->ExceptionInformation[0] ? "write" : "read",
                (unsigned)(addr - (uintptr_t)g_xbox_mem_offset),
                (unsigned)(addr - (uintptr_t)s_zw_base),
                SymFromAddr(GetCurrentProcess(), rip, &disp, si) ? si->Name : "?",
                (unsigned long long)disp);
        for (k = 0; k < 256 && shown < 8; k++) {
            uint32_t v = *(volatile uint32_t *)((uint8_t *)g_xbox_mem_offset + esp + 4u * k);
            if (v >= 0x00011000u && v < 0x00338620u) {
                fprintf(stderr, "[ZWATCH]   [esp+%03X] 0x%08X\n", 4u * k, v);
                shown++;
            }
        }
        fflush(stderr);
    }
    return EXCEPTION_CONTINUE_EXECUTION;   /* the guard bit is already cleared */
}

static DWORD WINAPI zwatch_thread(LPVOID unused)
{
    (void)unused;
    for (;;) {
        DWORD old;
        VirtualProtect(s_zw_base, s_zw_size, PAGE_READWRITE | PAGE_GUARD, &old);
        Sleep(50);
    }
}

static void zwatch_start(void)
{
    const char *e = getenv("RDR_ZWATCH");
    uint32_t va = 0x80B14000u, bytes = 640u * 480u * 4u;
    HANDLE th;

    if (!e)
        return;
    if (*e && *e != '1')
        sscanf(e, "%x,%u", &va, &bytes);
    s_zw_base = (uint8_t *)g_xbox_mem_offset + va;
    s_zw_size = bytes;
    AddVectoredExceptionHandler(1, zwatch_veh);
    th = CreateThread(NULL, 0, zwatch_thread, NULL, 0, NULL);
    if (th)
        CloseHandle(th);
    fprintf(stderr, "[ZWATCH] guarding guest 0x%08X, %u bytes\n", va, bytes);
}

/* ── Mouse: camera and aim on the right stick, buttons on the triggers ───
 *
 * With RECOMP_MOUSE=1 the toolkit already turns mouse motion into the right
 * stick (camera, and fine aim while aiming) and captures the cursor while the
 * window has focus (F9 frees it). What it lacks without the enhancements
 * layer is a binding for the buttons, so add them on top of the compiled-in
 * key map: left button fires (right trigger), right button aims (left
 * trigger), middle button is the right-stick click, the wheel is the white
 * and black buttons. Space is also A.
 *
 * RDR_MOUSE_SENS (default 1.0: 40 counts in one poll is full deflection) and
 * RDR_MOUSE_MIN (default 0.25, the smallest deflection any motion gives) tune
 * the stick model; RDR_MOUSE_INVERT_Y=1 inverts the vertical axis. */
/* Aiming has its own sensitivity, as BLACK's port has: while the right
 * button (aim) is held, the stick model's sensitivity is the base times
 * RDR_MOUSE_AIM_MULT, so fine aim keeps up with the hand without making the
 * free camera twitchy. A thread follows the button and swaps the options on
 * each edge; xbox_InputMouseOpts publishes them for the next poll. */
static double s_base_sens = 2.0, s_aim_mult = 1.75;

static DWORD WINAPI rdr_aim_sens_thread(LPVOID unused)
{
    int aiming = 0;
    (void)unused;
    for (;;) {
        int now = xbox_InputMouseHeld(XBOX_MOUSE_RIGHT);
        if (now != aiming) {
            xbox_mouse_opts o;
            xbox_InputMouseGetOpts(&o);
            o.sensitivity = now ? s_base_sens * s_aim_mult : s_base_sens;
            xbox_InputMouseOpts(&o);
            aiming = now;
        }
        Sleep(5);
    }
}

static void rdr_mouse_init(void)
{
    xbox_mouse_opts o;
    const char *e;

    if (!xbox_InputMouseOn())
        return;
    xbox_InputMouseGetOpts(&o);
    o.look = XBOX_MOUSE_LOOK_RIGHT;
    o.min_deflection = 0.3;
    if ((e = getenv("RDR_MOUSE_SENS")) && *e)
        s_base_sens = atof(e);
    if ((e = getenv("RDR_MOUSE_AIM_MULT")) && *e)
        s_aim_mult = atof(e);
    o.sensitivity = s_base_sens;
    if ((e = getenv("RDR_MOUSE_MIN")) && *e)
        o.min_deflection = atof(e);
    if ((e = getenv("RDR_MOUSE_INVERT_Y")) && *e == '1')
        o.invert_y = 1;
    xbox_InputMouseOpts(&o);

    xbox_InputBindingsStage();          /* start from the compiled-in key map */
    xbox_InputBind(INPUT_RIGHT_TRIGGER, XBOX_MOUSE_LEFT, 1);
    xbox_InputBind(INPUT_LEFT_TRIGGER, XBOX_MOUSE_RIGHT, 1);
    xbox_InputBind(INPUT_RIGHT_THUMB, XBOX_MOUSE_MIDDLE, 1);
    /* The wheel changes weapon both ways, as in a PC shooter: white is the
     * game's weapon cycle (one way only), so up and down both press it;
     * black stays on F. */
    xbox_InputBind(INPUT_WHITE, XBOX_MOUSE_WHEEL_UP, 1);
    xbox_InputBind(INPUT_WHITE, XBOX_MOUSE_WHEEL_DOWN, 1);
    xbox_InputBind(INPUT_A, 0x20 /* VK_SPACE */, 0);
    /* PC layout over the emulator row (Z X C V = A B X Y, Q E = white
     * black). The font's button glyphs (front.dat #5: U+BA A, U+BC Y,
     * U+BD X, U+BE B) say "Press Y to reload" and "Press X to enter the
     * Gunshop": R reloads (Y), E acts (X), C is B, F is black, Esc pauses
     * (START), Tab is BACK. The old letters stay where they do not clash. */
    xbox_InputBindingsClear(INPUT_Y);
    xbox_InputBind(INPUT_Y, 'R', 0);
    xbox_InputBind(INPUT_Y, 'V', 0);
    xbox_InputBindingsClear(INPUT_X);
    xbox_InputBind(INPUT_X, 'E', 0);
    xbox_InputBindingsClear(INPUT_B);
    xbox_InputBind(INPUT_B, 'C', 0);
    xbox_InputBind(INPUT_B, 'X', 0);
    xbox_InputBindingsClear(INPUT_BLACK);
    xbox_InputBind(INPUT_BLACK, 'F', 0);
    xbox_InputBind(INPUT_START, 0x1B /* VK_ESCAPE */, 0);
    xbox_InputBind(INPUT_BACK, 0x09 /* VK_TAB */, 0);
    xbox_InputBindingsCommit();
    fprintf(stderr, "[RDR] mouse: right stick, sensitivity %.2f (x%.2f aiming), min %.2f%s; "
                    "LMB fire, RMB aim, MMB right-stick click, wheel weapon (white); R reload (Y), E use (X), C B, F black, Esc start, Tab back\n",
            o.sensitivity, s_aim_mult, o.min_deflection, o.invert_y ? ", inverted Y" : "");
    {
        HANDLE th = CreateThread(NULL, 0, rdr_aim_sens_thread, NULL, 0, NULL);
        if (th)
            CloseHandle(th);
    }
}

/* ── Graphics: the GPU backend's host options without the enhance layer ──
 *
 * The D3D11 backend honours nv2a_host_opts (internal resolution, anisotropic
 * filtering, present filter, aspect, fullscreen), which only the opt-in
 * enhancements layer fills. Fill them here before the guest starts, from
 * env.bat:
 *   RDR_RENDER_SCALE  1..4   internal resolution factor (default 2: 1280x960)
 *   RDR_ANISO         0..16  anisotropic filtering (default 16)
 *   RDR_FILTER        nearest | linear | integer (default linear)
 *   RDR_ASPECT        4:3 | 16:9 | 16:10 | 21:9 (default 4:3, the stock frame)
 *   RDR_FULLSCREEN    1 starts borderless fullscreen (default 0)
 * snap_2d keeps 2D batches (the HUD, text) on the guest pixel grid above
 * scale 1, so they do not pick up seams from the larger target. */
static void rdr_graphics_init(void)
{
    struct nv2a_host_opts o;
    const char *e;
    unsigned aw = 0, ah = 0;

    memset(&o, 0, sizeof o);
    o.render_scale = 2;
    o.aniso = 16;
    /* Sharp scaling and no pixel-aligned HUD, fixed: their F2 rows are gone
     * (the user's choice, 2026-11-02). Pause on focus loss stays on. */
    o.present_filter = NV2A_PRESENT_NEAREST;
    o.snap_2d = 0;
    if ((e = getenv("RDR_RENDER_SCALE")) && *e)
        o.render_scale = (unsigned)atoi(e);
    if (o.render_scale < 1) o.render_scale = 1;
    if (o.render_scale > 4) o.render_scale = 4;
    if ((e = getenv("RDR_ANISO")) && *e)
        o.aniso = (unsigned)atoi(e);
    if (o.aniso > 16) o.aniso = 16;
    if ((e = getenv("RDR_ASPECT")) && sscanf(e, "%u:%u", &aw, &ah) == 2
            && aw && ah && !(aw * 3 == ah * 4)) {
        o.aspect_w = aw;
        o.aspect_h = ah;
    }
    if ((e = getenv("RDR_FULLSCREEN")) && *e == '1')
        o.fullscreen = 1;
    nv2a_host_opts_set(&o);
    fprintf(stderr, "[RDR] graphics: scale %ux (%ux%u), aniso %u, filter %s, aspect %s%s\n",
            o.render_scale, 640u * o.render_scale, 480u * o.render_scale, o.aniso,
            o.present_filter == NV2A_PRESENT_NEAREST ? "nearest"
            : o.present_filter == NV2A_PRESENT_INTEGER ? "integer" : "linear",
            o.aspect_w ? e : "4:3", o.fullscreen ? ", fullscreen" : "");
}

/* ── RDR_SCAN: find a counter that steps down by one ────────────────────
 *
 * RDR_SCAN=t1,t2,t3 (seconds since start) snapshots guest RAM three times
 * and prints every address whose value went down by exactly one at each
 * step, as int32, int16 or float. With a shot between snapshots that is the
 * ammo counter, whose writer is the firing code. Reads go through
 * ReadProcessMemory so unmapped guest pages are skipped, not faulted on. */
typedef struct { uint32_t va, len; } ScanRange;
static const ScanRange s_scan_ranges[] = {
    { 0x0040D8A0u, 0x0081CAE0u - 0x0040D8A0u },   /* .data and BSS */
    { 0x010C0000u, 0x04000000u - 0x010C0000u },   /* runtime heap */
    { 0x80000000u, 0x04000000u },                 /* contiguous window */
};

static uint8_t *scan_snapshot(void)
{
    size_t total = 0, off = 0, r;
    uint8_t *buf;
    for (r = 0; r < sizeof s_scan_ranges / sizeof s_scan_ranges[0]; r++)
        total += s_scan_ranges[r].len;
    buf = (uint8_t *)calloc(1, total);
    if (!buf)
        return NULL;
    for (r = 0; r < sizeof s_scan_ranges / sizeof s_scan_ranges[0]; r++) {
        uint32_t k;
        for (k = 0; k < s_scan_ranges[r].len; k += 0x10000u) {
            SIZE_T got = 0;
            uint32_t n = s_scan_ranges[r].len - k < 0x10000u ? s_scan_ranges[r].len - k : 0x10000u;
            ReadProcessMemory(GetCurrentProcess(),
                              (uint8_t *)g_xbox_mem_offset + s_scan_ranges[r].va + k,
                              buf + off + k, n, &got);
        }
        off += s_scan_ranges[r].len;
    }
    return buf;
}

static DWORD WINAPI scan_thread(LPVOID arg)
{
    unsigned t[3] = { 0, 0, 0 }, i;
    uint8_t *snap[3];
    DWORD start = GetTickCount();
    int found = 0;
    size_t off = 0, r;

    sscanf((const char *)arg, "%u,%u,%u", &t[0], &t[1], &t[2]);
    for (i = 0; i < 3; i++) {
        while (GetTickCount() - start < t[i] * 1000u)
            Sleep(20);
        snap[i] = scan_snapshot();
        fprintf(stderr, "[SCAN] snapshot %u at %us\n", i, t[i]);
        if (!snap[i])
            return 0;
    }
    for (r = 0; r < sizeof s_scan_ranges / sizeof s_scan_ranges[0]; r++) {
        uint32_t k;
        for (k = 0; k + 4 <= s_scan_ranges[r].len; k += 2) {
            const uint8_t *a = snap[0] + off + k, *b = snap[1] + off + k, *c = snap[2] + off + k;
            int32_t ia, ib, ic; int16_t sa, sb, sc; float fa, fb, fc;
            const char *kind = NULL;
            memcpy(&ia, a, 4); memcpy(&ib, b, 4); memcpy(&ic, c, 4);
            memcpy(&sa, a, 2); memcpy(&sb, b, 2); memcpy(&sc, c, 2);
            memcpy(&fa, a, 4); memcpy(&fb, b, 4); memcpy(&fc, c, 4);
            if (!(k & 3) && ia > 1 && ia < 100000 && ib == ia - 1 && ic == ib - 1)
                kind = "int32";
            else if (sa > 1 && sb == sa - 1 && sc == sb - 1)
                kind = "int16";
            else if (!(k & 3) && fa > 1.5f && fa < 100000.f && fb == fa - 1.f && fc == fb - 1.f)
                kind = "float";
            if (kind && found++ < 60)
                fprintf(stderr, "[SCAN] 0x%08X %s %d -> %d -> %d\n",
                        s_scan_ranges[r].va + k, kind,
                        kind[0] == 'f' ? (int)fa : kind[3] == '1' ? sa : ia,
                        kind[0] == 'f' ? (int)fb : kind[3] == '1' ? sb : ib,
                        kind[0] == 'f' ? (int)fc : kind[3] == '1' ? sc : ic);
        }
        off += s_scan_ranges[r].len;
    }
    fprintf(stderr, "[SCAN] %d candidate(s)\n", found);
    fflush(stderr);
    return 0;
}

static void scan_start(void)
{
    const char *e = getenv("RDR_SCAN");
    HANDLE th;
    if (!e || !*e)
        return;
    th = CreateThread(NULL, 0, scan_thread, (LPVOID)e, 0, NULL);
    if (th)
        CloseHandle(th);
}

/* rdr-port: a fault nobody handled. Windows froze every thread while it
 * built its report, so the game looked alive but ignored every key, and the
 * player could not tell. Now: a line in the log, a notice, and out. Only the
 * truly unhandled ones reach here (the VEH above sees first-chance faults,
 * some of which a DLL handles itself). */
static LONG WINAPI unhandled_filter(PEXCEPTION_POINTERS ep)
{
    wchar_t msg[256];
    fprintf(stderr, "[CRASH] unhandled 0x%08lX: closing the game\n",
            (unsigned long)ep->ExceptionRecord->ExceptionCode);
    fflush(stderr);
    _snwprintf(msg, 256,
               L"El juego tuvo un error y se va a cerrar (código 0x%08lX).\n\n"
               L"Si se repite, mandá el archivo registro.txt que está junto a RedDeadRevolver.exe.",
               (unsigned long)ep->ExceptionRecord->ExceptionCode);
    msg[255] = 0;
    ClipCursor(NULL);
    MessageBoxW(NULL, msg, L"Red Dead Revolver", MB_OK | MB_ICONERROR | MB_TOPMOST | MB_SETFOREGROUND);
    TerminateProcess(GetCurrentProcess(), 1);
    return EXCEPTION_EXECUTE_HANDLER;
}

static void host_install_crash_handler(void)
{
    SetUnhandledExceptionFilter(unhandled_filter);
    /* Load symbols up front rather than from inside the handler: at fault
     * time the process is already in a bad way, and SymInitialize
     * allocates. Failure is not fatal -- the handler prints no name. */
    SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME);
    SymInitialize(GetCurrentProcess(), NULL, TRUE);
    /* First handler in the chain */
    AddVectoredExceptionHandler(1, veh_handler);
}

#else /* !_WIN32 */

/* ── POSIX: SIGBUS/SIGSEGV crash handler ───────────────────── */

/* Guest memory is reserved PROT_NONE, and on macOS touching a mapped but
 * inaccessible page is SIGBUS; only a truly unmapped address is SIGSEGV. So
 * the common guest fault arrives as SIGBUS, and both are handled. Nothing in
 * the toolkit installs signal handlers, so nothing else competes for these.
 *
 * Known gaps, accepted for a bring-up tool: vsnprintf and dladdr are not
 * formally async-signal-safe (dladdr takes dyld's lock), and Darwin allocates
 * __thread storage lazily, so reading the guest registers on a thread that
 * never touched them can malloc. The Windows VEH has the same exposure with
 * fprintf. */

/* PC of the faulting instruction, from the signal context. */
static void *host_fault_pc(void *ucv)
{
    ucontext_t *uc = (ucontext_t *)ucv;
#if defined(__APPLE__) && defined(__aarch64__)
    return (void *)(uintptr_t)uc->uc_mcontext->__ss.__pc;
#elif defined(__APPLE__) && defined(__x86_64__)
    return (void *)(uintptr_t)uc->uc_mcontext->__ss.__rip;
#elif defined(__linux__) && defined(__aarch64__)
    return (void *)(uintptr_t)uc->uc_mcontext.pc;
#elif defined(__linux__) && defined(__x86_64__)
    return (void *)(uintptr_t)uc->uc_mcontext.gregs[REG_RIP];
#else
    (void)uc;
    return NULL;
#endif
}

/* Read or write, when the host can tell.
 *
 * arm64 Darwin: the ESR's WnR bit (6) means "write", but only for a data
 * abort (exception class 0x24 from a lower EL, 0x25 from the same EL). For any
 * other class the bit means something else, so say unknown. */
static int host_fault_access(void *ucv)
{
#if defined(__APPLE__) && defined(__aarch64__)
    ucontext_t *uc = (ucontext_t *)ucv;
    uint32_t esr = uc->uc_mcontext->__es.__esr;
    uint32_t ec = esr >> 26;

    if (ec == 0x24 || ec == 0x25)
        return (esr >> 6) & 1 ? FAULT_WRITE : FAULT_READ;
    return FAULT_UNKNOWN;
#else
    (void)ucv;
    return FAULT_UNKNOWN;
#endif
}

/* The native call chain, innermost first, by walking frame records.
 *
 * Apple's arm64 ABI keeps a frame pointer, so starting from the signal context
 * this is exact and async-signal-safe (bar dladdr) -- unlike backtrace(),
 * which drops the faulting leaf frame. Frame 0 is the faulting PC; frame 1 is
 * lr, which is the caller even when the leaf never built a frame of its own;
 * then each frame record [fp] = caller's fp, [fp+8] = return address. */
static void print_native_stack(void *ucv)
{
#if defined(__APPLE__) && defined(__aarch64__)
    ucontext_t *uc = (ucontext_t *)ucv;
    uintptr_t pc = (uintptr_t)uc->uc_mcontext->__ss.__pc;
    uintptr_t lr = (uintptr_t)uc->uc_mcontext->__ss.__lr;
    uintptr_t fp = (uintptr_t)uc->uc_mcontext->__ss.__fp;
    char name[300];
    int n = 0, first = 1;

    crash_printf("  Native stack (innermost first):\n");
    host_symbol_for((void *)pc, name, sizeof(name));
    crash_printf("    [%d] 0x%llX in %s\n", n++, (unsigned long long)pc, name);
    host_symbol_for((void *)lr, name, sizeof(name));
    crash_printf("    [%d] 0x%llX in %s\n", n++, (unsigned long long)lr, name);

    while (n < 16 && fp && (fp & 7) == 0) {
        uintptr_t next = ((const uintptr_t *)fp)[0];
        uintptr_t ret = ((const uintptr_t *)fp)[1];

        /* A leaf that did build a frame stored lr in it: skip that one
         * repeat only -- recursive frames legitimately share a return address. */
        if (!(first && ret == lr) && ret) {
            host_symbol_for((void *)ret, name, sizeof(name));
            crash_printf("    [%d] 0x%llX in %s\n", n++,
                         (unsigned long long)ret, name);
        }
        first = 0;
        if (next <= fp)     /* the stack grows down: callers' frames are higher */
            break;
        fp = next;
    }
#else
    (void)ucv;
    crash_printf("  Native stack: not available on this host\n");
#endif
}

/* Re-entry guard: a fault while writing the report, or a second thread
 * faulting meanwhile, must end the process, not report again. SA_NODEFER lets
 * a same-signal fault inside the handler get here instead of being
 * force-killed by the kernel with nothing said. */
static volatile sig_atomic_t g_in_crash_handler;

static void restore_default(int sig)
{
    struct sigaction sa;

    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = SIG_DFL;
    sigemptyset(&sa.sa_mask);
    sigaction(sig, &sa, NULL);
}

/* A signal sent with kill, raise or pthread_kill has no faulting instruction
 * to re-execute: returning would let the process run on. Deliver it again,
 * now with the default disposition. raise is async-signal-safe. */
static void die_if_sent(int sig, const siginfo_t *si)
{
    if (si->si_code == SI_USER || si->si_code == SI_QUEUE
#ifdef SI_TKILL
        || si->si_code == SI_TKILL
#endif
        )
        raise(sig);
}

static void posix_crash_handler(int sig, siginfo_t *si, void *ucv)
{
    /* Trapped hardware registers -> their models, through the toolkit's
     * dispatch: the APU, the AC'97 bus-master page (RECOMP_AC97_READY) and the
     * USB OHCI controllers. A serviced access returns here with pc advanced;
     * the kernel resumes the thread after the instruction. Hosts without a
     * decoder (x86-64 macOS) get 0 and fall through to the report. */
    if (xbox_PosixMmioFault(ucv, (uintptr_t)si->si_addr))
        return;

    if (__atomic_exchange_n(&g_in_crash_handler, 1, __ATOMIC_SEQ_CST)) {
        restore_default(sig);
        die_if_sent(sig, si);
        return;
    }

    report_crash(sig == SIGBUS ? "SIGBUS" : "SIGSEGV", host_fault_pc(ucv),
                 (uintptr_t)si->si_addr, host_fault_access(ucv));
    print_native_stack(ucv);

    /* Returning re-executes the faulting instruction with the default
     * disposition in place, so the process dies by the original signal: the
     * shell's exit status and any core dump say what happened. */
    restore_default(sig);
    die_if_sent(sig, si);
}

/* Alternate signal stack for the thread that installs the handler (the one
 * that runs the guest), so a stack overflow there still gets a report.
 * Guest-created threads have none (their start routine is toolkit code), so
 * an overflow on one of those dies unreported -- still by signal. 128 KB, the
 * Darwin SIGSTKSZ: snprintf plus a dladdr per frame does not fit in much
 * less. A literal, because SIGSTKSZ is not a compile-time constant on
 * glibc >= 2.34. */
static char g_crash_altstack[128 * 1024];

static void host_install_crash_handler(void)
{
    stack_t ss;
    struct sigaction sa;

    memset(&ss, 0, sizeof(ss));
    ss.ss_sp = g_crash_altstack;
    ss.ss_size = sizeof(g_crash_altstack);
    if (sigaltstack(&ss, NULL) != 0)
        fprintf(stderr, "[BOOT] sigaltstack failed; a guest-thread stack "
                        "overflow will die without a report\n");

    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = posix_crash_handler;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK | SA_NODEFER;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGSEGV, &sa, NULL);
}

#endif /* _WIN32 */

/* ── Startup failures ──────────────────────────────────────── */

/* A required startup step failed: say which, and what to do, on stderr on
 * every host -- and in a dialog on Windows, where a GUI-subsystem launch may
 * have no console to read. RECOMP_HEADLESS (no window) means no dialog
 * either: one would wait for a click nobody can give. */
static void host_report_fatal(const char *step, const char *detail)
{
    fprintf(stderr, "[FATAL] %s: %s\n", step, detail);
    fflush(stderr);
#if defined(_WIN32)
    if (!recomp_env_on(RENV_HEADLESS))
        MessageBoxA(NULL, detail, "Recomp", MB_ICONERROR);
#endif
}

/* rdr-port: the code was recompiled from one exact default.xbe, the PAL
 * (Europe) release, region "rest of the world", version 3. Any other build
 * (the NTSC one is 4,403,200 bytes) has its code and data elsewhere and dies
 * at the first indirect call, so say so and stop. RDR_XBE_ANY=1 skips the
 * check (development). FNV-1a 64 of the whole file. */
#define RDR_XBE_SIZE 4452352u
#define RDR_XBE_FNV  0x0D9B321F12DBAF37ull

static int rdr_xbe_supported(const uint8_t *data, size_t size)
{
    const char *any = getenv("RDR_XBE_ANY");
    uint64_t h = 0xcbf29ce484222325ull;
    size_t i;
    if (any && *any == '1')
        return 1;
    if (size != RDR_XBE_SIZE)
        return 0;
    for (i = 0; i < size; i++)
        h = (h ^ data[i]) * 0x100000001b3ull;
    return h == RDR_XBE_FNV;
}

static void rdr_report_wrong_xbe(size_t size)
{
    char msg[1200];
    snprintf(msg, sizeof msg,
             "Tu copia de Red Dead Revolver es otra versión del juego (default.xbe de %zu bytes).\n"
             "Este port solo funciona con la versión PAL (Europa) de Xbox: default.xbe de %u bytes.\n\n"
             "Your copy of Red Dead Revolver is a different version of the game (default.xbe, %zu bytes).\n"
             "This port only works with the PAL (Europe) Xbox release: default.xbe, %u bytes.",
             size, RDR_XBE_SIZE, size, RDR_XBE_SIZE);
    fprintf(stderr, "[FATAL] load XBE: unsupported game version (%zu bytes)\n", size);
    fflush(stderr);
#if defined(_WIN32)
    if (!recomp_env_on(RENV_HEADLESS)) {
        wchar_t w[1200];
        if (MultiByteToWideChar(CP_UTF8, 0, msg, -1, w, (int)(sizeof w / sizeof w[0])))
            MessageBoxW(NULL, w, L"Red Dead Revolver PC", MB_ICONERROR);
    }
#endif
}

/* ── Boot sequence (shared) ────────────────────────────────── */

/* RECOMP_STDIO_LOG and unbuffered stdio, from the entry points: before any
 * other output and before any thread, so every line of the boot reaches the
 * log. */
static void host_stdio_setup(void)
{
    /* RECOMP_STDIO_LOG=<path>: send stdout and stderr to a file (truncated).
     * Proton drops a game's stdio whatever its subsystem, so this is the only
     * way to see the boot log and crash reports there. The bench, the
     * Windows launcher and the SteamOS launcher all set it and read the
     * file. */
    int stdio_log_err = -1;   /* Windows only: did stderr reopen? */
    {
        const char *stdio_log = recomp_env(RENV_STDIO_LOG);
        if (stdio_log && *stdio_log) {
            /* Open it first: a failed freopen leaves the stream closed, and
             * the whole boot log would vanish without a word. */
            int opened = 0;
#if defined(_WIN32)
            /* A GUI-subsystem exe starts with no stderr descriptor
             * (_fileno(stderr) == -2), so there is nothing to _dup2 onto.
             * Reopen both streams instead, in append mode so that their
             * writes interleave rather than overwrite each other. */
            FILE *trunc = fopen(stdio_log, "w");
            if (trunc) {
                fclose(trunc);
                opened = 1;
                if (freopen(stdio_log, "a", stdout))
                    stdio_log_err = freopen(stdio_log, "a", stderr) != NULL;
            }
#else
            FILE *probe = fopen(stdio_log, "w");
            if (probe) {
                fclose(probe);
                opened = 1;
                if (freopen(stdio_log, "w", stdout))
                    dup2(fileno(stdout), fileno(stderr));
            }
#endif
            if (!opened)
                fprintf(stderr, "[BOOT] RECOMP_STDIO_LOG: cannot open %s; "
                        "output stays on the console\n", stdio_log);
        }
    }

    /* Unbuffered output for immediate visibility during debugging */
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    if (stdio_log_err == 0)
        printf("[BOOT] RECOMP_STDIO_LOG: stderr NOT redirected\n");
    /* Deprecated names and bad keys found when the environment was read:
     * held until now, so they land in the log rather than a closed stderr. */
    recomp_env_flush_notes();
}

/* The boot and the guest. On Windows and under RECOMP_HEADLESS it runs on the
 * process main thread; on a windowed POSIX host on the toolkit's guest-main
 * pthread (xbox_HostWindowMain), so the crash handler's alternate stack and
 * the watchdog, both installed here, follow the guest onto that thread. */
static int host_main(void)
{
    void *xbe_data = NULL;
    size_t xbe_size = 0;

    printf("=== Red Dead Revolver - Static Recompilation ===\n");
    printf("Loading XBE...\n");
    xbox_log_thread_role("guest-main", 0);

    /* Step 1: Crash diagnostics, before anything can fault */
    host_install_crash_handler();

    /* Step 2: Load XBE. RECOMP_GAME_FILES and RECOMP_HDD_DIR move the game
     * files and the emulated hard disk out of the working directory and the
     * toolkit's default save root: the CLI's launchers set both, so an
     * installed game keeps its saves outside the program files (and outside
     * any Wine prefix, which Proton may recreate). Unset, the defaults above
     * apply. */
    const char *game_dir_env = recomp_env(RENV_GAME_FILES);
    const char *hdd_dir = recomp_env(RENV_HDD_DIR);
    const char *game_dir = YOUR_GAME_DIR;
    char xbe_path[1024];
    if (hdd_dir && !*hdd_dir)
        hdd_dir = NULL;
    if (game_dir_env && *game_dir_env) {
        int n;
        game_dir = game_dir_env;
        n = snprintf(xbe_path, sizeof(xbe_path), "%s/default.xbe", game_dir);
        if (n < 0 || (size_t)n >= sizeof(xbe_path)) {
            /* A truncated path would open some other file, or none. */
            host_report_fatal("load XBE",
                              "the game files path (RECOMP_GAME_FILES) is too long");
            return 1;
        }
    } else {
        snprintf(xbe_path, sizeof(xbe_path), "%s", YOUR_GAME_XBE_PATH);
    }
    if (!load_xbe(xbe_path, &xbe_data, &xbe_size)) {
        char detail[1400];
        if (game_dir == game_dir_env)
            snprintf(detail, sizeof(detail),
                     "Failed to load %s (from RECOMP_GAME_FILES=%s).",
                     xbe_path, game_dir_env);
        else
            snprintf(detail, sizeof(detail),
                     "Failed to load default.xbe from %s.\n"
                     "Place the game files in " YOUR_GAME_DIR
                     ", or set RECOMP_GAME_FILES.", xbe_path);
        host_report_fatal("load XBE", detail);
        return 1;
    }
    printf("XBE loaded: %zu bytes\n", xbe_size);
    if (!rdr_xbe_supported(xbe_data, xbe_size)) {
        rdr_report_wrong_xbe(xbe_size);
        free(xbe_data);
        return 1;
    }

    /* rdr-port: "Modo experimental" (rdr_menu.ini) turns on run_ahead before
     * the memory layout starts the walker, which reads it once. */
    fast_mode_from_ini();

    /* Step 3: Initialize Xbox memory layout */
    printf("Initializing Xbox memory layout...\n");
    if (!xbox_MemoryLayoutInit(xbe_data, xbe_size)) {
        host_report_fatal("memory layout",
                          "Failed to initialize Xbox memory layout.\n"
                          "The required virtual address range may be unavailable.");
        free(xbe_data);
        return 1;
    }

    g_xbox_mem_offset = xbox_GetMemoryOffset();
    printf("Xbox memory mapped. Offset: 0x%llX\n", (unsigned long long)g_xbox_mem_offset);

    /* D3D's GPU completion fence. XDK D3D keeps a pointer to its device in a
     * global; the device holds the fence it last submitted at +0x2C and, at
     * +0x30, a pointer to the word the GPU writes as it completes work. The
     * toolkit drives PGRAPH 0x400B10, which D3D's wait-for-idle polls, from
     * that word. With RECOMP_PB_EXEC on the executor writes the word itself
     * at each semaphore release and this mirror steps aside after the first
     * one; it stays registered as the catch-up path when a walk stops short
     * of PUT, and as the only fence when the executor is off.
     *
     * The pointer is the game's: 0x2F1FB8 in BLiNX 2, 0x235528 in Spartan,
     * 0x35FB48 in Burnout 3 (XDK 5849; the same two offsets in all three).
     * `xbr new` fills the line in when it finds D3D's fence wait in the
     * dump's D3D section; otherwise find it as the CLI's docs/porting.md
     * ("The D3D fence") says and replace the example below. The runtime's
     * "NV2A fence mirror: ... now written by the executor; mirror off" line
     * confirms it. */
    xbox_Nv2aMirrorFence(0x003497F8, 0x2C, 0x30);   /* Red Dead Revolver, XDK 5849 */

    /* The vblank interrupt, which the toolkit raises only on request. XDK
     * D3D connects the NV2A interrupt during device creation and paces Swap,
     * BlockUntilVerticalBlank and the title's vblank callback on its DPC;
     * without it the boot stops in D3D's first vblank wait. Nothing is
     * delivered until the title connects the ISR and enables the interrupt,
     * so a title that never asks for it only pays a 60 Hz timer. An explicit
     * RECOMP_VBLANK in the environment still wins (=0 turns it off). */
    if (!recomp_env(RENV_VBLANK))
        recomp_env_set(RENV_VBLANK, "1");

    /* D3D8 builds the KEVENT its vblank DPC sets inline, without
     * KeInitializeEvent. The toolkit gives such an event a host event only on
     * request (upstream's ke_guest_event); without it KeSetEvent hands the
     * guest address to the host as a handle, which fails silently on Win32
     * and faults on POSIX. The vblank above needs it, and it does nothing for
     * an event KeInitializeEvent made. An explicit RECOMP_TITLE_KEVENTS in
     * the environment still wins (=0 turns it off). */
    if (!recomp_env(RENV_TITLE_KEVENTS))
        recomp_env_set(RENV_TITLE_KEVENTS, "1");

    /* Bring up the emulated APU.
     *
     * Gated on the same variable that unmaps its registers, because the two
     * halves are useless apart: a trap with no model declines every access,
     * and a model nothing traps into never sees a register. The APU walks
     * Xbox physical RAM to find voice buffers, so it gets the guest RAM
     * base. The toolkit turns RECOMP_AC97_READY on by default only where a
     * fault decoder exists (x86-64 Windows, POSIX arm64). */
    if (recomp_env(RENV_AC97_READY)) {
        g_apu_state = mcpx_apu_init_standalone((uint8_t *)xbox_GetMemoryBase());
        fprintf(stderr, "[BOOT] emulated APU %s\n",
                g_apu_state ? "up" : "FAILED to initialise");
    }

    /* The pad. XAPI is statically linked into the title and reaches the
     * controller by programming the MCPX's USB OHCI registers itself
     * (look for 0xFED00000 in the generated code); nothing in that path goes
     * through a kernel export this runtime could answer. Without the
     * toolkit's controller model the registers read as zeroed RAM, XAPI
     * finds no root hub ports, and no pad -- host, keyboard or
     * RECOMP_PAD_SCRIPT -- ever reaches the title. With it, the host's pad
     * (SDL GameController on POSIX, XInput on Windows; the keyboard merges
     * onto port 0) is presented as an Xbox controller on port 1. Must follow
     * the memory mapping: the model traps the aperture by protecting its
     * pages. A title that overrides XInput itself instead drops these lines.
     * An explicit RECOMP_USB in the environment still wins (=0 turns it
     * off). */
    if (!recomp_env(RENV_USB))
        recomp_env_set(RENV_USB, "1");
    xbox_OhciInit();
    rdr_mouse_init();
    {
        extern void rdr_mouselook_init(void);
        rdr_mouselook_init();
    }
    rdr_graphics_init();
    if (nv2a_tex_pack_count())
        pack_menu_init();
    fast_menu_init();
    /* The F2 menu's saved choices (d3d/host_menu.h) over env.bat's. */
    {
        extern void xbox_MenuLoad(const char *path);
        xbox_MenuLoad("rdr_menu.ini");
    }

    /* Step 4: Initialize Xbox kernel */
    printf("Initializing Xbox kernel replacement...\n");
    xbox_kernel_init();

    /* Step 5: Set game directory for file I/O path translation. A NULL save
     * dir (RECOMP_HDD_DIR unset) puts saves and partition images in the
     * toolkit's default place (beside the game on Windows, $XDG_DATA_HOME or
     * ~/.local/share elsewhere). */
    {
        extern void xbox_path_init(const char *game_dir, const char *save_dir);
        xbox_path_init(game_dir, hdd_dir);
    }

    /* Step 6: Initialize kernel bridge (thunk table in Xbox memory) */
    printf("Initializing kernel bridge...\n");
    xbox_kernel_bridge_init();

    /* Step 7: Initialize stack */
    g_esp = XBOX_STACK_TOP;

    /*
     * TODO: Pre-initialize CRT globals if needed.
     *
     * Many Xbox games use the MSVC CRT. The CRT's __heap_init sets up a
     * heap descriptor at a game-specific address. You may need to
     * pre-initialize __active_heap to avoid small-block heap issues:
     *
     *   uint32_t *active_heap = (uint32_t *)((uint8_t *)g_xbox_mem_offset + ACTIVE_HEAP_VA);
     *   *active_heap = 1;  // 1 = system heap (HeapAlloc), avoids SBH init
     *
     * Find ACTIVE_HEAP_VA by searching the disassembly for __heap_init
     * or by looking for the CRT's __active_heap global in the data section.
     */

    printf("\n=== Initialization complete ===\n");
    printf("Entry point: 0x%08X\n", YOUR_GAME_ENTRY_POINT);
    printf("ESP: 0x%08X\n", g_esp);

    /* Build the flat dispatch table before the guest runs.
     *
     * Without this recomp_lookup falls back to a binary search over the
     * whole function table -- roughly log2(n) branches on *every*
     * indirect call, which for a 45,000-function C++ title is about 16
     * every time the game goes through a vtable. Half-Life 2 spent most
     * of its static initialisation inside recomp_lookup for exactly this
     * reason, and it read as a hang.
     *
     * Optional by design: if the allocation fails the search still works,
     * so a failure is worth one line and not a fatal error. */
    if (!recomp_dispatch_init())
        fprintf(stderr, "[BOOT] flat dispatch unavailable; "
                        "indirect calls will use the binary search\n");

    /* Arm the hang watchdog. Does nothing unless RECOMP_WATCHDOG_SECS is set,
     * and must be called from this thread -- the guest registers it samples are
     * thread-local, so it has to be handed the copies belonging to the thread
     * that runs guest code.
     *
     * Not optional boilerplate: without this call RECOMP_WATCHDOG_SECS is
     * silently inert, and the one diagnostic that tells a hang from slowness
     * does nothing while appearing to be set. */
    xbox_WatchdogStart();
    zwatch_start();
    scan_start();

    /* Step 8: Call the recompiled entry point */
    printf("\nStarting game...\n");
    fflush(stdout);

    xbe_entry_point();

    printf("\nGame returned. Cleaning up...\n");

    /* Cleanup */
    xbox_kernel_shutdown();
    xbox_MemoryLayoutShutdown();
    free(xbe_data);

    return 0;
}

/* ── XBE Loading ───────────────────────────────────────────── */

static BOOL load_xbe(const char *path, void **out_data, size_t *out_size)
{
    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "Cannot open XBE: %s\n", path);
        return FALSE;
    }

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (size <= 0) {
        fclose(f);
        return FALSE;
    }

    void *data = malloc((size_t)size);
    if (!data) {
        fclose(f);
        return FALSE;
    }

    if (fread(data, 1, (size_t)size, f) != (size_t)size) {
        free(data);
        fclose(f);
        return FALSE;
    }

    fclose(f);
    *out_data = data;
    *out_size = (size_t)size;
    return TRUE;
}

/* ── Entry points ──────────────────────────────────────────── */

/* The enhancements (render scale, present filter, fullscreen, pacing):
 * config.default.toml beside the executable, config/config.toml over it,
 * the environment over both, every key stock by default. The user root is
 * the working directory: a developer runs from the project root, as
 * YOUR_GAME_DIR already assumes, so their choices live in a gitignored
 * config/config.toml and no source path is baked into the binary; a
 * bundle's launcher names the file with RECOMP_CONFIG, so there the root
 * is never used. Before any thread, so the backends, the window and the
 * kernel read settled values. Without the layer (-DXBOXRECOMP_ENHANCE=OFF)
 * this is nothing.
 *
 * A game's own keys (enhance_cfg_bind_env, enhance_cfg_choice, ...) are read
 * between the two calls, so a file that sets one is not told the key is
 * unknown. */
/* F2 row for the texture pack: its images on or off, to compare in the game
 * at once (F6 toggles the same, nv2a_pb_d3d11.c). */
static const char *const k_pack_onoff[] = { "No", "Sí", NULL };
static int get_pack_art(void) { return nv2a_tex_pack_kind_enabled(XRTP_KIND_ART); }
static void set_pack_art(int i)
{
    nv2a_tex_pack_set_kind_enabled(XRTP_KIND_ART, i);
    nv2a_tex_pack_set_kind_enabled(XRTP_KIND_FONT, i);
}
/* The buttons drawn on screen: the pack's kind BUTTON entries in this style
 * (tools/botones_estilo.py), whatever "Texturas mejoradas" (F6) says. Saved
 * as botones in rdr_menu.ini. Automático (the default) follows the device
 * last used (xbox_InputLastDevice), checked by btn_auto_thread; a style
 * picked by hand stays, in this run and the next. */
static const char *const k_btn_style[] = {
    "Automático", "Teclado y ratón", "Mando Xbox", "Mando PS4/PS5", NULL
};
static volatile int s_btn_choice;           /* 0 automatic, else style + 1 */
static int get_btn_style(void) { return s_btn_choice; }
static void set_btn_style(int i)
{
    s_btn_choice = i;
    if (i > 0)
        nv2a_tex_pack_set_button_style(i - 1);
    else if (xbox_InputLastDevice() >= 0)
        nv2a_tex_pack_set_button_style(xbox_InputLastDevice());
}
static DWORD WINAPI btn_auto_thread(LPVOID unused)
{
    (void)unused;
    for (;;) {
        int d = xbox_InputLastDevice();
        if (s_btn_choice == 0 && d >= 0 && d != nv2a_tex_pack_button_style())
            nv2a_tex_pack_set_button_style(d);
        Sleep(150);
    }
}
/* Subtitles are always on (movies.c); the row was taken out at the user's
 * request. */
static const xbox_menu_item k_pack_rows[] = {
    { NULL, "Texturas", NULL, NULL, NULL },
    { "pack_art", "Texturas mejoradas", k_pack_onoff, get_pack_art, set_pack_art },
    { "botones", "Botones en pantalla", k_btn_style, get_btn_style, set_btn_style },
};

/* "Modo experimental" (PC de gama baja): RECOMP_DEBUG=run_ahead=1. The game
 * thread waited at every D3D KickOff for the walker to finish the segment
 * before it (sub_0033EDE0, 22% of the game thread on an i5-3330); with it the
 * two overlap (13%, +5-8 fps there). The walker reads the key once, before
 * the F2 menu exists, so the ini line is read here first and the row only
 * records the choice for the next start. An explicit run_ahead in the
 * environment wins. */
static const char *const k_fast_mode[] = { "No", "Sí (PC gama baja)", NULL };
static int s_fast_choice;
static int get_fast_mode(void) { return s_fast_choice; }
static void set_fast_mode(int i) { s_fast_choice = i; }
static const xbox_menu_item k_fast_rows[] = {
    { NULL, "Rendimiento", NULL, NULL, NULL },
    { "modo_rapido", "Modo experimental (al reiniciar)", k_fast_mode, get_fast_mode, set_fast_mode },
};

static void fast_menu_init(void)
{
    xbox_MenuAdd(&k_fast_rows[0]);
    xbox_MenuAdd(&k_fast_rows[1]);
}

static void fast_mode_from_ini(void)
{
    char line[256];
    FILE *f = fopen("rdr_menu.ini", "r");
    if (f) {
        while (fgets(line, sizeof line, f)) {
            line[strcspn(line, "\r\n")] = 0;
            if (!strncmp(line, "modo_rapido=", 12))
                s_fast_choice = strcmp(line + 12, k_fast_mode[1]) == 0;
        }
        fclose(f);
    }
    if (s_fast_choice && !recomp_env(RENV_RUN_AHEAD))
        recomp_env_set(RENV_RUN_AHEAD, "1");
    fprintf(stderr, "[rdr] modo experimental: %s\n",
            recomp_env(RENV_RUN_AHEAD) && strcmp(recomp_env(RENV_RUN_AHEAD), "0")
                ? "on (run_ahead)" : "off");
}

static void pack_menu_init(void)
{
    size_t i;
    if (nv2a_tex_pack_button_style() < 0)
        nv2a_tex_pack_set_button_style(0);   /* keyboard until something is used */
    CreateThread(NULL, 0, btn_auto_thread, NULL, 0, NULL);
    for (i = 0; i < sizeof k_pack_rows / sizeof k_pack_rows[0]; i++)
        xbox_MenuAdd(&k_pack_rows[i]);
}

static void host_enhance_init(void)
{
#ifdef RECOMP_ENV_HAVE_ENHANCE_KEYS
    xbox_enhance_init(".", NULL);
    enhance_cfg_report_unused();
    fflush(stderr);
#else
    /* Without the layer nothing loaded RECOMP_TEXTURES_PACK (env.bat), so the
     * upscaled textures and fonts never reached the screen: load it here. */
    const char *pack = getenv("RECOMP_TEXTURES_PACK");
    char err[128];
    int n;
    if (pack && *pack) {
        n = nv2a_tex_pack_load(pack, err, sizeof err);
        if (n < 0)
            fprintf(stderr, "[rdr] textures.pack %s: %s; no pack\n", pack, err);
        else
            fprintf(stderr, "[rdr] textures.pack %s: %d entries (%u font)\n", pack, n,
                    nv2a_tex_pack_kind_count(XRTP_KIND_FONT));
        fflush(stderr);
    }
#endif
}

#if defined(_WIN32)
/* rdr-port: the release layout, next to the exe:
 *     Game\         the player's own game folder (default.xbe and the .dat),
 *                   or one folder inside it holding them
 *     Mods-Extras\  videos\<name>.mp4, texturas\textures.pack, replaced files
 * When Game\ has the game, every setting env.bat would give is set here
 * (unless the environment already has it), so the exe runs on its own. */
static void set_default(const char *k, const char *v)
{
    if (!getenv(k))
        _putenv_s(k, v);
}

/* The first file called `name` (any case) in dir or its subfolders, up to
 * `depth` levels down, into out; 0 when none. Skips texture dump folders.
 * movies.c finds the videos with it too. */
int rdr_find_file(const char *dir, const char *name, char *out, size_t n, int depth)
{
    WIN32_FIND_DATAA fd;
    HANDLE h;
    char p[MAX_PATH * 2];
    DWORD a;
    int found = 0;

    snprintf(p, sizeof p, "%s\\%s", dir, name);
    a = GetFileAttributesA(p);
    if (a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY)) {
        snprintf(out, n, "%s", p);
        return 1;
    }
    if (depth <= 0)
        return 0;
    snprintf(p, sizeof p, "%s\\*", dir);
    h = FindFirstFileA(p, &fd);
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    do {
        if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && fd.cFileName[0] != '.'
                && _stricmp(fd.cFileName, "dump") != 0) {
            snprintf(p, sizeof p, "%s\\%s", dir, fd.cFileName);
            found = rdr_find_file(p, name, out, n, depth - 1);
        }
    } while (!found && FindNextFileA(h, &fd));
    FindClose(h);
    return found;
}

static void portable_defaults(void)
{
    static const char *const env[][2] = {
        { "RECOMP_AC97_READY", "1" }, { "RECOMP_PB_EXEC", "1" },
        { "RECOMP_PB_BACKEND", "d3d11" }, { "RECOMP_VBLANK", "paced" },
        { "RECOMP_KEYBOARD", "1" }, { "RECOMP_MOUSE", "1" },
        { "RDR_MOUSE_LOOK", "direct" }, { "RDR_MOUSE_SENS", "3" },
        { "RDR_MOUSE_AIM_MULT", "2.0" }, { "RDR_MOUSE_MIN", "0.3" },
        { "RDR_MOUSE_INVERT_Y", "0" }, { "RDR_MOUSE_CAP", "0" },
        { "RECOMP_CONTIG_AVOID_IMAGE", "1" }, { "RDR_RENDER_SCALE", "2" },
        { "RDR_ANISO", "16" }, { "RDR_ASPECT", "4:3" }, { "RECOMP_WIDESCREEN", "1" },
        { "RECOMP_LANGUAGE", "es" }, { "RECOMP_TEXTURES_DUMP", "0" },
        { "RDR_FULLSCREEN", "0" }, { "RECOMP_D3D11_SKIP_RT", "1" },
    };
    char root[MAX_PATH], game[MAX_PATH + 16], p[MAX_PATH + 64];
    char *slash;
    size_t i;

    if (!GetModuleFileNameA(NULL, root, sizeof root) || !(slash = strrchr(root, '\\')))
        return;
    *slash = 0;
    snprintf(game, sizeof game, "%s\\Game", root);
    /* the game anywhere inside Game\ (pasted whole, or in folders of its own) */
    if (!rdr_find_file(game, "default.xbe", p, sizeof p, 4))
        return;
    *strrchr(p, '\\') = 0;
    snprintf(game, sizeof game, "%s", p);
    SetCurrentDirectoryA(root);             /* rdr_menu.ini, logs */
    snprintf(p, sizeof p, "%s\\registro.txt", root);    /* the run's log, for support */
    set_default("RECOMP_STDIO_LOG", p);
    set_default("RECOMP_TRACE", "tex_pack");
    set_default("RECOMP_GAME_FILES", game);
    for (i = 0; i < sizeof env / sizeof env[0]; i++)
        set_default(env[i][0], env[i][1]);
    snprintf(p, sizeof p, "%s\\Mods-Extras", root);
    CreateDirectoryA(p, NULL);
    set_default("RECOMP_MODS_DIR", p);
    snprintf(p, sizeof p, "%s\\Mods-Extras\\texturas\\dump", root);
    set_default("RECOMP_TEXTURES_DUMP_DIR", p);
    {
        char mods[MAX_PATH + 16], pack[MAX_PATH * 2];
        snprintf(mods, sizeof mods, "%s\\Mods-Extras", root);
        if (rdr_find_file(mods, "textures.pack", pack, sizeof pack, 4))
            set_default("RECOMP_TEXTURES_PACK", pack);
    }
}

/* The Windows build links as a GUI-subsystem program, which starts here. */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow)
{
    (void)hInstance;
    (void)hPrevInstance;
    (void)lpCmdLine;
    (void)nCmdShow;
    portable_defaults();
    recomp_env_init();   /* the environment, read once, before any thread */
    host_stdio_setup();
    host_enhance_init();
    xbox_log_thread_role("process-main", 0);
    xbox_HostWindowSetTitle("Red Dead Revolver");
    return host_main();
}
#endif

/* Console entry point: every non-Windows host, and console builds on Windows
 * (for debugging -- lets you see printf output).
 *
 * POSIX: the process main thread belongs to the window. AppKit only runs its
 * event loop there, so xbox_HostWindowMain (toolkit fb_present_sdl.c) opens
 * an SDL window here and runs host_main -- the whole boot and the guest --
 * on a "guest-main" pthread. RECOMP_HEADLESS=1 keeps the guest on this
 * thread with no window. */
int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    recomp_env_init();   /* the environment, read once, before any thread */
    host_stdio_setup();
    host_enhance_init();
    /* The initial thread, named first: the toolkit leaves its OS name alone
     * (renaming it breaks pgrep/ps). host_main then logs guest-main, on this
     * thread when headless or on Windows, on its own pthread when windowed. */
    xbox_log_thread_role("process-main", 0);
    /* The window's title bar; without it, the certificate's name. */
    xbox_HostWindowSetTitle("Red Dead Revolver");
#if defined(_WIN32)
    return host_main();
#else
#if defined(__APPLE__)
    /* Metal is the Mac's backend unless RECOMP_PB_BACKEND says otherwise: the
     * CPU rasteriser runs a title at a few frames a second there.
     * RECOMP_PB_BACKEND=cpu still asks for it. Set before the window reads
     * it, since a Metal window is a CAMetalLayer one. */
    {
        const char *be = recomp_env(RENV_PB_BACKEND);
        if (!be || !*be)
            recomp_env_set(RENV_PB_BACKEND, "metal");
    }
#endif
    return xbox_HostWindowMain(host_main);
#endif
}

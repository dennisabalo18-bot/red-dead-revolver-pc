/*
 * sampler -- a tiny sampling profiler for rdr_recomp.exe.
 *
 *   sampler <pid> [seconds=10] [interval_ms=1]
 *
 * Suspends every thread of the process at a fixed rate, reads its RIP,
 * resumes it, and at the end prints where the time went: per symbol overall,
 * and the top symbols of each busy thread. Symbols come from the exe's PDB
 * (runtime functions, and the public sub_XXXXXXXX names of the generated
 * guest code). Read-only apart from the brief suspends.
 */
#include <windows.h>
#include <dbghelp.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_THREADS 256
#define MAX_SYMS    8192

typedef struct { DWORD tid; HANDLE h; unsigned long samples, running; } Thr;
typedef struct { char name[160]; unsigned long hits; unsigned long per_thr[MAX_THREADS]; } Sym;

static Thr  s_thr[MAX_THREADS];
static int  s_nthr;
static Sym  s_sym[MAX_SYMS];
static int  s_nsym;
static HANDLE s_proc;

static void refresh_threads(DWORD pid)
{
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    THREADENTRY32 te;
    te.dwSize = sizeof te;
    if (snap == INVALID_HANDLE_VALUE)
        return;
    for (BOOL ok = Thread32First(snap, &te); ok; ok = Thread32Next(snap, &te)) {
        int i;
        if (te.th32OwnerProcessID != pid)
            continue;
        for (i = 0; i < s_nthr && s_thr[i].tid != te.th32ThreadID; i++)
            ;
        if (i < s_nthr || s_nthr == MAX_THREADS)
            continue;
        s_thr[s_nthr].tid = te.th32ThreadID;
        s_thr[s_nthr].h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT
                                     | THREAD_QUERY_INFORMATION, FALSE,
                                     te.th32ThreadID);
        if (s_thr[s_nthr].h)
            s_nthr++;
    }
    CloseHandle(snap);
}

/* Address -> symbol name, with a small direct-mapped cache. */
static const char *name_of(DWORD64 rip, char *buf, size_t n)
{
    static struct { DWORD64 rip; char name[160]; } cache[65536];
    unsigned slot = (unsigned)((rip >> 2) & 0xFFFF);
    char sbuf[sizeof(SYMBOL_INFO) + 256];
    SYMBOL_INFO *si = (SYMBOL_INFO *)sbuf;
    DWORD64 disp = 0;
    IMAGEHLP_MODULE64 mod;

    if (cache[slot].rip == rip)
        return cache[slot].name;
    memset(sbuf, 0, sizeof sbuf);
    si->SizeOfStruct = sizeof(SYMBOL_INFO);
    si->MaxNameLen = 255;
    mod.SizeOfStruct = sizeof mod;
    if (SymFromAddr(s_proc, rip, &disp, si)) {
        const char *m = SymGetModuleInfo64(s_proc, rip, &mod) ? mod.ModuleName : "?";
        _snprintf(buf, n, "%s!%s", m, si->Name);
    } else if (SymGetModuleInfo64(s_proc, rip, &mod)) {
        _snprintf(buf, n, "%s!?", mod.ModuleName);
    } else {
        _snprintf(buf, n, "?");
    }
    buf[n - 1] = 0;
    cache[slot].rip = rip;
    strncpy(cache[slot].name, buf, sizeof cache[slot].name - 1);
    return cache[slot].name;
}

static Sym *sym_get(const char *name)
{
    int i;
    for (i = 0; i < s_nsym; i++)
        if (!strcmp(s_sym[i].name, name))
            return &s_sym[i];
    if (s_nsym == MAX_SYMS)
        return NULL;
    strncpy(s_sym[s_nsym].name, name, sizeof s_sym[0].name - 1);
    return &s_sym[s_nsym++];
}

static int is_wait(const char *n)
{
    return strstr(n, "ntdll!NtWait") || strstr(n, "ntdll!ZwWait")
        || strstr(n, "ntdll!NtDelay") || strstr(n, "ntdll!ZwDelay")
        || strstr(n, "ntdll!NtRemoveIoCompletion") || strstr(n, "win32u!")
        || strstr(n, "ntdll!NtYield") || strstr(n, "ntdll!ZwYield");
}

static int by_hits(const void *a, const void *b)
{
    const Sym *x = (const Sym *)a, *y = (const Sym *)b;
    return (y->hits > x->hits) - (y->hits < x->hits);
}

int main(int argc, char **argv)
{
    DWORD pid;
    int secs, interval, t, i;
    unsigned long total = 0, guest = 0, waiting = 0;
    char buf[160];
    DWORD start;

    if (argc < 2) {
        fprintf(stderr, "usage: sampler <pid> [seconds] [interval_ms]\n");
        return 1;
    }
    pid = (DWORD)atoi(argv[1]);
    secs = argc > 2 ? atoi(argv[2]) : 10;
    interval = argc > 3 ? atoi(argv[3]) : 1;

    s_proc = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid);
    if (!s_proc) {
        fprintf(stderr, "OpenProcess failed: %lu\n", GetLastError());
        return 1;
    }
    SymSetOptions(SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS);
    if (!SymInitialize(s_proc, NULL, TRUE)) {
        fprintf(stderr, "SymInitialize failed: %lu\n", GetLastError());
        return 1;
    }
    timeBeginPeriod(1);

    start = GetTickCount();
    for (t = 0; GetTickCount() - start < (DWORD)secs * 1000u; t++) {
        if (t % 200 == 0)
            refresh_threads(pid);
        for (i = 0; i < s_nthr; i++) {
            CONTEXT ctx;
            const char *n;
            Sym *s;
            if (SuspendThread(s_thr[i].h) == (DWORD)-1)
                continue;
            ctx.ContextFlags = CONTEXT_CONTROL;
            if (!GetThreadContext(s_thr[i].h, &ctx)) {
                ResumeThread(s_thr[i].h);
                continue;
            }
            ResumeThread(s_thr[i].h);
            n = name_of(ctx.Rip, buf, sizeof buf);
            s_thr[i].samples++;
            total++;
            if (is_wait(n)) {
                waiting++;
                continue;
            }
            s_thr[i].running++;
            if (strstr(n, "!sub_"))
                guest++;
            if ((s = sym_get(n)) != NULL) {
                s->hits++;
                s->per_thr[i]++;
            }
        }
        Sleep((DWORD)interval);
    }

    {
        unsigned long busy = total - waiting;
        printf("samples %lu over %d threads; busy %lu (%.1f%%), guest code %.1f%% of busy\n\n",
               total, s_nthr, busy, total ? 100.0 * busy / total : 0.0,
               busy ? 100.0 * guest / busy : 0.0);
    }
    printf("busy threads (share of samples spent running):\n");
    for (i = 0; i < s_nthr; i++) {
        if (s_thr[i].samples && s_thr[i].running * 20 >= s_thr[i].samples) {
            unsigned long best = 0; int b = -1, k;
            for (k = 0; k < s_nsym; k++)
                if (s_sym[k].per_thr[i] > best) { best = s_sym[k].per_thr[i]; b = k; }
            printf("  tid %6lu  %5.1f%%  top: %s (%.0f%% of its busy)\n",
                   s_thr[i].tid, 100.0 * s_thr[i].running / s_thr[i].samples,
                   b >= 0 ? s_sym[b].name : "-",
                   b >= 0 ? 100.0 * best / s_thr[i].running : 0.0);
        }
    }

    /* The breakdown of each saturated thread: a serial bottleneck shows up
     * here and is averaged away in the overall table. */
    for (i = 0; i < s_nthr; i++) {
        unsigned long shown = 0;
        int k, rank;
        if (!s_thr[i].samples || s_thr[i].running * 2 < s_thr[i].samples)
            continue;
        printf("\nthread %lu (%.1f%% busy) top functions:\n", s_thr[i].tid,
               100.0 * s_thr[i].running / s_thr[i].samples);
        for (rank = 0; rank < 12; rank++) {
            unsigned long best = 0; int b = -1;
            for (k = 0; k < s_nsym; k++)
                if (s_sym[k].per_thr[i] > best
                        && (rank == 0 || s_sym[k].per_thr[i] < shown
                            || (s_sym[k].per_thr[i] == shown && 0))) {
                    best = s_sym[k].per_thr[i]; b = k;
                }
            if (b < 0)
                break;
            printf("    %5.1f%%  %s\n", 100.0 * best / s_thr[i].running, s_sym[b].name);
            shown = best;
        }
    }

    qsort(s_sym, (size_t)s_nsym, sizeof s_sym[0], by_hits);
    printf("\nhottest symbols (share of all busy samples):\n");
    {
        unsigned long busy = total - waiting;
        for (i = 0; i < s_nsym && i < 45; i++)
            printf("  %5.1f%%  %s\n", busy ? 100.0 * s_sym[i].hits / busy : 0.0,
                   s_sym[i].name);
    }
    timeEndPeriod(1);
    return 0;
}

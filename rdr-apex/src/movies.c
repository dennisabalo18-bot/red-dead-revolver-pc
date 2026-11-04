/*
 * The cutscenes from mods\videos\<name>.mp4 when there is one.
 *
 * sub_00071080(names, count, ...) starts the game's Bink player on a list of
 * movie names ("bridge01"), built into <disc>bik\<name>.bik by sub_00070FB0,
 * and returns 1 when it started, 0 when it could not (a file missing): the
 * callers then go on as after the movie (sub_00070BA0 calls sub_00071200;
 * the boot's rslogo ignores the result). When every name of the list has an
 * MP4 under RECOMP_MODS_DIR\videos, the D3D11 backend plays them here
 * instead (nv2a_d3d11_movie: blocks, the guest paused) and this returns as
 * a missing file does, after the same set-up (the movie's pacing mode,
 * sub_0017E7F0(4, 0), and the flag at 0x0041095C). An MP4 that will not play
 * falls back to the game's own.
 *
 * recomp_0009.c's definition is renamed sub_00071080_pad (tools/rename_pads.py).
 */
#include <stdio.h>
#include <stdlib.h>
#include <windows.h>
#include "recomp/gen/recomp_types.h"

void sub_00071080_pad(void);
void sub_00072110_pad(void);
void sub_0017E7F0(void);
int  nv2a_d3d11_movie(const char *path);
int  rdr_find_file(const char *dir, const char *name, char *out, size_t n, int depth);

#define MAX_MOVIES 8

static int movie_path(uint32_t name_va, char *out, size_t n)
{
    const char *mods = getenv("RECOMP_MODS_DIR");
    char name[64], rel[MAX_PATH];
    size_t i;

    if (!mods || !*mods || !name_va)
        return 0;
    for (i = 0; i < sizeof name - 1 && (name[i] = (char)MEM8(name_va + i)); i++)
        ;
    name[i] = 0;
    if (!i || i == sizeof name - 1)
        return 0;
    /* Whole: env.bat's is relative to rdr-apex ("..\modding\mods"). */
    snprintf(rel, sizeof rel, "%s\\videos\\%s.mp4", mods, name);
    if (!GetFullPathNameA(rel, (DWORD)n, out, NULL))
        return 0;
    if (GetFileAttributesA(out) != INVALID_FILE_ATTRIBUTES)
        return 1;
    {   /* rdr-port: or in any subfolder of the mods folder */
        char file[80], full[MAX_PATH];
        snprintf(file, sizeof file, "%s.mp4", name);
        if (!GetFullPathNameA(mods, sizeof full, full, NULL))
            return 0;
        return rdr_find_file(full, file, out, n, 4);
    }
}

void sub_00071080(void)
{
    char paths[MAX_MOVIES][MAX_PATH];
    uint32_t names = MEM32(g_esp + 4), count = MEM32(g_esp + 8), i;
    int played = 0;

    if (count < 1 || count > MAX_MOVIES) {
        sub_00071080_pad();
        return;
    }
    for (i = 0; i < count; i++)
        if (!movie_path(MEM32(names + i * 4), paths[i], MAX_PATH)) {
            sub_00071080_pad();
            return;
        }
    for (i = 0; i < count; i++) {
        if (nv2a_d3d11_movie(paths[i]))
            played = 1;
        else if (!played) {
            fprintf(stderr, "[MOVIE] %s did not play: the game's own movie\n", paths[i]);
            sub_00071080_pad();
            return;
        }
    }
    MEM32(0x410960) = MEM32(0x413D1C);
    PUSH32(g_esp, 0);
    PUSH32(g_esp, 4);
    PUSH32(g_esp, 0x0007109Fu);
    sub_0017E7F0();
    g_esp += 8;
    MEM8(0x41095C) = 1;
    g_eax = 0;
    g_esp += 4;                        /* ret */
}

/* Subtitles. The game shows them only while bit 1 of its options word
 * (MEM32(0x664260) + 0x5C, the in-game "Subtitles" row) is set. It sets it
 * at boot when the language is not English, but a profile saved in English
 * clears it again, so the Spanish lines never show. sub_00072110 draws the
 * subtitle in progress and tests that bit first: with "Subtitulos siempre"
 * (F2, on by default) the bit is set before it looks. */
static int s_subtitles_always = 1;

int  rdr_subtitles_always(void) { return s_subtitles_always; }
void rdr_subtitles_always_set(int on) { s_subtitles_always = on; }

void sub_00072110(void)
{
    uint32_t opts = MEM32(0x664260);
    if (s_subtitles_always && opts)
        MEM32(opts + 0x5C) |= 2;
    sub_00072110_pad();
}

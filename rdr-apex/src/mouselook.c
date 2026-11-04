/*
 * Mouse look as BLACK's port does it: the mouse turns the camera by a fixed
 * angle per count, with no dead zone, curve or smoothing in between.
 *
 * RDR's cameras read the right stick through sub_00028D20 (thiscall on the
 * pad manager, one out pointer: the stick as two floats in -1..1, (0, 0)
 * while both axes are inside 0.4). Two cameras call it:
 *
 *   sub_00045710 (returns to 0x0004597A): eases its own copy
 *     [esi+0xE4], [esi+0xE8] towards the stick at 4 units a second
 *     (sub_00020770), clamps it to -1..1 and turns by copy * -0.2 per frame
 *     (sub_00049750 yaw, sub_000496A0 pitch).
 *   sub_00040E90 (returns to 0x00041834): eases [esi+0x738], [esi+0x73C]
 *     towards stick - [esi+0x730/0x734] at a rate from its settings, and
 *     turns by copy * dt * speed ([[esi+0x6E4]+0x1E0], dt at 0x004109A4).
 *
 * The dead zone swallowed slow motion and the easing lagged every turn by
 * a quarter second. Here the counts since the last read become the value
 * that turns the camera by counts * degrees-per-count, written to the
 * caller's eased copy as well so the easing has nothing left to do. With no
 * mouse motion the pad's stick is read as before.
 *
 * recomp_0002.c's definition is renamed sub_00028D20_pad (CMakeLists.txt),
 * so the game's direct calls land here.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "recomp/gen/recomp_types.h"
#include "input/mouse.h"
#include "input/host_pad.h"
#include "input/input_names.h"
#include "d3d/host_menu.h"

void sub_00028D20_pad(void);

#define RET_FREE_CAM   0x0004597Au     /* sub_00045710 */
#define RET_PLAYER_CAM 0x00041834u     /* sub_00040E90 */
#define GAME_DT        0x004109A4u
#define PI_F           3.14159265f

static float s_deg_per_count = 0.06f;  /* BLACK's PC_DEGREES_PER_COUNT */
/* Aiming at 200 % by default: the user's pick, with the reticle's own speed
 * (LockedCursor*) flattened while aiming. */
static float s_sens = 1.0f, s_aim_mult = 2.0f, s_ysens = 1.0f;
/* The stick value the mouse may send in one frame, in full deflections; 0
 * is no limit. The right stick reaches the game's parameters unclamped
 * (sub_0013FCF0 stores it as read; only the left stick is cut to length
 * 1), so above 1 a fast move turns faster than the pad can. */
static float s_cap = 0.0f;
static int   s_invert_y, s_on;

static void menu_init(void);

void rdr_mouselook_init(void)
{
    const char *e = getenv("RDR_MOUSE_LOOK");

    s_on = !(e && !strcmp(e, "stick"));
    if ((e = getenv("RDR_MOUSE_SENS")) && *e)
        s_sens = (float)atof(e);
    if ((e = getenv("RDR_MOUSE_AIM_MULT")) && *e)
        s_aim_mult = (float)atof(e);
    if ((e = getenv("RDR_MOUSE_INVERT_Y")) && *e == '1')
        s_invert_y = 1;
    if (s_sens < 0.1f) s_sens = 0.1f;
    if (s_sens > 20.0f) s_sens = 20.0f;
    if ((e = getenv("RDR_MOUSE_CAP")) && *e)
        s_cap = (float)atof(e);
    xbox_InputMouseDirect(s_on);
    menu_init();
}

/* The game's frame counter: sub_00084100, the frame timer that also sets
 * the frame's dt (GAME_DT), adds 1 to it once a frame. */
#define GAME_FRAME     0x00666738u

/* The counts for this game frame. Several readers ask within one frame
 * (sub_0013FCF0 twice, a camera besides): the first read of a new game frame
 * takes the counts gathered since the last, the rest of the frame gets the
 * same. Frames were told apart by time (a read more than 4 ms after the
 * last) until a video showed the turn jerking: two frames run back to back
 * to catch up got the same counts twice, and two reads of one slow frame
 * split its counts. After 150 ms with no new frame the backlog (gathered in
 * a menu or a pause) is dropped. */
static int frame_counts(int *dx, int *dy, int *fresh)
{
    static LARGE_INTEGER last, freq;
    static uint32_t last_frame;
    static int fx, fy;
    LARGE_INTEGER now;
    uint32_t frame = MEM32(GAME_FRAME);
    double ms;

    if (!freq.QuadPart)
        QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&now);
    ms = (double)(now.QuadPart - last.QuadPart) * 1000.0 / (double)freq.QuadPart;
    *fresh = 0;
    if (frame != last_frame) {
        last_frame = frame;
        xbox_InputMouseTakeLook(&fx, &fy);
        if (abs(fx) + abs(fy) > 6)
            xbox_InputNoteDevice(0);   /* the mouse moved: keyboard buttons */
        *fresh = 1;
        if (ms > 150.0) {
            fx = fy = 0;
            *fresh = 2;
        }
        last = now;
    }
    *dx = fx;
    *dy = fy;
    return fx || fy;
}

/* Turn per count in radians, the aim button's multiplier included. */
static float look_rad(void)
{
    float rad = s_deg_per_count * s_sens * PI_F / 180.0f;
    if (xbox_InputMouseHeld(XBOX_MOUSE_RIGHT))
        rad *= s_aim_mult;
    return rad;
}

/* RDR_MOUSE_TRACE=1: every 2 s, which call sites read the right stick
 * (sub_00027980 x, sub_000279D0 y) while it is off centre, and which
 * called sub_00028D20 and whether with mouse counts. To find the camera
 * that reads it: move it with IJKL, then with the mouse. */
static int s_trace = -1;
static struct { uint32_t ret; char what; unsigned n; } s_hits[48];

static void trace_hit(char what, uint32_t ret)
{
    static DWORD dumped;
    DWORD now = GetTickCount();
    int i;

    for (i = 0; i < 48; i++) {
        if (s_hits[i].n && s_hits[i].ret == ret && s_hits[i].what == what) {
            s_hits[i].n++;
            break;
        }
        if (!s_hits[i].n) {
            s_hits[i].ret = ret;
            s_hits[i].what = what;
            s_hits[i].n = 1;
            break;
        }
    }
    if (now - dumped < 2000)
        return;
    dumped = now;
    for (i = 0; i < 48 && s_hits[i].n; i++)
        fprintf(stderr, "[LOOKTRACE] %c ret=0x%08X n=%u\n",
                s_hits[i].what, s_hits[i].ret, s_hits[i].n);
    fprintf(stderr, "[LOOKTRACE] --\n");
    fflush(stderr);
    memset(s_hits, 0, sizeof s_hits);
}

static int trace_on(void)
{
    if (s_trace < 0) {
        const char *e = getenv("RDR_MOUSE_TRACE");
        s_trace = e && *e == '1';
    }
    return s_trace;
}

/* sub_001A8DD0(axis): the controller-config layer's axis read; axis maps
 * through the table at 0x004164D0 to 0..3 = left x, left y, right x, right
 * y. sub_001A98C0 reads a stick through it for most of the game. Traced:
 * who reads the right stick while it is pushed past 0.3 ('X', 'Y'), and
 * which sub_001A98C0 call that happened under ('G'). */
void sub_001A8DD0_pad(void);
void sub_001A98C0_pad(void);
static int s_rs_seen;

void sub_001A8DD0(void)
{
    uint32_t ret = MEM32(g_esp), axis = MEM32(g_esp + 4);
    sub_001A8DD0_pad();
    if (trace_on() && axis < 64) {
        uint32_t m = MEM32(0x004164D0u + axis * 4u);
        if ((m == 2 || m == 3) && fabs(g_fp_stack[g_fp_top]) > 0.3) {
            trace_hit(m == 2 ? 'X' : 'Y', ret);
            s_rs_seen = 1;
        }
    }
}

/* sub_001A98C0(stick, out, dead-zone mode, mask), thiscall, ret 0x10:
 * stick 0 left, 1 right, as two floats at out after the dead zone and the
 * response curve. The game's player input (sub_0013FCF0 and five like it,
 * one per kind of play) reads the right stick here every frame. With mouse
 * motion the right stick is the mouse instead, straight: no dead zone, no
 * curve, the turn the counts ask for at the 60 Hz frame
 * (STICK_RAD_PER_SEC at full deflection), with no clamp: the value reaches
 * the camera's inputs (LookstickX/Y, ids 0xC/0xD of the camera machine's
 * input table, sub_001D46A0) as read, and its shaped copy AimRampX/Y
 * (0xE/0xF) goes through sub_0014DB20/sub_0014DBF0, made linear below while
 * the mouse drives the stick. */
#define STICK_RAD_PER_SEC 2.0f

/* 1 while this frame's right stick is the mouse's (set by sub_001A98C0, read
 * by the response curves that follow it in the same player input call). */
static int s_ramp;

/* Aiming (right button held) with the mouse: the two parts of the game's aim
 * assist that pulled the reticle onto enemies are off. They are globals the
 * game registers by name (sub_00192370) and its tuning files may rewrite:
 * AimRampCrossingSoftLockRate (0.5: the aim slowed to half over a target)
 * and TargetDriftAccel (0.1: a still reticle drifted onto it). The lock
 * itself is kept (the shots go where it says) but made tight: the game
 * took a target with the reticle within 1.4 target circles and let go of
 * it only past 1.8, so the hand had to drag well clear of an enemy before
 * the reticle (and the camera framing it) followed again; here it locks
 * within 1 and lets go past 1.1. The locked cursor moved at a speed that
 * ramped from LockedCursorMinSpeed 0.5 to Max 2.5 at 1 a second: a hand's
 * short moves never got past the slow start, so aiming needed 200 % to feel
 * right and still dragged. While aiming it is one speed, the top, at once.
 * The free reticle (no target locked: aiming at the scenery, the reticle
 * moving on the screen) had the same ramp: FreeCursorMinSpeed (0x681BA8, a
 * tuning file's) up to FreeCursorMaxSpeed (0.25) at FreeCursorAccel
 * (sub_00143350, 0x0014396A), and BeginnerModeCursorMinSpeed (0x681BB4) up
 * to its max (0.2) for the beginner targeting style: while aiming the
 * minimum is the maximum, so the reticle answers the hand at once.
 * (Flattening that ramp all the time spoiled every turn out of aiming: the
 * locked cursor drives the camera in a fight too.) The game's values come
 * back on release. */
#define TUNE_RAMP_CROSS_SOFTLOCK 0x00413638u
#define TUNE_DRIFT_ACCEL         0x0041364Cu
#define TUNE_LOCK_BORDER         0x004137A4u   /* two floats, x and y: 1.4 */
#define TUNE_UNLOCK_BORDER       0x004137ACu   /* two floats: 1.8 */
#define TUNE_LOCKED_ACCEL        0x00413658u   /* LockedCursorAccel 1.0 */
#define TUNE_LOCKED_MIN          0x0041365Cu   /* LockedCursorMinSpeed 0.5 */
#define TUNE_LOCKED_MAX          0x00413660u   /* LockedCursorMaxSpeed 2.5 */
#define TUNE_FREE_MIN            0x00681BA8u   /* FreeCursorMinSpeed */
#define TUNE_FREE_MAX            0x00413654u   /* FreeCursorMaxSpeed 0.25 */
#define TUNE_BEGIN_MIN           0x00681BB4u   /* BeginnerModeCursorMinSpeed */
#define TUNE_BEGIN_MAX           0x004136B4u   /* BeginnerModeCursorMaxSpeed 0.2 */
#define N_TUNE 10

static void aim_assist_off(int off)
{
    static const uint32_t addr[N_TUNE] = {
        TUNE_RAMP_CROSS_SOFTLOCK, TUNE_DRIFT_ACCEL,
        TUNE_LOCK_BORDER, TUNE_LOCK_BORDER + 4, TUNE_UNLOCK_BORDER, TUNE_UNLOCK_BORDER + 4,
        TUNE_LOCKED_ACCEL, TUNE_LOCKED_MIN, TUNE_FREE_MIN, TUNE_BEGIN_MIN
    };
    float ours[N_TUNE] = { 1.0f, 0.0f, 1.0f, 1.0f, 1.1f, 1.1f, 1000.0f, 0.0f, 0.0f, 0.0f };
    static float game[N_TUNE];
    static int applied;
    int i;

    ours[7] = MEMF(TUNE_LOCKED_MAX);   /* one speed: the top, at once */
    ours[8] = MEMF(TUNE_FREE_MAX);
    ours[9] = MEMF(TUNE_BEGIN_MAX);
    for (i = 0; i < N_TUNE; i++)
        if (!applied || MEMF(addr[i]) != ours[i])
            game[i] = MEMF(addr[i]);    /* the game's, or a tuning file's */
    if (off) {
        for (i = 0; i < N_TUNE; i++)
            MEMF(addr[i]) = ours[i];
        applied = 1;
    } else if (applied) {
        for (i = 0; i < N_TUNE; i++)
            if (MEMF(addr[i]) == ours[i])
                MEMF(addr[i]) = game[i];
        applied = 0;
    }
}

/* This frame's stick from the mouse, worked out once per frame for every
 * reader. Clamped by length, not per axis: per axis, a fast diagonal came
 * out bent towards the eight stick directions, and the game then shortens
 * the diagonal to length 1, so it turned slower than a straight move. What
 * the clamp cuts off is carried into the next frames (up to 3 full
 * deflections), so the camera still turns as far as the mouse moved. */
/* While aiming (right button) the counts reach the reticle through a short
 * exponential ease (AIM_EASE_S): every count still turns it, a frame or two
 * later at most, but a hand's uneven reports (0, 3, 1, 4 counts a frame)
 * become one motion instead of steps, the way a hand moves rather than a
 * robot. The free camera gets its counts as they come, as before. */
#define AIM_EASE_S 0.03f

static int frame_stick(float *ox, float *oy)
{
    static float sx, sy, rx, ry, ex, ey;
    int dx, dy, fresh;

    frame_counts(&dx, &dy, &fresh);
    if (fresh) {
        float dt = MEMF(GAME_DT), k, vx, vy, m, fx = (float)dx, fy = (float)dy;
        if (fresh == 2)
            rx = ry = ex = ey = 0.0f;  /* after a pause: nothing to carry */
        if (!(dt > 0.0005f && dt < 0.25f))
            dt = 1.0f / 60.0f;
        if (xbox_InputMouseHeld(XBOX_MOUSE_RIGHT)) {
            float a = 1.0f - expf(-dt / AIM_EASE_S);
            ex += fx;
            ey += fy;
            fx = ex * a;
            fy = ey * a;
            ex -= fx;
            ey -= fy;
            if (fabsf(ex) < 0.01f && fabsf(ey) < 0.01f)
                ex = ey = 0.0f;
        } else {
            fx += ex;                  /* what the ease still held */
            fy += ey;
            ex = ey = 0.0f;
        }
        k = look_rad() / (STICK_RAD_PER_SEC * dt);
        vx = fx * k + rx;
        vy = (s_invert_y ? -fy : fy) * k * s_ysens + ry;
        m = sqrtf(vx * vx + vy * vy);
        if (s_cap > 0.0f && m > s_cap) {
            sx = vx * s_cap / m;
            sy = vy * s_cap / m;
            rx = vx - sx;
            ry = vy - sy;
            m = sqrtf(rx * rx + ry * ry);
            if (m > 3.0f * s_cap) {
                rx *= 3.0f * s_cap / m;
                ry *= 3.0f * s_cap / m;
            }
        } else {
            sx = vx;
            sy = vy;
            rx = ry = 0.0f;
        }
    }
    *ox = sx;
    *oy = sy;
    return sx != 0.0f || sy != 0.0f;
}

void sub_001A98C0(void)
{
    uint32_t ret = MEM32(g_esp), stick = MEM32(g_esp + 4), out = MEM32(g_esp + 8);
    uint32_t mask = MEM32(g_esp + 0x10);
    int seen = s_rs_seen;

    float gx, gy;

    if (stick == 1)
        aim_assist_off(s_on && xbox_InputMouseHeld(XBOX_MOUSE_RIGHT));
    if (s_on && stick == 1 && (MEM32(g_ecx + 0x70) & mask) && frame_stick(&gx, &gy)) {
        MEMF(out) = gx;
        MEMF(out + 4) = gy;
        s_ramp = 1;
        if (trace_on())
            trace_hit('M', ret);
        g_esp += 0x14;                 /* ret 0x10 */
        return;
    }
    if (stick == 1)
        s_ramp = 0;
    s_rs_seen = 0;
    sub_001A98C0_pad();
    if (trace_on() && s_rs_seen)
        trace_hit('G', ret);
    s_rs_seen |= seen;
}

/* sub_0014DB20 / sub_0014DBF0 (thiscall, one float, ret 4, result in st0):
 * the look stick's response curve for AimRampX / AimRampY, the turn the
 * cameras use. Below a dead zone ([ecx+8] / [ecx+0x20]) 0, then a log
 * curve up to a saturation point, then a fixed top ([ecx+0x1C] / [ecx+0x34]),
 * times the game's own sensitivity setting (an exp of [ecx] / [ecx+4]); the
 * X curve also flips the sign. A mouse through it lost every small move to
 * the dead zone and every fast one to the top. While the mouse drives the
 * stick the curve is linear instead: the game's own full-deflection output
 * (the curve at +1, sign and sensitivity included) times the value. */
void sub_0014DB20_pad(void);
void sub_0014DBF0_pad(void);

static void ramp_linear(void (*pad)(void))
{
    uint32_t a = g_esp + 4;
    float x = MEMF(a);

    if (!s_ramp) {
        pad();
        return;
    }
    MEMF(a) = 1.0f;                     /* the caller's pushed argument */
    pad();
    g_fp_stack[g_fp_top] *= (double)x;
}

void sub_0014DB20(void) { ramp_linear(sub_0014DB20_pad); }
void sub_0014DBF0(void) { ramp_linear(sub_0014DBF0_pad); }

void sub_00028D20(void)
{
    uint32_t ret = MEM32(g_esp), out = MEM32(g_esp + 4);
    int dx, dy, fresh;
    float rad, gx, gy;

    if (trace_on())
        trace_hit('c', ret);           /* 'm' below: it took mouse counts */
    if (!s_on || (ret != RET_FREE_CAM && ret != RET_PLAYER_CAM)
            || !frame_counts(&dx, &dy, &fresh)) {
        sub_00028D20_pad();
        return;
    }
    if (trace_on())
        trace_hit('m', ret);
    rad = look_rad();
    /* Game space: x right, y as the stick's decoded byte, which the pad
     * code inverts (mouse forward, dy < 0, is stick up). */
    gx = (float)dx * rad;
    gy = (float)(s_invert_y ? -dy : dy) * rad * s_ysens;
    if (ret == RET_FREE_CAM) {
        /* turn = copy * -0.2 per frame; the sign is the stick's, which
         * gx, gy already follow */
        gx /= 0.2f;
        gy /= 0.2f;
        MEMF(g_esi + 0xE4) = gx;
        MEMF(g_esi + 0xE8) = gy;
    } else {
        /* turn = copy * dt * speed */
        float k = MEMF(GAME_DT) * MEMF(MEM32(g_esi + 0x6E4) + 0x1E0);
        if (!(fabsf(k) > 1e-6f)) {
            sub_00028D20_pad();
            return;
        }
        gx /= k;
        gy /= k;
        MEMF(g_esi + 0x738) = gx;
        MEMF(g_esi + 0x73C) = gy;
        gx += MEMF(g_esi + 0x730);
        gy += MEMF(g_esi + 0x734);
    }
    MEMF(out) = gx;
    MEMF(out + 4) = gy;
    g_esp += 8;                          /* ret 4 */
}

/* ---- the F2 menu's mouse rows (host_menu.h) ---- */

static int nearest(const float *v, int n, float x)
{
    int i, best = 0;
    for (i = 1; i < n; i++)
        if (fabsf(v[i] - x) < fabsf(v[best] - x))
            best = i;
    return best;
}

static const char *const k_sens[] = {
    "0.25", "0.5", "0.75", "1", "1.25", "1.5", "1.75", "2", "2.5", "3", "3.5", "4", "5",
    "6", "7", "8", "10", "12", "15", "20", NULL
};
static const float k_sens_v[] = {
    0.25f, 0.5f, 0.75f, 1, 1.25f, 1.5f, 1.75f, 2, 2.5f, 3, 3.5f, 4, 5, 6, 7, 8, 10, 12, 15, 20
};
static int get_sens(void) { return nearest(k_sens_v, 20, s_sens); }
static void set_sens(int i) { s_sens = k_sens_v[i]; }

static const char *const k_pct[] = {
    "25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%", NULL
};
static const float k_pct_v[] = { 0.25f, 0.5f, 0.75f, 1, 1.25f, 1.5f, 2, 3 };
static int get_ysens(void) { return nearest(k_pct_v, 8, s_ysens); }
static void set_ysens(int i) { s_ysens = k_pct_v[i]; }
static int get_aim(void) { return nearest(k_pct_v, 8, s_aim_mult); }
static void set_aim(int i) { s_aim_mult = k_pct_v[i]; }

static const char *const k_onoff[] = { "No", "Sí", NULL };
static int get_inv(void) { return s_invert_y; }
static void set_inv(int i) { s_invert_y = i; }

static const char *const k_mode[] = { "Directo (como Black)", "Stick emulado", NULL };
static int get_mode(void) { return !s_on; }
static void set_mode(int i)
{
    s_on = !i;
    xbox_InputMouseDirect(s_on);
    if (!s_on)
        aim_assist_off(0);
}

static const char *const k_cap[] = { "x1 (como el mando)", "x2", "x4", "x8", "Sin límite", NULL };
static const float k_cap_v[] = { 1, 2, 4, 8, 0 };
static int get_cap(void)
{
    int i;
    for (i = 0; i < 5; i++)
        if (k_cap_v[i] == s_cap)
            return i;
    return s_cap <= 0.0f ? 4 : nearest(k_cap_v, 4, s_cap);
}
static void set_cap(int i) { s_cap = k_cap_v[i]; }

static const xbox_menu_item k_rows[] = {
    { NULL, "Ratón", NULL, NULL, NULL },
    { "mouse_sens2", "Sensibilidad", k_sens, get_sens, set_sens },
    { "mouse_sens_y", "Sensibilidad vertical", k_pct, get_ysens, set_ysens },
    { "mouse_aim", "Sensibilidad al apuntar (clic der.)", k_pct, get_aim, set_aim },
    { "mouse_cap2", "Velocidad máx. de giro", k_cap, get_cap, set_cap },
    { "mouse_invert_y", "Invertir eje Y", k_onoff, get_inv, set_inv },
    { "mouse_mode", "Modo del ratón", k_mode, get_mode, set_mode },
};

static void menu_init(void)
{
    size_t i;
    for (i = 0; i < sizeof k_rows / sizeof k_rows[0]; i++)
        xbox_MenuAdd(&k_rows[i]);
}

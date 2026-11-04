/*
 * The game's own 16:9 without its 720x480 mode.
 *
 * sub_0017E370 fills the D3D present parameters from the video mode table at
 * 0x00413C70 (640x480 4:3, 720x480 16:9, and their progressive twins), picked
 * from XGetVideoFlags. For a widescreen mode it sets the byte at 0x00683568,
 * which the camera's projection (16/9 into 0x0066FD98, sub_00114450) and the
 * HUD's (sub_001E0250) read, and the pixel aspect at 0x00413D18 to
 * height / width * 16/9. The 720x480 mode itself failed D3D's device creation
 * here (the frame buffers were made and freed again, then the boot waited for
 * ever), so the mode stays 640x480 and only those two values are set after
 * the call: the game draws its 16:9 view anamorphic into 640x480, and the
 * D3D11 present shows it 16:9 (xbox_VideoWidescreen, nv2a_pb_d3d11.c).
 *
 * recomp_0027.c's definition is renamed sub_0017E370_pad (tools/rename_pads.py).
 */
#include "recomp/gen/recomp_types.h"

void sub_0017E370_pad(void);
int  xbox_VideoWidescreen(void);

#define WIDE_BYTE    0x00683568u
#define PIXEL_ASPECT 0x00413D18u
#define MODE_W       0x006834FCu   /* the mode's width, float */
#define MODE_H       0x006834DCu   /* its height */

void sub_0017E370(void)
{
    sub_0017E370_pad();
    if (xbox_VideoWidescreen() && MEMF(MODE_W) > 0.0f) {
        MEM8(WIDE_BYTE) = 1;
        MEMF(PIXEL_ASPECT) = MEMF(MODE_H) / MEMF(MODE_W) * (16.0f / 9.0f);
    }
}

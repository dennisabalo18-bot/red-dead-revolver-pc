@echo off
rem Runtime switches Red Dead Revolver needs; shared by run.bat and run_debug.bat.

rem Emulated MCPX audio chip: the title's own DirectSound drives it.
set RECOMP_AC97_READY=1
rem Execute the GPU pushbuffer, and show the framebuffer in a window.
set RECOMP_PB_EXEC=1
set RECOMP_FB_WINDOW=1
rem 60 Hz vblank interrupts: the engine's frame limiter waits on them.
set RECOMP_VBLANK=paced
rem Gamepad: emulated USB host controller, XInput pads, keyboard as pad 1.
set RECOMP_USB=1
set RECOMP_KEYBOARD=1
rem Keep contiguous (DMA) memory above the 8 MB image, or the USB
rem descriptors resolve into the game's code and the pad never enumerates.
set RECOMP_CONTIG_AVOID_IMAGE=1
rem Share even small draws with the raster threads (front end: ~1000 a frame).
set RECOMP_RASTER_MT_MIN=128

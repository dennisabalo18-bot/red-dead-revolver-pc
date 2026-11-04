# Port de Red Dead Revolver (Xbox) a PC — estado del proyecto

Actualizado: 2026-11-02.

**Estado (2026-11-02): versión jugable completa, con texturas mejoradas de menús, escenario y personajes.**

## Reglas de trabajo (las pidió el usuario)

- **No abrir el juego para hacer pruebas automáticas.** Nada de partidas con script, escaneos de memoria ni
  capturas lanzadas por Claude. Solo se compila. Las pruebas las hace el usuario (`run.bat` o `run_debug.bat`)
  y Claude lee después `rdr-apex\runs\last_err.txt`.
- Ahorrar tokens: trabajar de forma estática (desensamblado y código) y pedir al usuario pruebas cortas y concretas.
- Antes de un cambio arriesgado, proponer un intento acotado y un plan B seguro.

## Estructura

| Ruta | Qué es |
|---|---|
| `C:\rdr-port\rdr-apex` | Proyecto del juego con GPU (D3D11). Es el que se usa. |
| `C:\rdr-port\xboxrecomp-apex` | Runtime: fork de apexJCL, rama `rdr-port`, repositorio git propio. |
| `C:\rdr-port\analysis-apex` | Análisis del XBE: `disasm\asm\text.asm` (desensamblado con XREF), `func_id`, etc. |
| `C:\rdr-port\rdr`, `C:\rdr-port\xboxrecomp` | Versión antigua que renderiza por CPU (sin uso). |
| `C:\rdr-port\tools\mlog_draws.py` | Decodifica una captura F10 (`[MLOG]`) en llamadas de dibujado. |
| `C:\rdr-port\patches\xboxrecomp-apex\` | Parches exportados del fork (puede estar desactualizado: el fork tiene commits nuevos). |

- Juego (XBE y datos): `<carpeta del juego>\default.xbe`.
- Repositorio principal en `C:\rdr-port`, rama `gpu-d3d11`.
- Compilación (sin ejecutar el juego):
  `"C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" --build C:\rdr-port\rdr-apex\build --config Release --parallel 8`
- Lanzadores:
  - **`JUGAR.bat` (raíz): el que usa el usuario.** Llama a `rdr-apex\run.bat`. Si dice que "no hay F2 / 4:3",
    probablemente abrió `rdr\` (la versión vieja): mirar `rdr\xbox_kernel.log`.
  - `rdr-apex\run.bat`: juego normal.
  - `rdr-apex\run_debug.bat`: escribe los registros en `runs\last_err.txt` y activa `RDR_MOUSE_TRACE=1`.
- Ajustes del juego en `rdr-apex\env.bat`. Hacer doble clic en él no hace nada visible: solo define variables.

## Qué funciona

- Arranque, sonido, vídeos, menús, New Game, partida completa a 60 FPS con GPU (D3D11).
- Mando XInput, teclado (IJKL = stick derecho) y ratón.
- Gráficos: resolución interna ×2, filtro anisotrópico ×16, escalado lineal (`RDR_RENDER_SCALE`, `RDR_ANISO`, `RDR_FILTER`, `RDR_ASPECT`).
- Teclas:
  - F11 o Alt+Enter: pantalla completa.
  - F10: captura `[MLOG]` del siguiente fotograma. Mientras captura, los FPS bajan mucho; es normal.
  - **Ctrl+F8: velocidad del juego ×2** (antes F8 solo; un F8 que llegaba solo a la ventana arrancaba el juego a x2).
  - F9: libera el cursor.
  - **F6: texturas y letras mejoradas sí/no al instante**, para comparar (lo mismo que la fila de F2; no se guarda).
  - **F2: menú de ajustes** (nuevo, sin probar todavía por el usuario). Ver la sección "Menú F2".

## Ratón tipo Black (último trabajo)

Archivo: `rdr-apex\src\mouselook.c`. Se inicializa con `rdr_mouselook_init()`, llamado desde `main.c` después de `rdr_mouse_init()`.

Lo que se averiguó en el desensamblado:

- `sub_003C88B4` = XInputGetState. Lo llama `sub_00047F10`, que convierte los sticks a un byte (0..255) por mando.
  - El mando i está en `0x40E640 + 0x38*i`; RX en +0x2A, RY en +0x2B (invertido).
- `sub_00027980` / `sub_000279D0` / `sub_00027A20` / `sub_00027A70` devuelven RX / RY / LX / LY como float
  `(byte - 127.5) / 127.5`.
- `sub_001A8DD0(eje)` es la capa de controles configurables: la tabla `0x4164D0` asigna el eje 0..3 a LX, LY, RX, RY.
  - Esa tabla también contiene una zona muerta de 0.3 y una saturación de 0.9.
- **`sub_001A98C0(stick, out, modo, máscara)`** (thiscall, `ret 0x10`): lee un stick (0 izquierdo, 1 derecho),
  le aplica zona muerta y curva, y escribe dos floats en `out`.
  - La "entrada del jugador" de cada fotograma lo llama: `sub_0013FCF0` (ret `0x13FDF7`) y otras cinco funciones
    parecidas (ret `0x149045`, `0x143485`, `0x14B238`, `0x14B015`, `0x14AB95`), además de `0x1AA694`.
  - Después, el valor pasa a un sistema de parámetros del juego (llamadas virtuales `push id`); no se siguió más.
- `sub_00028D20`: lectura del stick derecho con zona muerta de 0.4. Solo la usan dos cámaras especiales:
  - `sub_00045710` (cámara libre; solo se activa con un botón).
  - `sub_00040E90`.
  - Las dos suavizan el valor con `sub_00020770` (aproximar a velocidad·dt).
- No son la cámara: `sub_001A9EF0` (navegación de menús en 8 direcciones), `sub_00064DC0` (inactividad),
  `sub_00048410` (stick como botones), `sub_001A85D0` (copia de la entrada).
- El dt del fotograma del juego está en `0x004109A4`.

Implementación actual:

- `sub_001A98C0` y `sub_001A8DD0` envuelven a las originales, que se renombraron `_pad` editando
  **`src\recomp\gen\recomp_0031.c`** (solo las definiciones).
  - **Ese archivo generado no está en git.** Si se vuelve a generar el código, hay que repetir el renombrado.
- `sub_00028D20`: la original se renombra `sub_00028D20_pad` con una definición de compilación en `CMakeLists.txt`
  aplicada a `recomp_0002.c`.
- Con movimiento del ratón y stick = 1, devuelve el ratón directamente, sin zona muerta ni curva:
  - valor = cuentas × 0.06° × `RDR_MOUSE_SENS` / (0.1 rad × 60 × dt);
  - con `RDR_MOUSE_AIM_MULT` mientras se mantiene el clic derecho;
  - recorte por longitud, y el exceso pasa a los fotogramas siguientes (hasta 3).
- Todas las lecturas de un mismo fotograma reciben el mismo valor (`frame_counts`: nueva toma si pasaron más de 4 ms;
  si pasaron más de 150 ms, se descarta lo acumulado).
- En el runtime, `mouse.c` tiene `xbox_InputMouseDirect()` y `xbox_InputMouseTakeLook()`.
  - En modo directo, el stick emulado no recibe el ratón.
- `env.bat`: `RDR_MOUSE_LOOK=direct` (`stick` vuelve al modo anterior), `RDR_MOUSE_SENS=2.0`, `RDR_MOUSE_AIM_MULT=1.75`,
  `RDR_MOUSE_INVERT_Y=0`.
- Estado:
  - Primera versión (enganche solo en `sub_00028D20`): la cámara no se movía.
  - Con `sub_001A98C0`: la cámara se mueve, pero "tosco, 4 direcciones, diagonal lenta".
  - Se corrigió el recorte por ejes (commit `a06bf3e`). **El usuario todavía no lo ha probado.**
- Si sigue tosco:
  - Probablemente el juego aplica más adelante otra zona muerta o un suavizado.
  - Opción: compensar la zona muerta. Opción más cara: encontrar la variable del ángulo de cámara siguiendo el valor
    desde `0x13FDF7` por el sistema de parámetros, y escribir los grados directamente (el método de Black).
  - El techo actual es la velocidad máxima de giro del stick.

## Hallazgos clave (2026-11-01, segunda ronda) — LEER PRIMERO
- **Humo y mira a media escala (resuelto en el backend):** el juego los dibuja en el back buffer 640x480 con SET_SURFACE_FORMAT 0x2128 (antialiasing SQUARE_OFFSET_4) y recorte/viewport lógicos de 320x240 (la XDK, sub_00339540, divide el tamaño entre 2 en modo multisample). El hardware y xemu multiplican recorte, borrado y posiciones ×2; el backend D3D11 lo ignoraba. Ahora `nv2a_aa_x/y` (nv2a_backend_common.h) y `aa_box` / `set_vp` (nv2a_pb_d3d11.c) lo aplican.

**Cámara de RDR (estático, verificado en el desensamblado):**
- La cámara es una "CamMach" guiada por archivos `.ccm`. Su tabla de entradas se registra en `sub_001D46A0`
  (id → nombre): 0xC LookstickX, 0xD LookstickY, 0xE AimRampX, 0xF AimRampY, 0x14 CameraBearing,
  0x15 CameraTilt, 0x2E AimHorizSensitivity, 0x43 AimVertSensitivity (lista completa: 92 entradas).
- `sub_0013FCF0` (entrada del jugador) las rellena: LookstickX = stick X tal cual (de `sub_001A98C0`);
  LookstickY = stick Y (×−1 si invertido); **AimRampX = `sub_0014DB20`(X), AimRampY = `sub_0014DBF0`(Y)**.
- `sub_0014DB20/DBF0` = curva del stick: zona muerta `[ecx+8]`/`[ecx+0x20]`, curva log hasta la saturación,
  tope `[ecx+0x1C]`/`[ecx+0x34]`, × exp(sensibilidad del juego). **Esto hacía horrible el ratón.**
- Acciones de cámara (nombre → función de fábrica → actualización): `p_lookleftright` 0x2A3A90 → 0x29FBB0,
  `h_fpslook` 0x2A36D0 → 0x29FA90, `h_fpslookupdown` → 0x29FB40, `H_LookUpDown` → 0x2A6FE0. Integran
  ángulo −= dt × `[0x419FA8]` (factor de tiempo, tiempo bala) × valor. Lineal, sin suavizado.
- Ratón ahora (como BLACK, que engancha la integración del ángulo): stick lineal sin recorte
  (`STICK_RAD_PER_SEC` 2.0) y `sub_0014DB20/DBF0` envueltas: con ratón devuelven curva(+1) × valor
  (lineal, sin zona muerta ni tope, con signo y sensibilidad del juego).
- Referencia BLACK: github.com/Spark198rus/black-pc `loader/src/input/mouselook.cpp`.

**16:9 nativo:**
- RDR tiene modos 640×480 4:3 y **720×480 16:9** (tabla `0x413C70`, elegida al arrancar en `sub_0017E520`/
  `sub_0017E370` según `sub_001922EA` = XGetVideoFlags = (XC_VIDEO >> 16) & 0x5F). Con panorámico, el byte
  `[0x683568]` = 1 y el juego usa 16/9 en la proyección (`[0x66FD98]`) y el HUD (`sub_001E0250`).
- El kernel devolvía `0x03` (defines mal: 0x01/0x02) → tras >>16 = 0 → el juego nunca veía panorámico.
  Arreglado en `kernel.h` (valores EEPROM reales) + `xbox_VideoWidescreen()` (`RECOMP_WIDESCREEN`, F2).
- Presentación: un fotograma 720×480 con panorámico se muestra a 16:9 (`wide_frame`, `present_blit`).
- **El modo 720×480 colgaba el arranque** (la XDK crea y libera los búferes y el juego espera para siempre).
  Ahora XC_VIDEO sigue en 4:3 y `rdr-apex/src/widescreen.c` envuelve `sub_0017E370`: tras configurar el modo
  640×480 pone `[0x683568]=1` y `[0x413D18]=alto/ancho×16/9`; el present estira el 640×480 a 16:9.
- Se aplica **al reiniciar** (el juego elige modo una vez, `sub_00051A30`). El hor+ (`NV2A_OPT_ASPECT`) no
  hacía nada visible y salió del menú.

**Brillo/costura v3:** se salta cualquier copia reducida pegada sobre un destino mayor (la escena se dibuja en
un 640×480 aparte, `0x0198AC00`, no en el fotograma; la v2 exigía el mismo destino y nunca saltaba).

**`tools/rename_pads.py`:** renombra a `_pad` las definiciones envueltas (`recomp_0031.c`, `recomp_0023.c`).
Ejecutarlo después de regenerar el código.

## Pausa, FPS, VSync y teclas de PC (2026-11-01, sin probar)

- Pausa al cambiar de ventana: `WM_ACTIVATEAPP` → el flip (`d3d11_flip`) llama `xbox_PauseSet(1)` y espera
  bombeando la ventana. `kernel_pacing.c`: velocidad 0 = relojes quietos, sin vblanks; `apu_core.c` no hace
  cuadros mientras `xbox_Paused()`. F2 "Pausa al cambiar de ventana", `RECOMP_PAUSE_UNFOCUSED=0` la apaga.
- F2 "Mostrar FPS": recuadro arriba a la izquierda (`fps_pixels` en `host_menu.c`, misma textura que el menú).
- F2 "VSync": `nv2a_d3d11_vsync` (intervalo de Present 1/0).
- Teclas (`main.c`): R/V = Y (recargar: "Press ¼ to reload"), E = X (acción: tiendas, tren), C/X = B,
  F/rueda abajo = Black, Esc = START, Tab = BACK; siguen WASD, Espacio = A, Q = White, clic izq./der. = gatillos.
- Iconos de botones (verificado en la fuente): U+BA º = A, U+BC ¼ = Y, U+BD ½ = X, U+BE ¾ = B,
  U+2020 † = gatillo izq., U+2021 ‡ = gatillo der. Fuente = tabla de glifos (float 1.02, cuenta en 0x2C,
  registros de 10 bytes: u32 carácter, x, y, w, h, s16) + páginas P8 128x128 lineales (sin swizzle) justo
  después (`front.dat` #5 → #6..#10). Está copiada en cada nivel y en swat.dat (6 fuentes con botones).
- `tools/botones_teclado.py` (+ `modding/botones_teclado.bat`, "quitar" lo deshace): dibuja Espacio/R/E/C y
  el ratón en esas celdas (colores en ranuras libres de la paleta) y reconstruye 65 archivos en
  `modding/mods/` (alineado 0x20, deflate crudo). Verificado: solo cambian 141 páginas. Sin probar en el juego.

## Cinemáticas en MP4 (2026-11-01, sin probar en el juego)

- Videos: Bink 1 ("BIKi") 720x480 en `bik\` (30 fps) y `bik50\` (PAL 25 fps, mismos nombres).
  `modding/extraer_videos.bat` los saca con ffmpeg a `modding/mods/videos/<nombre>.mp4`.
- Mejorados con SeedVR2 (2026-11-02): `tools/videos_seedvr2.py` (de a uno desde la ventana de abajo), ComfyUI abierto
  en :8188. Frames con ffmpeg, nodo de video SeedVR2 (3B fp8, 960 lado corto = x2, lotes de 21, VAE en
  mosaicos de 512: pico 10.4 GB; 768 llena los 12 GB y tarda 6x más; sin mosaicos 18 min un lote) en tandas de 84 + 4 de contexto,
  MP4 CRF 14 con el audio del .bik. Reanudable. ~2.3 s/frame en la RTX 5070: 22788 frames (23 videos) = ~14 h.
  PreviewImage llena la carpeta temp de ComfyUI hasta reiniciarlo.
- Ventana `modding/Mejorar videos.bat` -> `tools/videos_app.py` (tkinter): los 23 videos de bik\ con duración,
  tiempo estimado (frames x `videos_mejorados/velocidad.txt`, la última velocidad medida), tick verde si existe
  `modding/videos_mejorados/<nombre>.mp4`; botón Reescalar (cola de a uno), Detener (reanudable), Rehacer.
  El terminado queda SOLO en videos_mejorados (decisión del usuario): `mods/videos` (lo que lee el juego,
  copias 720x480 de extraer_videos.bat) no se toca; para jugarlos hay que copiarlos a mano.
- 2026-11-03: los 23 terminados y verificados (decodifican enteros, mismos frames, duración y audio que el
  .bik; diferencia media con el original 2-9/255). royfi01 sale 1280x960 (su .bik es 640x480).
  Copiados a `mods/videos` (2026-11-03, pedido del usuario): el juego ya los usa. Para volver a los
  720x480: borrar mods/videos y correr extraer_videos.bat.
- 60 fps (prueba, 2026-11-03): `tools/videos_60fps.py <nombre> [--poner]`: RIFE v4.26 (Comfy-Org, en
  models/frame_interpolation, corre con el Python de ComfyUI sin abrirlo) entre cada par de frames, repite el
  anterior en cortes de escena, deband de ffmpeg, mismo audio -> `modding/videos_60fps`; el de 30 fps se copia
  a `modding/videos_30fps`. El reproductor (movie_mf + Present con vsync) no limita fps. Hecho: titles (puesto
  en mods/videos; el usuario lo vio: se ve muy bien). Volver: copiar videos_30fps/titles.mp4 a mods/videos.
- Ventana `modding/Videos 60 fps.bat` -> `tools/videos_app.py --60`: misma ventana que la de SeedVR2 (clase Job),
  fuente = videos_mejorados, tick = videos_60fps/<nombre>.mp4, ~0.31 s por frame de 30 fps
  (`videos_60fps/velocidad.txt`). Detener mata RIFE y descarta ese video. No toca el juego salvo con los botones
  'Poner los 60 fps en el juego' / 'Volver a 30 fps'.
- Videos y overlays (2026-11-03): `movie_run` presenta con `movie_show` (frame + ovl_present + menu_present):
  el recuadro de FPS y F2 se ven sobre la película; con F2 abierto la película se pausa y sus teclas (Esc,
  Enter, Espacio) no la saltan. Teclas de volumen/medios (VK_VOLUME_MUTE..VK_LAUNCH_APP2) van a DefWindowProc
  (antes el WndProc devolvía 0: sin WM_APPCOMMAND no salía el cuadro de volumen). Compila; sin probar.
- `sub_00071080(nombres, cuenta, ...)` arranca el reproductor Bink (rutas por `sub_00070FB0`, "%sbik\%s.bik");
  devuelve 0 si no pudo (los llamadores siguen como al terminar la película). `rdr-apex/src/movies.c` lo
  envuelve (`_pad` por `tools/rename_pads.py`): si TODOS los nombres tienen MP4 en `RECOMP_MODS_DIR\videos`,
  `nv2a_d3d11_movie` los reproduce y devuelve 0 tras el mismo preparado que un archivo ausente.
- Runtime (`movie_mf.c` + `nv2a_pb_d3d11.c`): IMFMediaEngine con el dispositivo D3D11 (creado con
  VIDEO_SUPPORT; sin él no hay reemplazo). El hilo del juego espera; el hilo ack (dueño del dispositivo) lo
  reproduce en `d3d11_on_poll` con el invitado en pausa. 3:2 se muestra 4:3; otra forma, la suya. Salto:
  Esc, Enter, Espacio, clic izq., A/B/START. Si el MP4 no abre, juega el Bink. Log: `[MOVIE]`.
- Para desactivarlo: quitar/renombrar `modding/mods/videos`.

## Texturas mejoradas y letras (2026-11-01..02)

- **Estado final (2026-11-02):** Upscayl escaló 1890 texturas más (0 fallos) y `textures.pack` tiene 3650
  entradas (10.8 GB, validado). Incluye por primera vez el escenario de los niveles y los personajes. El
  usuario lo probó: "una versión increíble para jugar". F6 lo apaga y prende en vivo
  (`nv2a_tex_pack_kind_enabled` + `wnd_proc` en `nv2a_pb_d3d11.c`; la fila de F2 lee el mismo estado).

- **El pack nunca se cargó hasta ahora.** `rdr-apex/build` está configurado con `XBOXRECOMP_ENHANCE=OFF`, y
  el único que leía `RECOMP_TEXTURES_PACK` era esa capa. En `last_err.txt` no aparecía ninguna línea
  `textures.pack`. Arreglo: `host_enhance_init()` (`rdr-apex/src/main.c`), sin la capa, llama
  `nv2a_tex_pack_load(getenv("RECOMP_TEXTURES_PACK"))`. Log: `[rdr] textures.pack ...: N entries (M font)`.
  Se apaga vaciando la línea en `env.bat`. No se encendió la capa entera para no chocar con el menú F2.
- Texturas: `modding/escalar_texturas.bat` (Upscayl por CLI, una imagen por proceso, mosaicos chicos; el
  modelo `digital-art-4x` va en `mejoradas/upscayl_png_digital-art-4x_4x/`). 1827 de 1832 escaladas.
  `crear_pack_texturas.bat` arma `textures.pack` v2 (unos 7.8 GB, 10–20 min). La transparencia se toma del
  dump (`texturas/dump/`, que ya no existe: para rehacer el pack completo hay que volver a extraer).
- Letras: el port no vuelca las páginas P8 de las fuentes. `tools/letras.py` las saca de los archivos del juego
  (65 páginas; `modding/mods` si existe la copia reconstruida), a 4x con borde nítido, y dibuja los íconos de
  teclado a 4x en las celdas de botones (la tienda usa `front.dat` #34, página #39, que `botones_teclado.py`
  no tocaba). Claves: hash de los índices (en orden del archivo y en Z-order) con la paleta de 256/128/64/32
  entradas, 8 por página. Van como tipo "font" (kind 1). `python tools/texturas_pack.py letras` las agrega
  al pack existente en segundos (índice nuevo al final; el viejo queda como espacio muerto).
- Partida del 2026-11-01 22:35 (registro `[TEXPACK] hit`): el pack se usó en 62 entradas (56 dibujos, 6 páginas
  de letras: `front.dat` #6..#10 y #185, o sea la letra principal sí entra). Los 76 fallos son casi todos P8
  (`fmt0B`) de 128x128 y 256x256: texturas de modelos (dentro de las entradas RSC0), que ni el volcado ni
  `extraer_texturas.py` sacan. Por eso el mundo "se ve igual": lo que escaló Upscayl son sobre todo menús,
  carteles y efectos (DXT). Buscar la cabecera 14-byte de P8 dentro de RSC0 no encontró ninguna: los modelos
  guardan sus texturas con otro formato. **Formato RSC0 resuelto:** chunks (tag, fin) desde 0x0C, el primero en
  0x80; MIP0 = u32 cuenta + u32 offset a descriptores D3D de 20 bytes (data relativo al chunk, palabra de
  formato con tamaño y niveles), texeles YA en Z-order; PAL0 = una paleta por modelo en +0x40. Clave = la misma
  fórmula (confirmado con una textura de `swat.dat` en el registro). `extraer_texturas.py` las saca: 253 nuevas
  (159 de 256x256: ropa, caras, pelo de personajes). Faltan por escalar con `escalar_texturas.bat` y rehacer
  el pack. **Escenario encontrado:** cada nivel tiene una entrada RSC0 grande (cientos de chunks: PMT0, BND0 y
  grupos MIP0/PAL0/TEX0/MOD0); la cabecera mide u32@8 (0x80 en los modelos chicos, 0xB00 en el escenario) y
  cada MIP0 usa el PAL0 que lo sigue. Extraídas 1367 más (roca, arena, baldosas, papel tapiz...). Dump: 3777
  PNG; unas 1950 sin escalar.
- `extraer_texturas.py` ahora también saca las P8 sueltas (fmt 0x0E): clave = hash de los niveles en Z-order
  con la paleta de 256 entradas (confirmado: así entran las páginas de letras). Dump rehecho: 2210 PNG, 383 sin
  escalar (casi todas páginas de letras de 128x128).
- "La animación de carga se ve oscura" desde que carga el pack: sin causa encontrada. Upscayl no oscureció los
  colores (las medidas que lo sugerían premultiplicaban por alfa). F2 tiene ahora "Texturas mejoradas"
  (Sí/No, `pack_art` en `rdr_menu.ini`, `nv2a_tex_pack_set_kind_enabled`) para ver
  en el juego cuál la causa. `texturas_pack.py` (al rehacer el pack) toma el color original donde la textura es
  transparente (`restore`) y busca las originales en los archivos del juego.
- Prueba del usuario: con "Texturas mejoradas" en No la pantalla de carga (Red al atardecer) se ve normal; con
  Sí aparece un marco ovalado de papel/lienzo marrón que la oscurece. No se encontró qué entrada del pack lo
  dibuja: los colores y el alfa de todas las de `front.dat` coinciden con las originales, y todos los aciertos
  vienen de los archivos del juego. **Resuelto:** `[TEXPACK] on screen` (3 s después de encender el pack en
  F2) dio `37385E870F750893` = `front.dat` #49, una viñeta borrosa de 32x32 que Upscayl convirtió en un óvalo
  duro con trama de lienzo. Las texturas de 32x32 o menos quedan fuera del pack (`SMALL` en
  `texturas_pack.py`; `texturas_pack.py sin_chicas` las quitó del pack actual: 67).
- Letras del pack: el usuario las vio peor que las originales. Quitadas del pack (`texturas_pack.py sin_letras`)
  y de F2; un pack completo ya no las incluye (`texturas_pack.py letras` las agrega si se quieren otra vez).
- Velocidad: F2 "Velocidad" x1/x2/x4; Ctrl+F8 pasa x1 -> x2 -> x4 -> x1.
- Sin cubrir: fuentes con páginas de 16 colores (formato 16, 8270 bytes) y la "B" de la tienda (entrada rara
  de 225 bytes). Si las letras siguen iguales con el pack cargado: `env.bat` ya trae `RECOMP_TRACE=title,tex_pack`:
  mirar las líneas `[TEXPACK] miss ... P8` de `rdr-apex/runs/last_err.txt` para ver la clave real.

## Letras vectoriales y teclas en todas las fuentes (2026-11-02, sin probar en el juego)

- `tools/letras_vector.py`: las fuentes "normales" se redibujan desde una TrueType de Windows a 4x, cada
  letra estirada a la caja de tinta de la original en su celda (la tabla de glifos no cambia). `FONTS`:
  `front.dat` #5 serif -> `pala.ttf` (textos legales, menús), #184 -> `arialbd.ttf` ("Presionar START",
  "Cargando"), #29 máquina de escribir -> `courbd.ttf`. La #34 (tienda) se probó con Impact: pierde el estilo
  desgastado, queda fuera. Las fuentes western decorativas no tienen equivalente. Vistas previas en
  `modding/texturas/letras_vector/comparar_*.png`. `texturas_pack.py letras_vector` las agrega al pack
  (104 claves, tipo font, 512x512) en segundos. F6 y F2 apagan arte y letras juntos.
- Botones: `fuentes_botones.fonts()` solo aceptaba fuentes con TODAS las páginas P8 128x128; quedaban fuera 6
  (la de la tienda #34, cuya B está en una página rara). Ahora basta con que una página con botones sea P8 o
  P4 (16 colores, 8270 bytes: paleta de 64 bytes, nibble bajo primero), y `botones_teclado.repaint4` pinta
  las P4 (colores libres de la paleta, o el más cercano). Repintadas: tienda A/Y/X (`front.dat` #39), máquina
  de escribir (#31), `swat.dat` #7830, #15472, #15488, #15489. Sin cubrir: la B de la tienda (#40, 225
  bytes) y LT/RT de la #34 (#43, 947 bytes): no son páginas de textura (empiezan con texto).
- **Tienda (resuelto con un volcado del usuario):** sus botones A/Y/X/B son imágenes sueltas de 32x32 DXT
  (`562B8D102E7C0525` A, `2F64743FD0FFABF7` Y, `945255403598B301`/`96886387F3E236AB` X, `40669087AF0A4BAD` B;
  también hay íconos de PlayStation sin usar), no glifos: el pack dejaba fuera todo lo de 32x32. El papel y las
  armas de la tienda nunca se habían extraído (por eso F6 no cambiaba nada ahí). `texturas_pack.py agregar`
  suma al pack, sin rehacerlo, lo escalado que le falta y `BUTTON_IMAGES` como teclas 128x128. Para otra
  pantalla igual: F6 apagado, F2 "Volcar texturas", recorrer la pantalla, `escalar_texturas.py`, `agregar`.
  Las letras de "Terminar" de la tienda siguen sin identificar.
- **2026-11-02 tarde:** "HUD alineado a píxel" (snap_2d) muestreaba todo lo 2D en bloques de 1 píxel de
  640x480: por eso las letras vectoriales seguían escalonadas. El usuario lo apagó en F2.
- "Brillo a pantalla completa" quitado de F2 a pedido del usuario. Prenderlo de nuevo desenfocó toda la imagen
  (texto y fondo): `env.bat` lo deja apagado (`RECOMP_D3D11_SKIP_RT=1`). La línea punteada de los bordes no era
  el brillo: a escala n, un borde 2D en x.5 (las franjas negras de cine) dejaba sin cubrir la primera fila de
  píxeles del bloque. `set_vp` corre la imagen (n-1)/2 píxeles del host. **Probado por el usuario (2026-11-02):
  letras nítidas, sin desenfoque y sin la línea de los bordes.**
- Ese corrimiento de toda la imagen dejaba sin pintar una columna y una fila a la derecha y abajo de lo que
  llena su superficie de borde a borde: el borde raro del libro del menú a x2/x3/x4. Ahora los shaders corren
  solo los vértices en medio píxel (`frac == 0.5`, cantidad en `vp_off.w` = `c[7]`); los de píxel entero quedan
  donde estaban (sin probar en el juego). Lo mismo pasaba con cualquier capa a pantalla completa (fundidos).
- Ese corrimiento por vértice, en 3D, hacía aparecer líneas finas que parpadean desde los personajes hacia el
  piso (sombras): dos vértices a 1/16 de píxel, uno corrido y el otro no, abrían triángulos que antes no cubrían
  ningún píxel. Ahora solo se aplica a los dibujos 2D (`two_d` de `set_vp`). Sin probar.
- Upscayl alisa el ruido fino (grava del vagón del tren, arena, tierra). `tools/texturas_detalle.py` compara el
  detalle (laplaciano) de cada escalada vuelta a su tamaño con el de la original y lista en
  `texturas/borrosas.txt` las que quedan por debajo del 55 % (494). `texturas_pack.py sin_borrosas` las sacó del
  pack (3291 entradas); el armado completo y `agregar` ya las saltan.
- Revólver "Seis-disparos" de la armería (`3392172B6626B0F7`, 256x128, dibujo a lápiz): digital-art lo dejaba
  manchado con halos claros. Reemplazado en el pack por UltraSharp (`ultrasharp-4x`, conserva el rayado; la de
  digital-art quedó como `.digital-art.bak`) y sacado de `borrosas.txt`. Para otra textura de dibujo con el mismo
  problema: probar `ultrasharp-4x` en vez de `digital-art-4x`.
- Teclado muerto tras dejar el juego 20 min (pantalla apagada): el registro muestra pausa y reanudación por foco
  y el juego siguió dibujando ~5 s hasta que se cerró; causa sin encontrar. `env.bat` traza ahora las teclas
  (`RECOMP_TRACE=...,key`) para la próxima vez. El usuario lo da por resuelto (no volvió a pasar); si vuelve,
  mirar las líneas `[KEY]` del registro.
- Pendiente: el diario de fin de nivel (volcar sus texturas como se hizo con la tienda).
- Más de 60 FPS: el juego avanza un paso por cuadro (x2 de velocidad lo demuestra), así que más FPS =
  más rápido. Opción práctica: generación de cuadros externa (AMD AFMF, NVIDIA Smooth Motion, Lossless Scaling).

## Ronda 2026-11-02 noche: dibujos, letras, superficies, antialiasing

- **Volcado:** apagado en F2 (`tex_dump=No`). Las 31 imágenes del 2026-11-02 14-15 h son texturas reales de
  menús y tienda (retrato del sheriff, revólveres cruzados, candado, marcos), no basura: no se borran porque el
  pack toma de `texturas/dump/` la transparencia de cada original. Hay 69 sin escalar (31 nuevas + 38 viejas).
- **Dibujos con halos (punto 2):** `tools/texturas_halos.py` mide en cada escalada de digital-art la parte de
  texeles claramente más claros que el original a su alrededor (revólver: digital-art 6,6 %, ultrasharp 3 %) y
  lista en `texturas/halos.txt` las de 4 % o más (147). `tools/texturas_ultrasharp.py` las escala con
  `ultrasharp-4x` (a `texturas/ultrasharp/`), se queda con la de UltraSharp si el halo baja al 60 % o menos y el
  detalle sigue en 55 % o más, deja la de digital-art como `.digital-art.bak` y anota en `texturas/ultrasharp.txt`.
  **Resultado:** 111 de 147 pasaron a UltraSharp (revisadas a ojo: rejas, escopetas, hiedra y molduras quedan
  sin halos; en la hiedra digital-art inventaba un resplandor amarillo). `texturas_pack.py reemplazar` reescribió
  103 entradas del pack (las otras 8 son de 32x32, fuera del pack).
- **Las 69 sin escalar:** `escalar_texturas.py ultrasharp-4x` (a `mejoradas/upscayl_png_ultrasharp-4x_4x/`) y
  `agregar`: 29 texturas nuevas en el pack (el resto son páginas de letras o de 32x32 o menos). Pack: 3320
  entradas, índice validado. Para lo próximo que se vuelque, usar `ultrasharp-4x`.
- **"Terminar" / "Comprar esto" (punto 3):** son la serif `front.dat` #5; en la partida de las 15:16 sus 5 páginas
  son `[TEXPACK] hit`: ya usan la letra vectorial. Las fuentes de swat.dat que faltan en el pack no aparecen en
  ningún registro (no se usaron en lo jugado).
- **Superficies internas (punto 6):** todos los destinos de dibujo se crean a escala (`nv2a_host_size`, máx.
  16384) y nada se lee de vuelta a tamaño Xbox: no hay nada que agrandar.
- **Antialiasing (punto 7, sin probar):** `s_blit_ps` (presentación) promedia 4x4 muestras filtradas sobre la
  huella de cada píxel de pantalla cuando el cuadro es más grande que su lugar (x3/x4 en 1080p): supersampling.
  1:1 o agrandado, una muestra como antes. Para notarlo: escala x4.

## F2 simplificado (2026-11-02)

- El usuario confirmó: las líneas de las sombras en 3D desaparecieron (corrimiento solo en 2D).
- Quitadas de F2: "Filtro de escalado" (fijo en nítido, `NV2A_PRESENT_NEAREST` en `rdr_graphics_init`;
  `RDR_FILTER` ya no se lee), "HUD alineado a píxel" (fijo en No, `snap_2d = 0`) y "Pausa al cambiar de
  ventana" (fija en Sí, `nv2a_d3d11_pause_focus`). Sus líneas salieron de `rdr_menu.ini`.
- Revólver de la armería: la partida de las 15:51 dibujó `3392172B6626B0F7` del pack de las 15:42 (UltraSharp).
  Cambia poco porque el original es un dibujo de 256x128.
- Letras escalonadas en "Cargando partida" y "Presionar START" (serif vectorial): el juego muestrea sus
  páginas de letras en modo punto; a 1x es el texel justo, pero una página 4x achicada en pantalla salía con
  bordes en escalera. Se probó filtrar toda textura del pack: **no cambió nada** y se deshizo (el usuario no
  quiere tocar las texturas que ya estaban bien).
- Causa real (deducida): en la partida de las 16:01 no hubo ni un acierto de letras (a las 15:16, las 5 páginas
  de la serif). Esos textos se desvanecen o titilan; el juego lo hace cambiando la paleta, y la clave P8 incluye
  la paleta (`tex_hash_pal`), así que el pack no las encontraba y salía la página original de 1x. Los fallos de
  letras no se veían porque `nv2a_tex_pack_print_misses` solo muestra texturas "candidate" (swizzle/DXT).
- Arreglo: `texturas_pack.py letras_indices` agrega a cada página de letras una clave con solo sus índices (26).
  `tex_upload`: si un P8 falla, prueba esa clave; si es una página de letras, la usa teñida con la paleta actual
  (`font_retint`: la entrada más opaca de la paleta contra el texel más opaco de la página). Las texturas que ya
  acertaban no cambian. Registro: `[TEXPACK] font page by its indices` (16 como máximo). Sin probar.

## Subtítulos (2026-11-02, sin probar en el juego)

- No salían en las cinemáticas ni en el juego. El juego los muestra solo con el bit 1 (valor 2) de su palabra de
  opciones, `MEM32(0x664260) + 0x5C` (la fila "Subtitles" de sus opciones: `sub_00030390`/`sub_00030690`).
  Al arrancar lo prende si el idioma no es "en" (`0x17C73`), pero el perfil guardado lo vuelve a poner como
  estaba: una partida guardada en inglés lo deja apagado.
- Los de las películas Bink se cargan como `<película>_subtitles` (`sub_00072560` → `sub_00072300`; el
  parámetro "nosubtitles" los apaga) y se dibujan en `sub_00072110` con la fuente "berrylium".
- Arreglo: `movies.c` envuelve `sub_00072110` (renombrado `_pad` por `tools/rename_pads.py`) y prende el bit
  antes de que el juego lo mire. F2 > "Subtítulos siempre" (Sí por defecto; con No manda la opción del juego).
- Si siguen sin salir en alguna escena: esa escena usa otro camino; buscar quién lee `+0x5C` con `>> 1`.

## Menú F2 (2026-11-01, sin probar)

- Runtime: `xboxrecomp-apex/src/d3d/host_menu.c/.h`. Panel dibujado con GDI en una DIB, subido a una textura y
  mezclado sobre el back buffer en `menu_present()` (`nv2a_pb_d3d11.c`, justo antes de `Present`).
- Teclas: F2/Esc cierran; flechas arriba/abajo eligen; izquierda/derecha/Enter cambian; rueda y clics también.
  Con el menú abierto el juego no recibe teclas ni botones (`xbox_InputKeysClear`, `xbox_InputMouseSuspend`).
  F8, F10 y F11 siguen funcionando.
- Filas del runtime: resolución interna x1..x4, aspecto 4:3/16:9/16:10/21:9, tamaño de ventana (lista),
  pantalla completa, filtro, anisotrópico, HUD alineado a píxel, brillo a pantalla completa, velocidad.
- Filas del juego (`mouselook.c`, `xbox_MenuAdd`): sensibilidad 0.25..20, sensibilidad vertical, sensibilidad
  al apuntar, velocidad máx. de giro (`RDR_MOUSE_CAP`), invertir Y, modo del ratón.
- Se guarda solo en `rdr-apex/rdr_menu.ini` (lo carga `main.c` con `xbox_MenuLoad` después de
  `rdr_graphics_init`). Gana sobre `env.bat`; borrarlo vuelve a `env.bat`.
- Aspecto en vivo: nuevo `NV2A_OPT_ASPECT` en `nv2a_backend_common.c/h`; al cambiar, `scale_drop()` suelta los
  destinos como con la escala.
- Tamaño de ventana: `nv2a_d3d11_window_request()` + `window_apply()` en `d3d11_on_flip`. En pantalla completa
  espera a que se vuelva a ventana.

## Ratón: techo de velocidad

- En `sub_0013FCF0` el stick derecho pasa a los parámetros del juego (`push 0xC`) sin recortar; solo el
  izquierdo se recorta a longitud 1. Por eso el recorte a 1 de `frame_stick` era el techo que hacía sentir
  "sensibilidad baja". Ahora el límite es `s_cap` (por defecto 4, `RDR_MOUSE_CAP`, 0 = sin límite).
- `RDR_MOUSE_SENS` por defecto 4 (antes 2), rango hasta 20.

## Traducción

- Revisado: las únicas instrucciones sin traducir que se ejecutan son `wbinvd`, `cli`, `sti` (no-ops correctos).
  El resto de `RECOMP_UNIMPL` son datos decodificados como código (pshufb mm, aam, insb...). Los 6 stubs no
  resueltos no se alcanzan. Kernel: 149/149 resueltos. Los 3 archivos que faltan (`stream5.dat`,
  `lvls_sng\waterfal.dat`, `lvls_m2\lvl_colseum2.dat`) son sondeos del juego, no existen en el disco original.

## Errores pendientes

1. **[RESUELTO, confirmado por el usuario 2026-11-04] Humo y polvo del disparo desplazados** (arriba a la izquierda de la mira, y el polvo dentro de un rectángulo).
   - Descartado: la resolución ×2 (probado con 1: igual), instrucciones sin traducir, llamadas indirectas
     sin resolver y la colocación en el backend de la tubería fija (`nv2a_vsh_ff.c` está bien).
   - Según el MLOG, el juego ya envía esos vértices mal colocados. La causa probable está en la lógica del juego.
   - Se aparcó: es caro y el usuario lo aceptó.
2. **Costura en el centro de la pantalla al girar la cámara** — resuelta al apagar el brillo a pantalla
   completa (`RECOMP_D3D11_SKIP_RT=1`, fila quitada de F2). Notas viejas:
   - Viene del efecto de brillo a pantalla completa: copia de 640×480 a 512×256 y luego un abanico al 50 % desde (320,240).
   - Se revisaron sin encontrar el fallo: la conversión del abanico, la lectura de la copia y el ajuste `snap_2d`
     (no se aplica a texturas que son destino de render).
   - Plan B v1: `RECOMP_D3D11_SKIP_RT=512x256` rompía el menú (libro y carteles son destinos de 512×256).
   - **Plan B v2 (activo, sin probar):** `rt_copy_mark()` marca un destino como copia de otro más grande (o de
     otra copia); `skip_rt_overlay()` solo salta una copia devuelta sobre el destino del que salió. El libro no es
     copia del fotograma. `RECOMP_D3D11_SKIP_RT=1` en `env.bat`; se cambia en vivo en F2 > "Brillo a pantalla
     completa" para comparar.
   - Si se retoma: distinguir el brillo de otras pasadas (por ejemplo, abanico con el centro en (320,240), o el
     destino 640×480 con una textura que es un destino de render de 512×256 y 50 % de alfa).
   - Una captura F10 en el momento del fallo ayudaría.

## Cambios por repositorio (commits recientes)

`C:\rdr-port` (rama `gpu-d3d11`):

- `a06bf3e` Recorte por longitud y exceso pasado a los fotogramas siguientes.
- `b6af1c3` Ratón en la entrada del jugador (`sub_001A98C0`).
- `2b1e194` Primer ratón tipo Black (`sub_00028D20`).
- `e5ba14f` / `70c25f6` / `09dfa4c` Notas de `env.bat`: F8 y brillo encendido o apagado.
- `c161fdf` `tools/mlog_draws.py`.
- `CMakeLists.txt`: incluye `src/mouselook.c` y la definición de compilación de `recomp_0002.c`.
- `run_debug.bat`: incluye `RDR_MOUSE_TRACE=1`.

`C:\rdr-port\xboxrecomp-apex` (rama `rdr-port`):

- `43be546` `mouse.c`/`mouse.h`: modo directo y `TakeLook`.
- `9a830cb` Velocidad del juego ×2:
  - `kernel_pacing.c/h`: `xbox_SpeedSet`, `xbox_WarpCounts`, el ritmo de vblank se reinicia al cambiar la velocidad.
  - `kernel_hal.c`: contador de rendimiento, rdtsc, `KeQuerySystemTime`, `KeQueryInterruptTime`, `xbox_GuestTickMs`.
  - `xbox_memory_layout.c`: `KeTickCount`.
  - `nv2a_pb_d3d11.c`: F8.
- `38f6e5d` `RECOMP_D3D11_SKIP_RT` en `nv2a_pb_d3d11.c` (`skip_rt_overlay`).
- `3968588` Suavizado del stick emulado por el ratón (modo `stick`).
- Anteriores: F11 y F10 en `wnd_proc`, MLOG, tablas de salto de hasta 4096 entradas, conformance.

## Ronda 2026-11-03 noche

- Tienda: el volcado del usuario (23:40) trajo 13 texturas de armas (cuchillo, revólver, escopetas, dinamita y
  sus sombras). Escaladas con ultrasharp-4x (`escalar_texturas.py ultrasharp-4x`, 15 con 2 viejas) y sumadas
  con `texturas_pack.py agregar`: pack 3361 entradas, ordenado, sin repetidos. Sin probar en el juego.
- Línea blanca a la izquierda del libro del menú (x2..x4, 4:3 y 16:9): el corrimiento de medio píxel de los
  bordes 2D (set_vp, `vp_off.w`) solo se aplicaba con two_d, y two_d solo se calculaba con hor+ (pad) o
  snap_2d. RDR usa su 16:9 nativo (sin pad) y snap_2d quedó fijo en No: ningún lote era 2D y el borde en x.5
  dejaba la columna 0 del host mostrando la escena. Ahora `scan` también corre con escala > 1 en destinos no
  cuadrados (los cuadrados son mapas de sombra/brillo: ahí el corrimiento dibujaba las líneas de las sombras).
  Sin pad, two_d solo alimenta ese corrimiento y snap_2d. Compila; sin probar.
- F2: quitada la fila "Subtítulos siempre" (siempre Sí, `s_subtitles_always = 1` en movies.c).
- Cinemáticas en tiempo real a 60 fps: no, el juego avanza un paso por cuadro (ver "Más de 60 FPS"): irían al
  doble de velocidad. Opción: generación de cuadros del driver (NVIDIA Smooth Motion en la RTX 5070).
- Ratón al apuntar ("se mueve extraño, no se puede disparar cómodo"): sin cambiar todavía; falta saber qué
  pasa exactamente. Sospechas: AimRamp en modo apuntar (aceleración/rampa del .ccm o ayuda al apuntar),
  `frame_counts` con la ventana de 4 ms (dos lectores del mismo cuadro separados >4 ms toman cuentas
  distintas), y el salto de x3 al soltar el clic derecho con "Sensibilidad al apuntar" 300 %.
- Usuario: pasa con el clic derecho y "se pega a los enemigos". Variables de la ayuda al apuntar, registradas
  por nombre con `sub_00192370` (`0x14C298`..`0x14C5B1`): AimRampCrossingSoftLockRate `0x413638` (0.5),
  TargetDriftDelay `0x413648` (2), TargetDriftAccel `0x41364C` (0.1), LockedCursorAccel/Min/MaxSpeed
  `0x413658/5C/60` (1, 0.5, 2.5), TargetLockBorder `0x4137A4` (1.4), TargetUnlockBorder `0x4137AC` (1.8).
- 1er intento (77750f3, revertido): con el ratón, además de las dos de abajo, LockedCursorAccel 1000 y
  Min = Max. El usuario: "horrible, se mueve espantoso cuando no apuntás" -> el cursor enganchado también mueve
  la cámara fuera del apuntado. NO tocar LockedCursor*.
- Ahora (`aim_assist_off`): solo con el clic derecho apretado, CrossingSoftLockRate 1 y DriftAccel 0; al
  soltar vuelven los del juego. Sin el clic no cambia nada respecto de antes. Compila; sin probar.
- Black (github.com/Spark198rus/black-pc mouselook.cpp) suma el ángulo del ratón al yaw/pitch después del paso
  del stick, × factor de zoom, sin suavizado. En RDR las acciones de cámara (p_lookleftright 0x29FBB0, etc.)
  ya integran ángulo -= dt × [0x419FA8] × Lookstick, lineal: el ratón por el stick lineal equivale a eso.
- Video del usuario (2026-11-04 00-18-17.mkv), medido con correlación de fase cuadro a cuadro: con la mano
  pareja la cámara giraba 1, 1, 3, 0 px por cuadro. Causa: WM_INPUT iba a la ventana del juego y solo se
  procesaba en pump(), que el presentador D3D11 llama una vez por cuadro en el flip; el juego leía las cuentas
  en otro momento y recibía 0 o 2 tandas. Arreglo en el runtime (`mouse.c`): ventana solo-mensajes en un hilo
  de prioridad alta (`sink_window`, RIDEV_INPUTSINK, se aceptan solo con la ventana del juego al frente) que
  procesa cada reporte al llegar. El log dice `[INPUT] mouse: raw input on its own thread`.
- Al apuntar el video muestra la mira enganchada al blanco y la cámara reencuadrando a saltos. `aim_assist_off`
  (solo con clic derecho y ratón) ahora también pone TargetLockBorder 1.0 y TargetUnlockBorder 1.1 (eran 1.4 y
  1.8): engancha solo encima del blanco y lo suelta apenas sale. `rdr_menu.ini` mouse_aim 300 % -> 100 %.
- Todo compila; sin probar en el juego.
- 2º video (Mi video.mp4, 30 fps): el giro lento ya es parejo, pero en giros medianos seguían saltos (13, 38, 20,
  7; ceros en medio de un giro). Causa: `frame_counts` separaba cuadros por tiempo (>4 ms): dos cuadros
  seguidos para ponerse al día recibían las mismas cuentas dos veces. Ahora usa el contador de cuadros del juego
  `0x666738` (sub_00084100, el temporizador que también fija el dt, suma 1 por cuadro).
- Al apuntar el usuario necesitaba 200 %: el cursor enganchado acelera de LockedCursorMinSpeed 0.5 a Max 2.5 a 1
  por segundo, y un movimiento corto de mano nunca salía del arranque lento. Con clic derecho + ratón ahora es
  una sola velocidad (Accel 1000, Min = Max). Solo al apuntar: fuera de eso arruinó la cámara (77750f3).
  `rdr_menu.ini` mouse_aim vuelve a 100 % (la mira enganchada va hasta 5 veces más rápida que antes).

## Ratón: estado bueno guardado y ajustes al apuntar (2026-11-04)

- **Copia del ratón que funciona bien** (pedido del usuario): etiqueta git `raton-bueno-2026-11-04` en los dos
  repos (rdr-port y xboxrecomp-apex, commit b1c7501 / eff8d74) y copia de `mouselook.c`, `mouse.c` y
  `rdr_menu.ini` en `modding/backup_raton_2026-11-04/`. Volver: `git checkout raton-bueno-2026-11-04 -- <archivo>`.
- Usuario: caminar ya bien; al apuntar necesita 200 % como base. Ahora `s_aim_mult` por defecto 2.0,
  `env.bat` RDR_MOUSE_AIM_MULT=2.0, `rdr_menu.ini` mouse_aim=200%.
- "Si subo apuntar también camina más rápido": en el código no se tocan. `look_rad()` multiplica por
  `s_aim_mult` solo con el clic derecho apretado; el hilo `rdr_aim_sens_thread` de main.c solo cambia la
  sensibilidad del modo "stick emulado", que en modo directo no recibe el ratón. Si lo sigue notando, pedir
  video.
- Mira más humana (solo al apuntar): `frame_stick` pasa las cuentas por un suavizado exponencial de 30 ms
  (`AIM_EASE_S`) mientras el clic derecho está apretado; no se pierde ninguna cuenta (lo retenido sale al
  soltar). La cámara libre recibe las cuentas tal cual.
- Ruedita: arriba y abajo presionan WHITE (el cambio de arma del juego, en un solo sentido); BLACK solo en F.
- Correr: no hay botón. El juego camina o corre según cuánto se inclina el stick izquierdo (WalkLinearZone,
  RunLinearZone, WalkToRunDelay); el teclado da el stick completo, así que con WASD siempre corre (con la
  rampa `input.stick_ramp_ms`). No hay tecla de caminar configurada (`input.walk_key` sin valor).
- Investigación (ports y adaptaciones de ratón para juegos de consola):
  - Black PC (github.com/Spark198rus/black-pc): suma el ángulo del ratón al yaw/pitch después del paso del
    stick, × factor de zoom, sin suavizado ni aceleración; el stick no se apaga.
  - KAMI (github.com/dio-gh/KAMI, PCSX2/RPCS3 por IPC): sensibilidad en radianes por píxel, escribe el vector de
    la cámara en memoria; para Red Dead Redemption (PS3) además apaga el centrado automático de la cámara
    ("requerido, y mejora la experiencia"). Red Dead Revolver no está en su lista ni en los Mouse Injector.
  - Lo común en ports criticados: suavizado, aceleración, zona muerta y ayuda al apuntar pensadas para mando
    pasadas al ratón; el arreglo habitual es separar los caminos del ratón y del mando y apagar suavizado,
    "ease" y enganche para el ratón. Es lo que se hizo aquí (aim_assist_off).
  - Pendiente posible: el centrado automático de la cámara de RDR (CameraLookRate y afines) si el usuario nota
    que la cámara vuelve sola detrás del personaje.

## Mira libre a pie y carro del circo (2026-11-04, segunda vuelta)

- Copia del ratón antes de este cambio: `modding/backup_raton_2026-11-04b/` (mouselook.c, mouse.c, rdr_menu.ini,
  env.bat) y etiqueta git `raton-apuntar-200-2026-11-04` en los dos repos. La anterior (`raton-bueno-2026-11-04`)
  sigue igual.
- Usuario: con el arma fija (la ametralladora) la mira se mueve genial; a pie, apuntando (quieto o caminando),
  no se mueve con la misma libertad.
- Causa encontrada: a pie, sin enemigo fijado, la mira es un cursor que se mueve por la pantalla
  (sub_00143350, 0x0014396A) a una velocidad que sube de **FreeCursorMinSpeed** (0x681BA8, la pone un archivo
  de ajustes) a **FreeCursorMaxSpeed** (0x413654, 0.25) según FreeCursorAccel (0x413650, 0.1): los movimientos
  cortos de la mano nunca salen del arranque lento. Es la misma rampa que tenía la mira fijada
  (LockedCursor*). En el estilo de apuntado "principiante" la rampa es BeginnerModeCursorMinSpeed (0x681BB4) ->
  BeginnerModeCursorMaxSpeed (0x4136B4, 0.2).
- Cambio: mientras se apunta con el ratón (clic derecho), mínimo = máximo en las dos rampas (`aim_assist_off`,
  ahora 10 valores); al soltar vuelven los del juego. Caminar sin apuntar no se toca. Puede que 200 % ahora
  resulte rápido: se baja en F2.
- Lista completa de ajustes del juego con nombre (sub_00192370, 0x413608..0x413848) sacada del XBE. Otros que
  importan a la mira: CameraLookOffsetTop/Sides/Bottom 0.5 (la cámara gira cuando la mira pasa media pantalla),
  CameraLookRate 10, CameraLookDeadzone 0.06, TurnWhileTargetingRate / ...AndMovingRate 90, AimRampDecelerate 1,
  CursorBackupDelay/Speed. Sin tocar.
- Carro del circo "Professor Perry's" que titila a veces: no se ve en una foto fija. Las texturas del pack tienen
  mipmaps y filtro anisotrópico, así que la prueba es F6 (texturas mejoradas sí/no): si con F6 apagado sigue
  titilando es del juego (dos superficies a la misma profundidad); si no, es la textura escalada y se saca del pack.
- Resultado del usuario: el parpadeo es del juego (sigue con F6 apagado). La mira a pie quedó "muy bien, jugable".

## Ronda 2026-11-04: cámara al apuntar, cartel de F6

- Copia antes de esta ronda: `modding/backup_raton_2026-11-04c/` (mouselook.c, mouse.c, main.c, rdr_menu.ini,
  env.bat) y etiqueta `raton-mira-libre-2026-11-04` en los dos repos.
- Correr: no hay botón. WASD da siempre el stick a fondo (corre); Shift agacha y va despacio (lo dijo el usuario).
  No hace falta tecla de caminar.
- **Cámara al apuntar:** a pie la cámara solo giraba con la mira cuando ésta pasaba media pantalla
  (CameraLookOffsetTop/Sides/Bottom 0.5, sub_00143350 0x00143A08: dentro de esa caja se mueve la mira y la vista
  queda quieta; fuera, la vista gira con el movimiento × CameraLookRate). Con el ratón apuntando la caja es
  `AIM_LOOK_BOX` 0.2 (mouselook.c, dentro de `aim_assist_off`, 13 valores); al soltar vuelve 0.5. Sin probar.
- **Cartel de F6:** al cambiar las texturas aparece arriba al centro "Texturas mejoradas (modernas)" o
  "Texturas originales (antiguas)" durante 1,8 s (`xbox_MenuToast` en host_menu.c; `corner` = 2 en
  `menu_present`). Mientras está el cartel no se ve el recuadro de FPS. `s_owner` dice qué dibujo tiene la
  superficie compartida (menú, FPS o cartel). Sin probar.
- **Centrado automático de la cámara (pendiente):** no es un ajuste con nombre del XBE. La cámara la guían los
  archivos `.ccm` (CamMach); las acciones candidatas son `p_follow` (nombre en 0x402B74, registrado en
  recomp_0048.c:8709) y `P_FollowSimple` (0x402C1C, recomp_0048.c:8293). Falta ver qué hace su actualización y
  qué `.ccm` la usa a pie, y apagar solo el giro de vuelta detrás del personaje.
- Humo y polvo del disparo: resuelto (confirmado por el usuario).
- Diario de fin de nivel: queda para cuando el usuario pase un nivel completo (F6 apagado, F2 "Volcar texturas").

## Ronda 2026-11-04 tarde: suavizado de bordes, mandos modernos, botones de PlayStation

- **Suavizado de bordes (FXAA), hecho, sin probar:** F2 > Gráficos > "Suavizado de bordes (FXAA)" (sí/no, se
  guarda en `rdr_menu.ini` como `fxaa`; `RECOMP_FXAA=1` lo prende por defecto). Una pasada sobre el fotograma
  entero a su tamaño interno antes del escalado a la ventana (`aa_pass` en `nv2a_pb_d3d11.c`, sombreador
  `s_aa_ps_src`, propio, del tipo FXAA). Como el HUD está en el mismo fotograma, sus letras se suavizan un poco.
  No actúa con resolución x1 y filtro "más cercano" (ese caso presenta copiando).
- **Sombras y distancia de detalle:** el usuario decidió dejarlas como están.
- **Mandos modernos (hecho, sin probar):** SDL3 3.4.18 bajado con permiso del usuario
  (`third_party/SDL3-3.4.18`, del zip oficial `SDL3-devel-3.4.18-VC.zip`, sha256 78d84602…7acd; el zip queda
  en `third_party/dl`). `xboxrecomp-apex/src/input/sdl_pads_win.c`: en Windows, junto a XInput, lee por SDL3
  los mandos que no son de Xbox (DualShock 4, DualSense, Switch Pro, genéricos) con vibración. XInput sigue con
  los de Xbox; a SDL se le apagan XInput, RawInput, WGI y GameInput y se salta todo mando que diga ser de Xbox,
  así ninguno aparece dos veces. Puerto sin mando XInput = mando SDL del mismo número. Sin ventana SDL: los
  eventos de mando están apagados, la lectura del juego actualiza cada 2 ms y vuelve a buscar mandos cada 1 s.
  Se compila con `-DXBOXRECOMP_SDL3_DIR=C:/rdr-port/third_party/SDL3-3.4.18` (ya está en la caché de
  `rdr-apex/build`); `SDL3.dll` se copia junto al exe al compilar. Registro: `[INPUT] SDL pads on`,
  `[INPUT] SDL pad added slot=N "nombre"`. Sin la dll el juego no arranca: hay que llevarla con el exe.
- **Íconos de botones (hecho, sin probar en el juego):** F2 > Texturas > "Botones en pantalla": Teclado y
  ratón / Mando Xbox / Mando PS4/PS5 (se guarda como `botones`; por defecto teclado). F6 ya no cambia los
  botones: solo las letras y el resto.
  - Runtime: tipo nuevo de entrada del pack, `XRTP_KIND_BUTTON` 3 (`nv2a_tex_pack.h`), buscado antes que todo
    con `nv2a_tex_pack_find_button` por la clave `hash ^ (0x9E3779B97F4A7C15 * (1 + estilo*2 + F6))`, tanto
    por el hash de la textura como por el de sus índices (página de letras con paleta de fundido, con
    `font_retint`). Cambiar de estilo sube `nv2a_tex_pack_gen` y las texturas se vuelven a subir.
  - `tools/botones_estilo.py` agrega al pack (al final, índice nuevo, como `agregar`) 6 variantes por cada
    página de letras con botones (13 páginas distintas en todos los archivos) y por cada imagen de botón de la
    tienda (5): 810 claves, unos 110 MB. Letras: con F6 sí, las del pack (TrueType o 4x nítido); con F6 no, la
    página original agrandada 4x. Botones: teclado = `botones_teclado.icon`; Xbox = el glifo original del juego
    (del disco, no de `modding/mods`); PlayStation = cruz, círculo, cuadrado, triángulo, L2, R2 dibujados ahí
    (A=cruz, B=círculo, X=cuadrado, Y=triángulo). En la tienda, el Xbox es un botón redondo dibujado.
    `python tools/botones_estilo.py muestra` deja `modding/texturas/botones_estilos_muestra*.png`.
  - Cabecera del pack antes de agregarlos: `modding/texturas/textures.pack.cabecera_antes_botones.bin` (32
    bytes; escribirla sobre el principio del pack lo deja como estaba, el índice viejo sigue en el archivo).
  - Sin cubrir (igual que antes): páginas P4 de 16 colores (máquina de escribir, algunas de `swat.dat`), la B de
    la tienda #40 y LT/RT de #43. Ahí se ve lo de `modding/mods` (teclado) sea cual sea el estilo.
- **Botones automáticos y nitidez (2026-11-04, sin probar):**
  - F2 "Botones en pantalla" ahora tiene **Automático** (por defecto), Teclado y ratón, Mando Xbox, Mando
    PS4/PS5. Automático sigue al último control usado en el puerto 0 (`xbox_InputLastDevice`, input_core.c:
    botón, gatillo o stick bien movido del mando -> Xbox o PlayStation según `xbox_InputPadFamily`; tecla o clic
    -> teclado; el ratón movido lo avisa `mouselook.c` con `xbox_InputNoteDevice(0)`). Un hilo de main.c
    (`btn_auto_thread`, cada 150 ms) aplica el estilo. Uno elegido a mano queda guardado (rdr_menu.ini guarda el
    texto de la opción). El ini del usuario tenía `botones=Mando PS4/PS5` de la prueba: sigue fijo hasta que
    elija Automático.
  - Nitidez: las 9 páginas de letras con botones que no son de las 4 fuentes redibujadas (la letra de los
    carteles del juego, bridge2/barfight, swat) salían con el 4x de `letras.sharpen`, el que el usuario ya
    había descartado. Ahora esas páginas (y todas con F6 apagado) son la original agrandada 4x en bilineal,
    como la dibuja la placa. Las 4 fuentes TrueType quedan idénticas a las del pack de antes (comparado:
    0 píxeles distintos fuera de los botones).
- **Íconos de botones (plan original):** hoy los íconos de teclado salen de dos lados: (1) páginas de letras del
  juego repintadas en los archivos reconstruidos de `modding/mods` (`botones_teclado.py`, fijo) y en las letras
  del pack (tipo font, que F6 apaga junto con el arte); (2) los botones de la tienda, imágenes de 32x32 en el
  pack como arte (`BUTTON_IMAGES`), que F6 también apaga: por eso F6 cambia teclado <-> Xbox en la tienda.
  Plan: un tipo nuevo de entrada en el pack para los botones, con una variante por estilo (teclado, Xbox,
  PlayStation), que F6 no toque, y una fila de F2 "Botones en pantalla" para elegir el estilo.

## Ronda 2026-11-04 madrugada: ratón restaurado, sin FXAA, inventario de letras

- **Ratón:** el usuario pidió volver al estado bueno: `mouselook.c` es otra vez el de la etiqueta
  `raton-mira-libre-2026-11-04` (rampa de la mira libre aplanada al apuntar, SIN la caja de cámara 0.2), más
  solo el aviso de ratón movido para los botones automáticos (`xbox_InputNoteDevice(0)`).
- **FXAA eliminado** a pedido del usuario ("es horrible"): revert del commit en xboxrecomp-apex (ee039a3); la
  fila de F2 y `RECOMP_FXAA` ya no existen; `fxaa=` sacado de rdr_menu.ini.
- **Inventario de fuentes:** 67 fuentes distintas en los archivos del juego (contadas por tabla + páginas).
  Solo unas pocas tienen páginas P8 (las que el pack sabe reemplazar); la mayoría son P4 (16 colores) y su hash
  en el runtime no se conoce: el volcado (F2 "Volcar texturas", con F6 apagado) es la forma de verlo, pasando por
  la pantalla donde aparecen.
- **"Cargando, no apague su Xbox":** el texto no está como cadena en `default.xbe`, `front.dat` ni `swat.dat`
  (buscado en ASCII y UTF-16): casi seguro es una imagen de texto pre-dibujada (tipo TEXT del pack). Hace falta
  un volcado de esa pantalla de carga para identificarla.
- **Armas de papel de la tienda:** solo hay 13 (las del volcado del 03/11, ya mejoradas con ultrasharp). Las
  demás armas nunca se volcaron: hace falta recorrer todas las páginas de la tienda con el volcado prendido.

## Próximos pasos

**Al 2026-11-02 el usuario confirmó resueltos los errores anteriores** (tienda con teclas, letras nítidas,
brillo y línea de los bordes, texturas que perdían detalle). Abiertos:

- Subtítulos: probar "Subtítulos siempre" (sección "Subtítulos").
- Diario de fin de nivel: volcar sus texturas cuando el usuario pueda (F6 apagado, F2 "Volcar texturas").
- Letras de "Terminar": resuelto (ya eran vectoriales).

Lista vieja:

1. Que el usuario pruebe el ratón (commit `a06bf3e`) y decidir según su respuesta (ver "Si sigue tosco").
2. Opcional: quitar o mantener los registros `[LOOKTRACE]` (solo con `RDR_MOUSE_TRACE=1`).
3. Exportar de nuevo los parches del fork a `C:\rdr-port\patches\xboxrecomp-apex\`.
4. Guardar el renombrado de `recomp_0031.c` de forma reproducible (por ejemplo, un script en `tools/` que
   renombre las definiciones después de generar el código).
5. Costura: un intento acotado más con un filtro específico del brillo.
6. Humo: resuelto (el usuario lo confirmó el 2026-11-04).

## Ronda 2026-11-04 madrugada (2): volcado de letras y textos

- Volcado del usuario de las 02:12: solo salieron 2 imágenes nuevas de la tienda (escopeta de dos caños
  `EEE7B05B14459329` y dinamita `93174E3C9EE0F56A`); las demás ya estaban volcadas. Las dos se escalaron con
  ultrasharp y entraron al pack (`texturas_pack.py agregar`; cabecera previa en
  `textures.pack.cabecera_antes_armas2.bin`).
- **Por qué no salieron letras ni "Cargando, no apague su Xbox":** el volcado salteaba toda textura P8 (256
  colores), que es el formato de las páginas de letras y de las imágenes de texto. El último registro muestra
  muchos `miss ... fmt0B` (P8) sin reemplazo. "apague" no está en ningún archivo del juego (3,3 GB, ASCII y
  UTF-16): es imagen o texto con codificación propia.
- Arreglo (fork, `tex_dump`): ahora también vuelca P8, una vez por índices (`s_idx_hash`), así un texto que se
  desvanece no llena la carpeta de copias por paleta. Cada P8 volcado anota en `dump/p8_indices.txt`
  `clave_con_paleta clave_indices WxH`. Compilado, sin probar.
- Falta: que el usuario vuelva a volcar (F6 apagado, F2 "Volcar texturas") pasando por la pantalla de carga,
  menús, pausa, diario y tienda; después identificar letras/textos y mejorarlos.
- **Volcado de las 02:3x (con P8):** 20 páginas de letras, ninguna en el pack (ni por paleta ni por índices).
  Contacto en `dump/p8_indices.txt` (orden 0-19). Encontradas en los archivos (fuentes P4, coincidencia exacta):
  `front.dat` #206 (western bloque, págs 0-1 = volcado 3,4), #314 (western con contorno, 8,9), #231 (angosta,
  10-12), `swat.dat` #38377 pág 3 (angosta con acentos, 13). Las de 256x128 y 256x256 (serif de menús 0,1,2,5,6,17;
  western 14,15,16,18) **no están en ningún archivo**: el juego las arma en memoria (reacomoda letras de las
  páginas de 128 en una más grande), así que no hay tabla de letras para ellas. 7 = "BDSADEFHILORT" 128x64,
  19 = "KO" 64x64 (imágenes chicas).
- Ideas: (a) fuentes P4 con tabla -> redibujo vectorial (letras_vector) donde haya TrueType parecida;
  (b) páginas armadas en memoria -> ubicar cada letra por sus manchas y reconocerla comparando con la fuente
  original, luego redibujar; (c) las western no tienen TrueType equivalente en Windows.
- **Serif armada en memoria redibujada (`tools/letras_atlas.py`):** las páginas P8 del volcado que no están en
  ningún archivo vienen en orden de código (94 ASCII y después las que el texto usa, en orden creciente). La
  herramienta recorta cada letra (manchas agrupadas por fila y por superposición), nombra las 94 por su lugar y
  el resto por parecido con la TrueType (programación dinámica creciente, con preferencia por letras del
  castellano), y redibuja cada una con `pala.ttf` a 4x sobre su caja de tinta (como `letras_vector.py`). Solo
  páginas con parecido >= 0,55: entraron las 6 serif (875B38B5..., A71ED23F..., 069BC22B..., E16275E9...,
  CB8E1DA8..., 7CDAEF92...); las western dan ~0,25 con Palatino y quedan como están (solo Impact se les parece).
  Se probó `palab.ttf`: demasiado gruesa; Palatino normal es la misma de los textos legales.
  `letras_atlas.py agregar` las sumó al pack (12 claves: con paleta y por índices, tipo letra; cabecera previa
  en `textures.pack.cabecera_antes_atlas.bin`). Vistas en `modding/texturas/letras_atlas/*_comparar.png`.
  Sin probar en el juego.

## Ronda 2026-11-04 madrugada (3): logo, "Xbox" en textos, launcher

- **Logo a "30 fps":** `rslogo.mp4` sí está a 60 fps, pero el original tiene un tirón cada ~19 cuadros (un
  cuadro adelantado un paso y el siguiente repetido) y RIFE lo conservaba. `videos_60fps.py --parejo`
  redibuja ese cuadro a mitad de camino entre sus vecinos antes de interpolar. Rehecho `rslogo` y copiado a
  `mods/videos` (picos bruscos 4 -> 1; los cuadros quietos que quedan son pausas de la animación). El anterior
  quedó en `videos_60fps/rslogo.antes_parejo.mp4.bak`. Sin probar en el juego.
- **"Xbox" -> "PC" y botón Xbox Live:** los textos en castellano no están legibles en ningún archivo (ni
  "Guardar", "partida", "Cargando"): vienen comprimidos o codificados. El menú es Flash/ActionScript dentro de
  `swat.dat` (`_global.xboxButtons`, `acceptMainXbox`); `default.xbe` tiene `XboxLiveGroup`, `xboxlivename`,
  `xblive`. Para cambiarlos hace falta enganchar la carga de textos o el menú en el código recompilado.
- **Launcher tipo Splatterhouse (analizado `C:\Emuladores y Juegos\Splatterhouse`):** `Configuración.exe` (216 KB)
  abre `Launcher\Lanzador.ps1` (PowerShell + WPF, xaml en `Launcher\ui`), que edita `splatterhouse.toml`,
  muestra estado (exe, DLL, juego), respalda partidas y lanza el juego. `install.bat` extrae la ISO a `assets\`.
  Su `splatterhouse.exe` (79 MB) sí lleva el código traducido.

## Launcher y carpetas Game / Mods-Extras (2026-11-04, compilado, sin probar el juego)

- **El exe solo (`main.c portable_defaults`):** si junto al exe hay `Game\default.xbe` (o
  `Game\<carpeta>\default.xbe`), el juego usa esa carpeta, se para en la carpeta del exe (rdr_menu.ini y
  registros ahí), pone todos los valores de `env.bat` que falten, `Mods-Extras\` como carpeta de mods (videos en
  `Mods-Extras\videos`, archivos sueltos reemplazan a los del juego), `Mods-Extras\texturas\textures.pack` si
  existe y el volcado en `Mods-Extras\texturas\dump`. Sin `Game\` (desarrollo con `run.bat`) no cambia nada.
- **`Configuración.exe` (`tools\launcher\Configuracion.cs`, `compilar.ps1`):** C# WinForms con el csc de
  .NET Framework 4 que trae Windows. Muestra el estado (juego, texturas, videos, exe), edita `rdr_menu.ini` con los
  mismos valores que F2 (imagen, controles, idioma), botones JUGAR / Guardar / Valores por defecto / Abrir Game /
  Abrir Mods-Extras. Revisado con una captura de su ventana.
- **`tools\armar_paquete.ps1 [-Prueba]`:** arma `dist\Red Dead Revolver PC\` (RedDeadRevolver.exe, SDL3.dll,
  Configuración.exe, LEEME.txt, `Game\PEGAR ACA EL JUEGO.txt`, `Mods-Extras\LEEME.txt`). `-Prueba` enlaza sin
  copiar el juego de esta PC (unión), el pack y los videos (enlaces duros). `dist/` y el exe del launcher están en
  `.gitignore`.
- Falta: que el usuario pruebe abrir el juego desde `dist\...\Configuración.exe`; ícono propio; decidir cómo
  publicar sin repartir el código traducido (el exe lo lleva adentro).
- **Ajustes y subcarpetas (2026-11-04):** los valores por defecto del launcher son los del usuario en F2
  (panorámico Sí, FPS Sí, resto igual); `armar_paquete.ps1` deja un `rdr_menu.ini` con esos valores, y el exe
  arranca con `RECOMP_WIDESCREEN=1`. `rdr_find_file` (main.c) busca hasta 4 niveles: el juego en cualquier
  subcarpeta de `Game\`, `textures.pack` en cualquier subcarpeta de `Mods-Extras\`, y `movies.c` busca cada
  `<nombre>.mp4` en cualquier subcarpeta (salteando `dump`). El launcher detecta igual. F2 sigue en el juego.
- **Pesos:** programa (RedDeadRevolver.exe 158 MB + SDL3.dll 2,7 MB + Configuración.exe 21 KB + ini/LEEME)
  ~161 MB; en .zip ~47 MB. Pack: 11,06 GB, de los que 9,66 GB son 3233 texturas de arte (RGBA sin comprimir, con
  mips), 0,1 GB botones, 0,04 GB letras; ~1,2 GB es espacio muerto de índices y entradas reemplazadas.
  Comprimido sin pérdida (zlib) quedaría en ~36 % (~4 GB). En BC3 (formato de GPU que el runtime ya lee,
  `XRTP_FLAG_BC3`) el arte pasaría a ~2,4 GB, con una pérdida leve; las letras y botones quedarían sin tocar.
- **Texturas en BC3 (`tools\bc3\bc3pack.c`, `compilar.ps1`):** compresor BC3 propio en C (sin descargas): eje
  principal del bloque ponderado por alfa + un ajuste por mínimos cuadrados, alfa en modo de 8 valores. Solo arte
  (tipo 0); letras, textos y botones quedan RGBA. Prueba con 6 texturas de 1024: 39-41 dB, sin diferencia a la
  vista. `bc3pack textures.pack textures_bc3.pack` (58 s): 3233 en BC3 (9,66 -> 2,41 GB), 127 sin tocar,
  **pack nuevo 2,56 GB** (`modding\texturas\textures_bc3.pack`, índice verificado). **El original
  `textures.pack` (11,06 GB) no se tocó.** Para comparar: `run.bat` usa el original;
  `armar_paquete.ps1 -Prueba -BC3` pone el BC3 en `dist` (abrir `dist\...\Configuración.exe`). Sin probar en el juego.
- **BC3 elegido (2026-11-04):** el usuario no ve diferencia. `env.bat` (run.bat) y `armar_paquete.ps1 -Prueba`
  usan `textures_bc3.pack`; `-SinComprimir` vuelve al de 11 GB. `textures.pack` queda como fuente: toda
  herramienta que agrega texturas escribe en él, y después hay que correr
  `tools\bc3\bc3pack.exe modding\texturas\textures.pack modding\texturas\textures_bc3.pack` (~1 min).
- **Botones del primer menú (reporte del usuario, versión de prueba de `dist`):** elegir PS/Xbox en el launcher no
  cambiaba los botones del primer menú. Revisado: el ini se lee antes de iniciar el kernel y `set_btn_style` aplica
  el estilo; las fuentes de 16 colores del volcado (#206, #314, #231, swat #38377) no tienen botones; los botones
  de los menús son las imágenes de 32x32 A/Y/X/B (ya con estilos). En los archivos también hay botones de PS2
  sin usar (triángulo `E72699B9...`, círculo `C1640D20...`, cuadrado `0A4A1FC5...`). Sin causa encontrada: hace
  falta una captura del menú. Encontrado de paso: `armar_paquete.ps1` pisaba el `rdr_menu.ini` del jugador en
  cada rearmado; ahora solo lo crea si no existe.
- **Compilar en la PC del jugador:** el código generado son 97 MB de C en 83 archivos; acá compila en ~10 min
  con 8 hilos. Ver la respuesta al usuario del 2026-11-04 (estimación y herramientas necesarias).
- **Registro en el paquete:** en modo `Game\`, el exe escribe su salida en `registro.txt` junto al exe
  (`RECOMP_STDIO_LOG`) con `RECOMP_TRACE=tex_pack`; cada cambio de estilo de botones deja
  `[TEXPACK] button style N`. Captura del usuario: el menú del diario ("Entrar"/"Opciones") mostraba los A/X de
  Xbox. Esos A/X son las imágenes de la tienda (`562B8D10...` y `94525540...`): en la partida de las 02:12 dieron
  `hit` de tipo botón en estilo teclado (`6A457E62...`, `A83CA632...`). El caché de texturas sí se refresca al
  cambiar el estilo (`pack_gen`). Falta el `registro.txt` de una prueba desde el launcher.
- **Botones del diario resueltos (2026-11-04):** "Entrar"/"Opciones" dibujan sus botones desde una página de letras
  con los A/Y/X/B redondos de Xbox ya dibujados (`7ACEF9DD...`, 128x128, DXT). No está en ninguna tabla de
  letras de los archivos: había entrado al pack como arte (Upscayl), por eso se veía "ultra definida" y siempre
  Xbox. Hay 7 páginas así en el volcado (2 Xbox, 5 con los botones de PS2 que el juego también trae), listadas en
  `botones_estilo.DUMPED_BUTTON_PAGES` con su familia. `botones_estilo.py volcado [muestra]`: cada símbolo de
  color (piezas unidas), el disco medido por su área y nunca más allá de la mitad hasta el vecino, un tamaño por
  página; variantes 3 estilos x F6 (F6 sí: la escalada del pack; no: original 4x bilineal; estilo Xbox en página
  Xbox: el botón original). Vistas en `modding/texturas/botones_volcado_*.png`. 42 claves al `textures.pack`
  (cabecera previa en `textures.pack.cabecera_antes_botones_volcado.bin`) y BC3 rehecho (2,61 GB). Sin probar.

## Íconos, README y rutas (2026-11-04)

- **Íconos (`tools/iconos.py`):** desde la portada que pasó el usuario (escalada 4x con ultrasharp,
  `assets/iconos/portada_x4.png`): `juego_{cuadrado,redondo}.ico` y `config_{cuadrado,redondo}.ico` (la misma
  imagen un poco más oscura con un engranaje crema), 16 a 256 px; `muestra.png` para comparar. El elegido se copia
  como `juego.ico` / `config.ico` (por ahora los cuadrados). El exe lo toma por `rdr-apex/src/icono.rc` y el
  launcher por `/win32icon`, ambos solo si el archivo existe. `assets/iconos/` está fuera de git (es arte de la
  portada). Verificado extrayendo el ícono de los dos exe de `dist`.
- **Rutas personales fuera del repositorio:** el juego ahora es `juego\` en la raíz (unión a la carpeta real en
  esta PC, en `.gitignore`) o la variable `RDR_JUEGO`: `main.c` (`..\juego`, XBE `..\game_files\default.xbe`),
  `rdr/src/main.c`, `tools/extraer_audio.py`, `tools/videos_seedvr2.py`, los `.bat` de `modding`,
  `armar_paquete.ps1`; `ver_progreso.ps1` toma la carpeta por parámetro. ESTADO.md usa `<carpeta del juego>` y
  `%USERPROFILE%`. Los parches dicen `From: rdr-port`. Las copias `modding/backup_raton_*` siguen en disco pero
  fuera de git. **El historial de git conserva el correo de los commits** (autor configurado en git).
- **README.md** nuevo, en inglés y español: qué es, cómo jugar (Game / Mods-Extras / Configuración.exe), teclas,
  cómo compilar, créditos y licencias (xboxrecomp MIT, SDL3 zlib).
- **Íconos elegidos:** los cuadrados (`juego.ico` = `juego_cuadrado.ico`, `config.ico` = `config_cuadrado.ico`), ya puestos.

## Versión terminada (2026-11-04)

- **Carpeta final:** `C:\Emuladores y Juegos\Red Dead Revolver PC\` con copias reales (no enlaces):
  RedDeadRevolver.exe, SDL3.dll, Configuración.exe, LEEME.txt, rdr_menu.ini (ajustes del usuario), `Game\` con el
  juego (115 archivos, verificado), `Mods-Extras\texturas\textures.pack` (= textures_bc3.pack, verificado) y
  `Mods-Extras\videos\` (23 MP4). 6,97 GB. Plan de publicación: repositorio en una cuenta nueva de GitHub;
  texturas y videos en Google Drive.
- **Limpieza hecha (el usuario confirmó; antes se quitó la unión al juego dentro de `dist`, el juego quedó intacto):** `dist\` (~170 MB propios; ¡tiene una unión al
  juego, borrar la unión primero!), `modding\videos_30fps` (930 MB, idéntico a `videos_mejorados`),
  `modding\videos_60fps` (997 MB, idéntico a `mods\videos`), `modding\audio\stream0` y `stream1` (1,66 GB, WAV
  extraídos, se rehacen con `extraer_audio.bat`; queda `doblaje.json`), `rdr-apex\runs` (519 MB de registros
  viejos), `rdr\build` y `rdr\runs` (270 MB, proyecto viejo), `analysis\` (163 MB, análisis del proyecto viejo).
  También se vació `rdr-apexuns` (run.bat lo vuelve a crear). `armar_paquete.ps1` rearma `dist`;
  `videos_60fps.py` vuelve a crear `videos_30fps` y `videos_60fps` cuando hace falta.

## Foco: ratón trabado y controles muertos (2026-11-04, compilado, sin probar)

- **Reporte (2 PCs):** (1) al abrir el juego (launcher o exe) el cursor quedó encerrado sobre una ventana de
  carpeta; (2) después de cambiar opciones en F2 no respondía ningún control, solo F2.
- **Causa:** el foco salía solo de los mensajes de Windows. (1) La ventana podía tener el foco dentro de su hilo
  sin estar adelante (el launcher se cierra, Explorer queda arriba): el ratón se capturaba igual (ClipCursor y
  re-centrado) sobre el rectángulo que tapaba la carpeta. (2) La pausa en segundo plano se prendía con
  `WM_ACTIVATEAPP(FALSE)`; si el `TRUE` se perdía (cambio de pantalla completa desde F2), la pausa seguía.
- **Arreglo (fork):** `mouse.c`: `clip_client` nunca encierra si la ventana no es la de adelante; `Win32Sync`
  compara cada pump `GetForegroundWindow()` con el foco guardado y lo corrige, y solo captura estando adelante.
  `nv2a_pb_d3d11.c`: `pump()` recalcula `s_unfocused` con `GetForegroundWindow()`; el primer flip pide
  `SetForegroundWindow` una vez (si Windows no deja, el juego espera pausado con el cursor libre hasta un clic).
  Copiado a `C:\Emuladores y Juegos\Red Dead Revolver PC\RedDeadRevolver.exe`.

## Texturas en segundo plano y medición (2026-11-04, compilado, sin probar)

- **Copia previa:** `modding\backup_texturas_2026-11-04\` (nv2a_tex_pack.c/.h, nv2a_pb_d3d11.c y el exe anterior
  como `RedDeadRevolver_antes.exe`) y la etiqueta `texturas-sincronas-2026-11-04` en el fork.
- **Antes:** cada textura del pack se leía en el hilo que dibuja la primera vez que aparecía, abriendo y cerrando
  el archivo cada vez; el cuadro esperaba al disco. Lo leído quedaba en memoria para siempre.
- **Ahora (`nv2a_tex_pack.c`):** el archivo queda abierto (un solo handle con candado). Las texturas de arte las
  lee un **hilo de carga** (prioridad baja): el primer cuadro dibuja la textura original y, cuando la mejorada está
  lista, la caché la vuelve a subir (`TexEntry.pack_wait`, `nv2a_tex_pack_ready`). Letras, textos y botones se
  siguen leyendo en el momento. **Precarga:** cada minuto se guarda `<pack>.usadas` con las texturas usadas; al
  arrancar, el hilo las precarga cuando no tiene pedidos (hasta 3/4 del presupuesto). **Memoria:** presupuesto
  `RECOMP_TEXPACK_MB` (1536 MB por defecto); pasado eso, cada 2 s se liberan las que no se usan hace más de 30 s.
- **Medición en `registro.txt`:** cada 5 s con lecturas, una línea `[TEXPACK] 5 s: en el cuadro N lecturas X ms
  (max Y ms); en segundo plano M (Z ms), precargadas P, cambios tardios C; leido MB, en memoria MB`. "En el cuadro"
  es lo que frena el juego; "cambios tardíos" son las texturas que se vieron originales un momento.
  Al arrancar: `[TEXPACK] loader thread on; budget 1536 MB; N to preload`.

## Volcado apagado al arrancar y .zip para GitHub (2026-11-04)

- **Volcado:** el `rdr_menu.ini` copiado a la carpeta final traía `tex_dump=Sí` de las pruebas en `dist`; la partida
  de las 06:18 volcó 162 imágenes en `Mods-Extras\texturas\dump` hasta que el usuario lo apagó. Ahora `set_dump`
  ignora el valor guardado (`host_menu.c`, `s_loading`): cada partida arranca sin volcar; F2 lo prende en el momento
  y `RECOMP_TEXTURES_DUMP=1` sigue funcionando. Exe copiado a la carpeta final.
- **Parches del runtime:** `patches/xboxrecomp-apex/` rehechos con los 46 commits sobre `e5a7087` (apexJCL), autor
  `rdr-port`, con `BASE.txt` y `LEEME.txt` (cómo aplicarlos).
- **Superposiciones del HUD** (nombres del duelo sobre las barras, "4 4 4" sobre las balas): el usuario cree que
  son del juego; sin cambios.
- **.zip para GitHub:** `C:\Emuladores y Juegos\Red Dead Revolver PC\rdr-port-github.zip` = `git archive` del
  repositorio (solo archivos seguidos por git: código, herramientas, parches, README, ESTADO; sin juego, sin código
  generado, sin texturas, videos ni íconos).

## extract-xiso y release para GitHub (2026-11-04)

- **extract-xiso v2.7.1** (licencia tipo BSD, in@fishtank.com) en `tools/extract-xiso/` (el `.exe` lo ignora
  `.gitignore`; el `LICENSE.TXT` sí va). `armar_paquete.ps1` lo copia a `Herramientas\extract-xiso\` y escribe
  **`Instalar juego desde ISO.bat`**: se le arrastra la ISO (o busca un `.iso` en la carpeta o en `Game`), corre
  `extract-xiso -d Game -x <iso>` (las opciones van **antes** de `-x`; al revés extrae en la carpeta actual) y
  comprueba que quede `default.xbe`; si ya hay juego en `Game`, no hace nada. Probado con una ISO chica armada con
  `extract-xiso -c`, nombre con paréntesis incluido.
- Archivos "PEGAR ACA ..." en `Mods-Extras\texturas` y `Mods-Extras\videos`; LEEME del jugador con los pasos nuevos.
- **`armar_paquete.ps1 -Release`** arma `dist\RedDeadRevolverPC.zip` (47 MB): exe, SDL3.dll, Configuración.exe,
  el .bat, Herramientas, LEEME, `rdr_menu.ini` con los valores por defecto y las carpetas vacías con sus
  instrucciones. Sin juego, texturas, videos, registros ni volcados. Rutas con `/` y nombres en UTF-8.
  Va como asset de un **Release** de GitHub (el repositorio no acepta archivos de más de 100 MB; el exe pesa 158 MB).
  Copiado a la carpeta final junto con el .bat y Herramientas.
- README (inglés y español): pasos con Releases, la ISO y dónde pegar texturas y videos; crédito de extract-xiso.

## Teclas muertas al prender las texturas en una PC lenta (2026-11-04)

- **Reporte:** PC con 16 GB DDR3, disco mecánico y GT 1030: 40-50 fps en el tutorial. Al prender "Texturas
  mejoradas" en F2 y volver al juego, ninguna tecla respondía.
- **Causa probable** (sin registro de esa PC todavía): los candados del paquete (`io_lock`, `q_lock`) y la espera
  de una entrada en lectura eran giros puros. El hilo de carga corre con prioridad baja y tiene el candado mientras
  lee del disco; con el disco lento y todos los núcleos ocupados, el cuadro giraba esperándolo, la ventana dejaba
  de procesar mensajes y el juego no veía las teclas.
- **Cambio (`nv2a_tex_pack.c`, `relax`):** tras 64 vueltas cede con `SwitchToThread` (deja correr al hilo de
  carga aunque tenga menos prioridad) y desde las 256 duerme 1 ms. Parche 0048. Exe copiado a la carpeta final y
  `RedDeadRevolverPC.zip` rehecho. Copia previa en `modding/backup_texpack_lock/`.
- Para confirmar: el `registro.txt` de esa PC (líneas `[TEXPACK] 5 s: en el cuadro ... max Y ms`).
- **Cómo publican otros:** BLACK (black-pc) no trae código del juego: su exe carga el `default.xbe` del jugador y
  ejecuta el x86 original. OpenShao (Shaolin Monks) es recompilación estática como este port y publica el exe en
  Releases.

## Revisión de todas las opciones del F2 (2026-11-04)

- El usuario aclara: en la PC lenta (DDR3, disco mecánico, GT 1030) iba a 40-50 fps ya con resolución x1 y sin filtro.
- **Revisadas una por una** (qué hace cada `set` y cuándo se aplica):
  - Resolución interna, filtrado, pantalla completa: piden el cambio (`nv2a_host_opts_request`, un candado de
    instantes) y el cuadro lo aplica después del present (`d3d11_on_flip`: `scale_drop`, `fullscreen_switch`).
  - Tamaño de ventana: `window_apply` en el cuadro, solo en ventana. VSync, mostrar FPS, volcado: un valor.
  - Panorámico e idioma: valor del kernel, rige al reiniciar. Velocidad: `xbox_SpeedSet`.
  - Ratón (sensibilidades, invertir, modo, giro): valores leídos por mouselook; el modo además
    `xbox_InputMouseDirect`.
  - Botones en pantalla: `nv2a_tex_pack_set_button_style` (sube `s_gen`, re-sube texturas).
  - Texturas mejoradas: máscara de tipos; desde ahí las texturas se piden al hilo de carga.
  - Abrir/cerrar el menú limpia teclas y suspende el ratón; el foco se recalcula en cada `pump`.
  Ninguna espera nada salvo la de texturas, que en disco mecánico es la única que toca el disco.
- **Arreglos (parche 0049):**
  - El cuadro lee con su propio archivo abierto y el hilo de carga con otro: el cuadro ya no espera detrás de una
    lectura de fondo.
  - El hilo de carga corre en `THREAD_MODE_BACKGROUND_BEGIN`, con prioridad baja de disco: el streaming del propio
    juego (`stream*.dat`, niveles) pasa primero. Con disco mecánico y la misma prioridad, el juego podía quedar
    esperando sus datos y dejar de responder.
  - El registro anota `[MENU] abierto/cerrado` y `[MENU] clave = valor` en cada cambio.
- Falta confirmar con el `registro.txt` de la PC lenta. El que está en la carpeta final (14:24) es de una partida
  en la PC del usuario: prendió y apagó las texturas sin pausas ni trabas.

## Registro de la PC lenta: el hilo del mando se cae (2026-11-04)

- El `registro.txt` que estaba en la carpeta final (14:41, exe de las 14:34, pantalla 1366x768, usuario `hpgaga`)
  era de la PC lenta. Secuencia: precarga 237 texturas; `[PACE] game speed x2` (Ctrl+F8); F2 abierto, `vsync = No`,
  cerrado; `x4` justo cuando cargaba el nivel (perfnew.dat, hilo nuevo); `x1`; y unos segundos después:
  - `[CRASH]` en un hilo del juego (esp 0x010BFCC0): `sub_00047F10` (categoría game_input) llama a
    `sub_003C88B4` (XInputGetState) con el handle de `[0x0040E640+0x34]`, y `[handle+0xA3]` vale **0xCCCCCCCC**
    (memoria sin inicializar): lee 0xCCCCCCF4.
  - Otro `[CRASH]` en el hilo principal leyendo 0x84000000 (fin de los 64 MB), ya con el proceso cayéndose.
  - Sin enchufes ni desenchufes de mando en el registro.
- **Lectura:** las "teclas muertas" eran el juego **caído**: Windows congela los hilos mientras arma su informe
  de error, la imagen queda y nada responde. El fallo vino después del avance rápido; no se puede asegurar que
  sea la única causa (el primer reporte en la PC lenta no tiene registro).
- **Cambios:**
  - `main.c`: `SetUnhandledExceptionFilter` → línea `[CRASH] unhandled`, aviso "El juego tuvo un error y se va a
    cerrar... mandá registro.txt" y cierre inmediato (solo para errores que nadie atrapó; la VEH sigue igual).
  - Parche 0050: Ctrl+F8 y la fila "Velocidad" del F2 solo con `RDR_VELOCIDAD=1` (herramienta de prueba).
  - LEEME y README sin la tecla de velocidad.
- Carpeta final: exe nuevo, `rdr_menu.ini` por defecto, `registro.txt` y `xbox_kernel.log` borrados (pedido del
  usuario), zips rehechos. Copia previa de los tres archivos en `modding/backup_crash_speed/`.

## Personaje caminando solo y controles muertos: el juego lee el mando directo del PC (2026-11-04)

- **Reporte (PC lenta, exe de las 14:46):** ya no se cierra, pero tras ~1 minuto el personaje siguió caminando
  hacia adelante para siempre; la cámara se movía con el ratón, pero no se podía apuntar ni nada.
- **Registro (Descargas\registro.txt, 14:51):** sin errores, sin pausas, sin cambios de foco; F2 solo `vsync = Sí`.
  Estilo de botones siempre 0 (nunca se usó un mando del PC).
- **Causa:** el juego lee el mando con `XInputGetState` del XDK (`sub_003C88B4`, stdcall, `ret 8`; la llaman
  `sub_00047F10` "game_input" y `sub_00197BD0` por puerto). Esa función copia el último reporte que entregó el
  **mando USB emulado** (`ohci.c` + `usb_gamepad.c`, donde se mezclan teclado, ratón y mandos). Si la emulación
  USB deja de entregar reportes, el juego se queda con el último: tenía W (stick adelante) apretado. La cámara
  seguía porque mouselook lee el ratón por su cuenta. El cierre anterior fue lo mismo visto de otro lado:
  `XInputGetState` leyó una estructura de dispositivo llena de 0xCC.
- **Arreglo:** `rdr-apex/src/mando_directo.c` reemplaza `sub_003C88B4` (la traducida queda como `_pad` en
  `recomp_0077.c`, vía `tools/rename_pads.py`). Escribe en el `XINPUT_STATE` del juego el estado del PC
  (`xbox_InputGetState(0)`: teclado, ratón y mandos mezclados, lo mismo que mandaba el USB), sin tocar la
  estructura del dispositivo; como mucho una lectura cada 4 ms (el juego pregunta desde dos lugares por cuadro).
  El mando USB sigue enchufado para el juego, pero reporta todo en reposo y no lee el PC
  (`usb_gamepad_host_direct`, parche 0051), así no le roba al juego el movimiento del ratón ni los cambios de
  tecla. `RDR_MANDO_USB=1` vuelve al camino USB para comparar. En el registro:
  `[INPUT] game controller read: host state (direct)`.
- Copias previas en `modding/backup_mando_directo/`. Exe copiado a la carpeta final, zips rehechos. Volcado de
  `Mods-Extras\texturas\dump` borrado (pedido del usuario).
- **Probado por el usuario en la PC lenta: resuelto** (sin caminar solo ni teclas muertas).
- Rendimiento en esa PC (GT 1030, DDR3, disco mecánico): tutorial con lluvia y fuego ~30 fps; segundo nivel
  49-55 fps. Subir la resolución de x1 a x3 no cambia los fps: el límite es la CPU (juego traducido +
  traducción de comandos de GPU), no la placa de video. Para mejorar ahí habría que perfilar el lado CPU.

## Rendimiento en la PC lenta (i5-3330, 4 núcleos): revisión del lado CPU (2026-11-04)

- Revisado sin cambiar código: compila con /O2 /Ob2 (runtime /O2); ningún bucle de espera activa (USB, vblank,
  candados ceden o duermen); el código invitado corre detrás de la compuerta de "una CPU" (como la Xbox), así que
  el juego en sí usa un núcleo, y el traductor de push buffer + D3D11 otro (hilo ack). Cada textura usada se
  re-hashea entera una vez por cuadro (`tex_bind`, `nv2a_tex_hash` de 4 carriles): candidato, pero cambiarlo
  arriesga texturas animadas viejas; no se toca sin medir.
- Medición: `Medir rendimiento.bat` (solo en la carpeta final, no en el release) corre el juego con
  `RECOMP_TRACE=tex_pack,prof=250,prof_delay=40,prof_out=rendimiento.txt` (perfilador por muestreo del runtime,
  `host_prof.c`; escribe al cerrar, Alt+F4 incluido). Exe y PDB de esa versión guardados en
  `modding/perf_build/` para simbolizar las direcciones (offsets de módulo) del informe.
- **Resultado (rendimiento.txt de la PC lenta, ~150 s, texturas mejoradas apagadas):** `tools/perfil.py` (llvm-symbolizer
  de VS sobre el exe guardado).
  - Hilo principal del juego: 89% ocupado. **22,5% en `sub_0033EDE0`** = KickOff de D3D: pone el bit 16 de PFB
    0x100410 (vaciar write-combine) y gira hasta que se borra. Lo borra el hilo ack recién cuando el walker
    terminó el segmento anterior (`xbox_memory_layout.c`, "The KickOff flush"): el cuadro cuesta juego + dibujo
    en serie. El resto del hilo está repartido (ninguna otra función >2,4%).
  - Hilo nv2a-ack (walker + D3D11): ~27% trabajo real (`nv2a_pb_exec_method` 8%, `register_from_env` 5%,
    `nv2a_tex_hash` 1%), el resto esperando (`xbox_HostNapNs` 22%, ntdll 51%). El re-hash de texturas no pesa.
  - Conclusión: el límite es el hilo del juego, y casi un cuarto de su tiempo es esperar al walker.
- **Prueba propuesta (opt-in, sin tocar el exe):** `Probar modo rápido.bat` en la carpeta final =
  `RECOMP_DEBUG=run_ahead=1` (walker publica GET cada ~4 KB y acka el flush con 1 segmento por delante; las NOP
  con notify levantan la interrupción PGRAPH; opción experimental del fork apex, sin probar en RDR) + perfilador a
  `rendimiento_rapido.txt`. Riesgos posibles: cuelgue esperando la interrupción, fallas gráficas. Si anda y gana,
  se puede volver default en `portable_defaults` (main.c).
- **Prueba del usuario en la PC lenta:** +5 a 8 fps según la zona, sin fallas ni cuelgues; registro limpio. El giro
  de KickOff bajó de 22,5% a 13,6% del hilo del juego.
- **Opción "Modo experimental"** (pedido del usuario: "activar en PC gama baja"), apagada por defecto:
  - `rdr_menu.ini`: `modo_rapido=No` / `modo_rapido=Sí (PC gama baja)`.
  - Configuración.exe: grupo "Juego", con explicación en el tooltip (ventana una fila más alta).
  - main.c: `fast_mode_from_ini()` lee la línea antes del paso 3 (el walker lee `run_ahead` una sola vez al
    iniciar la memoria) y pone `RENV_RUN_AHEAD=1` salvo que el entorno ya traiga `run_ahead`. Log:
    `[rdr] modo experimental: on (run_ahead)` / `off`.
  - F2: fila "Rendimiento → Modo experimental (al reiniciar)" (`k_fast_rows`); solo guarda la elección para el
    próximo arranque, y existe para que F2 no borre la línea al reescribir el ini.
  - `armar_paquete.ps1` escribe `modo_rapido=No`. Copias previas en `modding/backup_modo_rapido/`.
  - Exe y Configuración.exe copiados a la carpeta final; zip de release rehecho. `Probar modo rápido.bat` y
    `Medir rendimiento.bat` siguen en la carpeta final (solo para medir). Sin probar la opción desde el launcher.
- **Configuración.exe en pantallas chicas** (reporte del usuario: la ventana no se achicaba y los botones quedaban
  fuera de la pantalla): ahora es redimensionable (mínimo 560x360). Los ajustes van en un panel con scroll
  (`body`) y los botones en un pie fijo (`footer`, siempre visibles). Al abrir, `FitScreen()` la achica al área de
  trabajo del monitor si no entra. El tamaño por defecto es el de antes. Copia previa en
  `modding/backup_ventana_config/`. Copiado a la carpeta final; zip de release rehecho. Probado por el usuario en
  la PC lenta: "se ejecutó bastante bien".

## Mando del tutorial: revertido (2026-11-04)

- El usuario pidió sacar todo ("elimina todo deja como estaba"): al pasar el primer nivel el juego quedó en negro.
- Revertido: el fork (`8eaa20a` revierte `e339218`, el reemplazo del modelo por la imagen de teclado), el repo
  (`tools/mando_tutorial.py`, patch 0052 y las notas de los dos intentos) y los tres packs (truncados al tamaño
  previo con su cabecera de `modding/backup_mando_tutorial/`; 4227 entradas, sin ninguna clave del mando).
  Exe recompilado y copiado a la carpeta final.
- Lo que dice el registro de esa partida (copia en `modding/backup_mando_teclado/registro_pantalla_negra.txt`):
  el reemplazo actuó una vez, sobre un recuadro de 5x6 píxeles en el centro de la pantalla (982,719-987,725 de
  1920x1440), o sea que esa textura también la usa algo chico del nivel, no solo el mando del tutorial. Al terminar
  el nivel, después de abrir `pupshow.dat`, el juego llamó a `KeBugCheck` (código 0) 757 veces: el juego se frenó
  solo, no hubo un fallo del port. No está confirmado que lo haya causado el cambio. Si vuelve a pasar sin él,
  hay que investigar `pupshow.dat` y quién llama a `KeBugCheck`.
- Datos útiles si se retoma: la textura del mando es `1BA085E83C2A7AEA` (256x256, opaca, guardada al revés);
  White = L1/Q, Black = R1/F. El mecanismo de imagen plana sigue en el historial del fork (`e339218`).
- La partida del usuario sigue respaldada en `C:\Emuladores y Juegos\Red Dead Revolver PC\Respaldo partida 2026-11-04`.

## Publicado en GitHub (2026-11-04)

- Repositorio: https://github.com/dennisabalo18-bot/red-dead-revolver-pc (remoto `origin`).
- Se subió **un solo commit** (`31ae08b`, etiqueta local `publicado-github`) con el árbol de `d8f6d50`, autor
  `dennisabalo18-bot <dennisabalo18-bot@users.noreply.github.com>`: el usuario no quiere su correo público (los
  commits locales lo tienen). El historial local queda igual y no se sube.
- Para subir cambios después: otro commit sobre `publicado-github` con el árbol nuevo y el mismo autor anónimo
  (`git commit-tree <arbol> -p publicado-github`), nunca `git push` de `gpu-d3d11`.
- Falta: el Release con `dist\RedDeadRevolverPC.zip` y los enlaces de Google Drive (texturas, videos) en el README.
- **README con imágenes y descargas (2026-11-04):** `docs/img/` (7 capturas del usuario a 1280 en JPG y
  `juego.gif`, 8 s del pueblo con texturas mejoradas, 560 px, 4,6 MB, de su video `Mi video.mp4`). Tabla de
  descargas: Release (`releases/latest`), `RDR-PC-Texturas.zip` y `RDR-PC-Videos.zip` en Google Drive (armados en
  `dist\descargas\`, sin comprimir, con sus carpetas `texturas\` y `videos\` para descomprimir en `Mods-Extras\`).
  Publicado como `f43ff49` (padre `31ae08b`, autor anónimo; etiqueta local `publicado-github`). Verificado en la
  página: las 9 imágenes cargan y los dos enlaces de Drive abren el archivo.

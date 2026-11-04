# Lee un informe de RECOMP_TRACE=prof (rendimiento.txt) por funcion, para los hilos dados.
#   py -3 tools/perfil.py rendimiento.txt modding/perf_build/rdr_recomp.exe 0 40 "<VS>/VC/Tools/Llvm/x64/bin/llvm-symbolizer.exe"
# Hilos: los numeros de las lineas "thread N"; 0 es el hilo principal del juego, nv2a-ack el que dibuja.
import sys, subprocess, collections
rep, exe, slots, top, sym = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(',')], int(sys.argv[4]), sys.argv[5]
mods = {}; rows = []
for line in open(rep, encoding='utf-8', errors='replace'):
    p = line.split()
    if not p: continue
    if p[0] == 'module': mods[int(p[1])] = ' '.join(p[3:]).split(chr(92))[-1]
    elif p[0] == 's' and int(p[1]) in slots: rows.append((mods.get(int(p[2]), '?'), int(p[3], 16), int(p[4])))
offs = sorted({o for m, o, c in rows if m == 'RedDeadRevolver.exe'})
out = subprocess.run([sym, '--obj=' + exe, '--no-inlines'], input='\n'.join('0x%x' % (0x140000000 + o) for o in offs),
                     capture_output=True, text=True).stdout.split('\n')
names = {}
it = iter([l for l in out])
i = 0
lines = [l for l in out if l.strip() != '']
for k, o in enumerate(offs):
    names[o] = lines[2 * k] if 2 * k < len(lines) else '?'
tot = sum(c for _, _, c in rows)
fn = collections.Counter()
for m, o, c in rows: fn[names[o] if m == 'RedDeadRevolver.exe' else '[' + m + ']'] += c
print('total', tot)
for k, v in fn.most_common(top): print('%6.2f%%  %s' % (v * 100 / tot, k))

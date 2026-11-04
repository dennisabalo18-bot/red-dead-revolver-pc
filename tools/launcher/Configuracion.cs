// Configuración.exe: the settings of Red Dead Revolver (PC), outside the game.
//
// Sits next to the game's exe. Shows whether Game\ holds the player's game
// and what Mods-Extras\ brings (improved textures, videos), edits
// rdr_menu.ini (the same file and values as the in-game F2 menu) and starts
// the game. Built by tools\launcher\compilar.bat with the C# compiler that
// comes with Windows (.NET Framework 4), so nothing to install.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

static class Program
{
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();

    [STAThread]
    static void Main()
    {
        try { SetProcessDPIAware(); } catch { }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new Launcher());
    }
}

class Opt
{
    public string Key, Label, Tip, Def;
    public string[] Choices;
    public ComboBox Box;
    public Opt(string key, string label, string def, string tip, params string[] choices)
    { Key = key; Label = label; Def = def; Tip = tip; Choices = choices; }
}

class Launcher : Form
{
    static readonly Color Bg = Color.FromArgb(28, 22, 18);
    static readonly Color Panel = Color.FromArgb(44, 34, 27);
    static readonly Color Paper = Color.FromArgb(232, 214, 178);
    static readonly Color Muted = Color.FromArgb(170, 150, 120);
    static readonly Color Accent = Color.FromArgb(178, 46, 32);
    static readonly Color Ok = Color.FromArgb(120, 190, 100);
    static readonly Color Warn = Color.FromArgb(230, 180, 70);
    static readonly Color Bad = Color.FromArgb(230, 90, 70);

    readonly string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
    string Ini { get { return Path.Combine(root, "rdr_menu.ini"); } }
    string GameDir { get { return Path.Combine(root, "Game"); } }
    string ModsDir { get { return Path.Combine(root, "Mods-Extras"); } }

    readonly List<KeyValuePair<string, Opt[]>> groups = new List<KeyValuePair<string, Opt[]>>();
    readonly ToolTip tips = new ToolTip { AutoPopDelay = 15000, InitialDelay = 300 };
    Label stGame, stTex, stVid, stExe, msg;
    // The settings scroll inside body; the buttons stay in the footer, always visible.
    readonly Panel body = new Panel { Dock = DockStyle.Fill, AutoScroll = true, AutoScrollMargin = new Size(24, 12) };
    readonly Panel footer = new Panel { Dock = DockStyle.Bottom, Height = 94 };

    public Launcher()
    {
        groups.Add(new KeyValuePair<string, Opt[]>("Imagen", new[] {
            new Opt("render_scale", "Resolución interna", "x2 (1280x960)",
                "Cuántos píxeles dibuja el juego. Más alto = más nítido y más exigente.",
                "x1 (640x480)", "x2 (1280x960)", "x3 (1920x1440)", "x4 (2560x1920)"),
            new Opt("widescreen", "Panorámico 16:9", "Sí (nativo del juego)",
                "El modo panorámico propio del juego (más campo de visión a los costados).",
                "No (4:3)", "Sí (nativo del juego)"),
            new Opt("window", "Tamaño de ventana", "1920x1080",
                "Tamaño de la ventana cuando no está en pantalla completa.",
                "Libre", "640x480", "800x600", "960x720", "1024x768", "1280x720", "1280x960", "1366x768",
                "1440x1080", "1600x900", "1600x1200", "1920x1080", "2560x1080", "2560x1440", "3840x2160"),
            new Opt("fullscreen", "Pantalla completa", "Sí", "También se cambia en el juego con F11.", "No", "Sí"),
            new Opt("vsync", "Sincronía vertical (VSync)", "Sí", "Evita el desgarro de la imagen.", "No", "Sí"),
            new Opt("aniso", "Filtrado anisotrópico", "x16", "Texturas del suelo más nítidas a lo lejos.",
                "No", "x2", "x4", "x8", "x16"),
            new Opt("pack_art", "Texturas mejoradas", "Sí",
                "Usa las texturas de Mods-Extras\\texturas. En el juego, F6 las prende y apaga.", "No", "Sí"),
            new Opt("fps", "Mostrar FPS", "Sí", "Los cuadros por segundo en una esquina.", "No", "Sí"),
        }));
        groups.Add(new KeyValuePair<string, Opt[]>("Controles", new[] {
            new Opt("botones", "Botones en pantalla", "Automático",
                "Qué botones muestra el juego. Automático sigue al último mando o teclado que usaste.",
                "Automático", "Teclado y ratón", "Mando Xbox", "Mando PS4/PS5"),
            new Opt("mouse_mode", "Modo del ratón", "Directo (como Black)",
                "Directo: el ratón gira la cámara. Stick emulado: el ratón se comporta como el stick derecho.",
                "Directo (como Black)", "Stick emulado"),
            new Opt("mouse_sens2", "Sensibilidad del ratón", "1", "Velocidad de la cámara con el ratón.",
                "0.25", "0.5", "0.75", "1", "1.25", "1.5", "1.75", "2", "2.5", "3", "3.5", "4", "5", "6", "7",
                "8", "10", "12", "15", "20"),
            new Opt("mouse_sens_y", "Sensibilidad vertical", "100%", "Respecto de la horizontal.",
                "25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%"),
            new Opt("mouse_aim", "Sensibilidad al apuntar", "200%", "Con el clic derecho apretado.",
                "25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%"),
            new Opt("mouse_cap2", "Velocidad máxima de giro", "Sin límite", "Tope de giro en un cuadro.",
                "x1 (como el mando)", "x2", "x4", "x8", "Sin límite"),
            new Opt("mouse_invert_y", "Invertir eje Y", "No", "Mover el ratón hacia arriba mira hacia abajo.", "No", "Sí"),
        }));
        groups.Add(new KeyValuePair<string, Opt[]>("Juego", new[] {
            new Opt("language", "Idioma", "Español", "Idioma de los textos y las voces del juego.",
                "English", "Español", "Français", "Deutsch", "Italiano"),
            new Opt("modo_rapido", "Modo experimental", "No",
                "Activalo en PC de gama baja: el juego y el dibujo trabajan a la vez en vez de esperarse "
                + "(+5-8 fps en un i5 de 4 núcleos). Es experimental: si ves fallas, apagalo.",
                "No", "Sí (PC gama baja)"),
        }));
        Build();
        LoadIni();
        Refresh_();
    }

    // ---------- interface ----------
    void Build()
    {
        Text = "Red Dead Revolver - Configuración";
        BackColor = Bg;
        ForeColor = Paper;
        Font = new Font("Segoe UI", 10f);
        // Resizable: on a screen smaller than the window the settings scroll, the buttons stay.
        FormBorderStyle = FormBorderStyle.Sizable;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;
        Controls.Add(body);      // Fill: added first, so it takes what the footer leaves
        Controls.Add(footer);
        Load += delegate { FitScreen(); };
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

        var title = new Label {
            Text = "RED DEAD REVOLVER", Font = new Font("Georgia", 24f, FontStyle.Bold), ForeColor = Paper,
            AutoSize = true, Location = new Point(24, 16) };
        var sub = new Label {
            Text = "Port de PC  ·  Configuración", Font = new Font("Segoe UI", 10.5f), ForeColor = Muted,
            AutoSize = true, Location = new Point(28, 62) };
        var bar = new Panel { BackColor = Accent, Location = new Point(24, 92), Size = new Size(812, 3) };
        body.Controls.AddRange(new Control[] { title, sub, bar });

        // status
        var st = Box("Estado", 24, 108, 812, 150);
        stGame = Status(st, 0); stTex = Status(st, 1); stVid = Status(st, 2); stExe = Status(st, 3);

        // settings: two columns
        int y = 272, colW = 400;
        var left = Box(groups[0].Key, 24, y, colW, 402);
        AddOpts(left, groups[0].Value);
        var right = Box(groups[1].Key, 24 + colW + 12, y, colW, 296);
        AddOpts(right, groups[1].Value);
        var game = Box(groups[2].Key, 24 + colW + 12, y + 306, colW, 96);
        AddOpts(game, groups[2].Value);

        // buttons, in the footer
        int by = 12;
        var play = Btn("JUGAR", 24, by, 180, 46, true);
        play.Click += delegate { if (Save()) Play(); };
        var save = Btn("Guardar", 216, by, 120, 46, false);
        save.Click += delegate { if (Save()) msg.Text = "Guardado en rdr_menu.ini."; };
        var defs = Btn("Valores por defecto", 348, by, 170, 46, false);
        defs.Click += delegate { Defaults(); msg.Text = "Valores por defecto (todavía sin guardar)."; };
        var fGame = Btn("Abrir Game", 530, by, 145, 46, false);
        fGame.Click += delegate { OpenDir(GameDir); };
        var fMods = Btn("Abrir Mods-Extras", 687, by, 149, 46, false);
        fMods.Click += delegate { OpenDir(ModsDir); };
        msg = new Label { AutoSize = false, Location = new Point(24, by + 54), Size = new Size(812, 24), ForeColor = Muted };
        footer.Controls.AddRange(new Control[] { play, save, defs, fGame, fMods, msg });
        ClientSize = new Size(860, y + 418 + footer.Height);   // same size as before
        MinimumSize = new Size(560, 360);
    }

    // Never bigger than the screen it opens on (the taskbar left out).
    void FitScreen()
    {
        var wa = Screen.FromPoint(Cursor.Position).WorkingArea;
        int w = Math.Min(Width, wa.Width), h = Math.Min(Height, wa.Height);
        if (w == Width && h == Height) return;
        Size = new Size(w, h);
        Location = new Point(wa.Left + (wa.Width - w) / 2, wa.Top + (wa.Height - h) / 2);
    }

    Panel Box(string caption, int x, int y, int w, int h)
    {
        var p = new Panel { BackColor = Panel, Location = new Point(x, y), Size = new Size(w, h) };
        p.Controls.Add(new Label {
            Text = caption.ToUpper(), Font = new Font("Segoe UI", 9f, FontStyle.Bold), ForeColor = Accent,
            AutoSize = true, Location = new Point(12, 8) });
        body.Controls.Add(p);
        return p;
    }

    Label Status(Panel p, int row)
    {
        var l = new Label { AutoSize = false, Location = new Point(14, 34 + row * 27), Size = new Size(p.Width - 28, 25) };
        p.Controls.Add(l);
        return l;
    }

    void AddOpts(Panel p, Opt[] opts)
    {
        int y = 34;
        foreach (var o in opts) {
            var l = new Label { Text = o.Label, AutoSize = false, Location = new Point(12, y + 3), Size = new Size(190, 24) };
            o.Box = new ComboBox {
                DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(204, y), Width = p.Width - 216,
                BackColor = Bg, ForeColor = Paper, FlatStyle = FlatStyle.Flat };
            o.Box.Items.AddRange(o.Choices);
            tips.SetToolTip(l, o.Tip);
            tips.SetToolTip(o.Box, o.Tip);
            p.Controls.Add(l);
            p.Controls.Add(o.Box);
            y += 36;
        }
    }

    Button Btn(string text, int x, int y, int w, int h, bool main)
    {
        var b = new Button {
            Text = text, Location = new Point(x, y), Size = new Size(w, h), FlatStyle = FlatStyle.Flat,
            BackColor = main ? Accent : Panel, ForeColor = Paper,
            Font = new Font("Segoe UI", main ? 12f : 9.5f, main ? FontStyle.Bold : FontStyle.Regular) };
        b.FlatAppearance.BorderColor = main ? Accent : Muted;
        return b;
    }

    // ---------- status ----------
    static void Set(Label l, Color c, string text) { l.ForeColor = c; l.Text = text; }

    // The first `name` in dir or its subfolders (4 levels, as the game looks), or null.
    static string Find(string dir, string name, int depth)
    {
        try {
            var f = Path.Combine(dir, name);
            if (File.Exists(f)) return f;
            if (depth <= 0 || !Directory.Exists(dir)) return null;
            foreach (var d in Directory.GetDirectories(dir)) {
                if (Path.GetFileName(d).Equals("dump", StringComparison.OrdinalIgnoreCase)) continue;
                var r = Find(d, name, depth - 1);
                if (r != null) return r;
            }
        } catch { }
        return null;
    }

    static List<string> FilesIn(string dir, string pattern, int depth)
    {
        var all = new List<string>();
        try {
            if (!Directory.Exists(dir)) return all;
            all.AddRange(Directory.GetFiles(dir, pattern));
            if (depth > 0)
                foreach (var d in Directory.GetDirectories(dir))
                    if (!Path.GetFileName(d).Equals("dump", StringComparison.OrdinalIgnoreCase))
                        all.AddRange(FilesIn(d, pattern, depth - 1));
        } catch { }
        return all;
    }

    string FindGame()
    {
        var x = Find(GameDir, "default.xbe", 4);
        return x == null ? null : Path.GetDirectoryName(x);
    }

    string FindExe()
    {
        foreach (var n in new[] { "RedDeadRevolver.exe", "rdr_recomp.exe" }) {
            var p = Path.Combine(root, n);
            if (File.Exists(p)) return p;
        }
        return null;
    }

    void Refresh_()
    {
        try { Directory.CreateDirectory(GameDir); Directory.CreateDirectory(ModsDir); } catch { }
        var g = FindGame();
        if (g == null)
            Set(stGame, Bad, "✖  Juego: falta. Pegá en la carpeta Game tu copia del juego descomprimida (con default.xbe).");
        else {
            bool dat = File.Exists(Path.Combine(g, "front.dat")) && File.Exists(Path.Combine(g, "swat.dat"));
            Set(stGame, dat ? Ok : Warn, dat ? "✔  Juego encontrado: " + Short(g)
                                            : "⚠  Está default.xbe pero faltan archivos .dat en " + Short(g));
        }
        var pack = Find(ModsDir, "textures.pack", 4);
        if (pack != null)
            Set(stTex, Ok, string.Format("✔  Texturas mejoradas: {0:0.0} GB", new FileInfo(pack).Length / 1073741824.0));
        else
            Set(stTex, Muted, "–  Texturas mejoradas: no hay (opcional: textures.pack en Mods-Extras).");
        int n = FilesIn(ModsDir, "*.mp4", 4).Select(f => Path.GetFileName(f).ToLowerInvariant()).Distinct().Count();
        Set(stVid, n > 0 ? Ok : Muted, n > 0 ? "✔  Videos mejorados: " + n
                                             : "–  Videos mejorados: no hay (opcional: archivos .mp4 en Mods-Extras).");
        var exe = FindExe();
        Set(stExe, exe != null ? Ok : Bad, exe != null ? "✔  Programa: " + Path.GetFileName(exe)
                                                       : "✖  No encuentro RedDeadRevolver.exe junto a este programa.");
    }

    string Short(string p) { return p.StartsWith(root) ? p.Substring(root.Length).TrimStart('\\') : p; }

    // ---------- rdr_menu.ini ----------
    IEnumerable<Opt> All() { return groups.SelectMany(g => g.Value); }

    Dictionary<string, string> ReadIni()
    {
        var d = new Dictionary<string, string>();
        if (!File.Exists(Ini)) return d;
        foreach (var line in File.ReadAllLines(Ini, Encoding.UTF8)) {
            int i = line.IndexOf('=');
            if (i > 0 && !line.StartsWith("#")) d[line.Substring(0, i).Trim()] = line.Substring(i + 1).Trim();
        }
        return d;
    }

    void LoadIni()
    {
        var d = ReadIni();
        foreach (var o in All()) {
            string v;
            int k = d.TryGetValue(o.Key, out v) ? Array.IndexOf(o.Choices, v) : -1;
            o.Box.SelectedIndex = k >= 0 ? k : Array.IndexOf(o.Choices, o.Def);
        }
    }

    void Defaults()
    {
        foreach (var o in All()) o.Box.SelectedIndex = Array.IndexOf(o.Choices, o.Def);
    }

    bool Save()
    {
        try {
            var lines = File.Exists(Ini) ? File.ReadAllLines(Ini, Encoding.UTF8).ToList()
                                         : new List<string> { "# Ajustes del menú F2 (se reescribe solo). Borra el archivo para volver a env.bat." };
            foreach (var o in All()) {
                string val = o.Choices[Math.Max(0, o.Box.SelectedIndex)];
                int at = lines.FindIndex(l => l.StartsWith(o.Key + "="));
                if (at >= 0) lines[at] = o.Key + "=" + val; else lines.Add(o.Key + "=" + val);
            }
            File.WriteAllLines(Ini, lines, new UTF8Encoding(false));
            return true;
        } catch (Exception e) {
            MessageBox.Show(this, "No pude guardar rdr_menu.ini:\n" + e.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
    }

    // ---------- actions ----------
    void Play()
    {
        Refresh_();
        var exe = FindExe();
        if (exe == null) {
            MessageBox.Show(this, "No encuentro RedDeadRevolver.exe en esta carpeta.", Text);
            return;
        }
        if (FindGame() == null) {
            MessageBox.Show(this, "Falta el juego.\n\nCopiá tu carpeta de Red Dead Revolver (la que tiene default.xbe, " +
                "front.dat, swat.dat...) dentro de la carpeta Game y volvé a intentar.", Text,
                MessageBoxButtons.OK, MessageBoxIcon.Information);
            OpenDir(GameDir);
            return;
        }
        try {
            Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = root, UseShellExecute = false });
            Close();
        } catch (Exception e) {
            MessageBox.Show(this, "No pude abrir el juego:\n" + e.Message, Text);
        }
    }

    void OpenDir(string d)
    {
        try { Directory.CreateDirectory(d); Process.Start("explorer.exe", "\"" + d + "\""); } catch { }
    }

    protected override void OnActivated(EventArgs e) { base.OnActivated(e); if (stGame != null) Refresh_(); }
}

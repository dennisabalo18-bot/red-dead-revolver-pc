// Configuración.exe: the settings of Red Dead Revolver (PC), outside the game.
//
// Sits next to the game's exe. Shows whether Game\ holds the player's game
// and what Mods-Extras\ brings (improved textures, videos), edits
// rdr_menu.ini (the same file and values as the in-game F2 menu) and starts
// the game. Built by tools\launcher\compilar.ps1 with the C# compiler that
// comes with Windows (.NET Framework 4, C# 5), so nothing to install.
//
// The window speaks Spanish, English, Portuguese, French, German and Italian
// (the selector at the top right; launcher.ini remembers it, the first time
// it follows Windows). rdr_menu.ini keeps the F2 menu's own values (Spanish):
// only what is shown is translated.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
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
    public string Key, Def;          // Def: one of Choices, as rdr_menu.ini writes it
    public string[] Choices;         // as rdr_menu.ini (and the F2 menu) writes them
    public ComboBox Box;
    public Opt(string key, string def, params string[] choices)
    { Key = key; Def = def; Choices = choices; }
}

// ---------- texts: es, en, pt, fr, de, it ----------
static class Tr
{
    public static readonly string[] Codes = { "es", "en", "pt", "fr", "de", "it" };
    public static readonly string[] Names = { "Español", "English", "Português", "Français", "Deutsch", "Italiano" };
    public static int Lang;          // index into Codes

    static readonly Dictionary<string, string[]> T = new Dictionary<string, string[]> {
        { "title", new[] { "Red Dead Revolver - Configuración", "Red Dead Revolver - Settings",
            "Red Dead Revolver - Configurações", "Red Dead Revolver - Paramètres",
            "Red Dead Revolver - Einstellungen", "Red Dead Revolver - Impostazioni" } },
        { "subtitle", new[] { "Port de PC  ·  Configuración", "PC port  ·  Settings", "Port para PC  ·  Configurações",
            "Portage PC  ·  Paramètres", "PC-Portierung  ·  Einstellungen", "Port per PC  ·  Impostazioni" } },
        { "lang", new[] { "Idioma:", "Language:", "Idioma:", "Langue :", "Sprache:", "Lingua:" } },
        { "g_status", new[] { "Estado", "Status", "Status", "État", "Status", "Stato" } },
        { "g_image", new[] { "Imagen", "Graphics", "Imagem", "Image", "Grafik", "Grafica" } },
        { "g_controls", new[] { "Controles", "Controls", "Controles", "Commandes", "Steuerung", "Controlli" } },
        { "g_game", new[] { "Juego", "Game", "Jogo", "Jeu", "Spiel", "Gioco" } },

        { "render_scale", new[] { "Resolución interna", "Internal resolution", "Resolução interna",
            "Résolution interne", "Interne Auflösung", "Risoluzione interna" } },
        { "render_scale.tip", new[] {
            "Cuántos píxeles dibuja el juego. Más alto = más nítido y más exigente.",
            "How many pixels the game draws. Higher = sharper and more demanding.",
            "Quantos pixels o jogo desenha. Mais alto = mais nítido e mais exigente.",
            "Nombre de pixels que le jeu dessine. Plus haut = plus net et plus exigeant.",
            "Wie viele Pixel das Spiel zeichnet. Höher = schärfer und anspruchsvoller.",
            "Quanti pixel disegna il gioco. Più alto = più nitido e più pesante." } },
        { "widescreen", new[] { "Panorámico 16:9", "Widescreen 16:9", "Widescreen 16:9",
            "Écran large 16:9", "Breitbild 16:9", "Widescreen 16:9" } },
        { "widescreen.tip", new[] {
            "El modo panorámico propio del juego (más campo de visión a los costados).",
            "The game's own widescreen mode (wider field of view at the sides).",
            "O modo widescreen do próprio jogo (mais campo de visão nas laterais).",
            "Le mode écran large du jeu (champ de vision élargi sur les côtés).",
            "Der eigene Breitbildmodus des Spiels (mehr Sichtfeld an den Seiten).",
            "La modalità widescreen del gioco (più campo visivo ai lati)." } },
        { "window", new[] { "Tamaño de ventana", "Window size", "Tamanho da janela",
            "Taille de la fenêtre", "Fenstergröße", "Dimensione finestra" } },
        { "window.tip", new[] {
            "Tamaño de la ventana cuando no está en pantalla completa.",
            "Window size when not in fullscreen.",
            "Tamanho da janela fora da tela cheia.",
            "Taille de la fenêtre hors du plein écran.",
            "Fenstergröße außerhalb des Vollbilds.",
            "Dimensione della finestra fuori dallo schermo intero." } },
        { "fullscreen", new[] { "Pantalla completa", "Fullscreen", "Tela cheia", "Plein écran", "Vollbild", "Schermo intero" } },
        { "fullscreen.tip", new[] {
            "También se cambia en el juego con F11.", "Can also be toggled in game with F11.",
            "Também muda no jogo com F11.", "Se change aussi en jeu avec F11.",
            "Lässt sich im Spiel auch mit F11 umschalten.", "Si cambia anche nel gioco con F11." } },
        { "vsync", new[] { "Sincronía vertical (VSync)", "Vertical sync (VSync)", "Sincronia vertical (VSync)",
            "Synchro verticale (VSync)", "Vertikale Synchr. (VSync)", "Sincronia verticale (VSync)" } },
        { "vsync.tip", new[] {
            "Evita el desgarro de la imagen.", "Prevents screen tearing.", "Evita que a imagem se rasgue.",
            "Évite le déchirement de l'image.", "Verhindert Bildreißen (Tearing).", "Evita lo strappo dell'immagine (tearing)." } },
        { "aniso", new[] { "Filtrado anisotrópico", "Anisotropic filtering", "Filtragem anisotrópica",
            "Filtrage anisotrope", "Anisotrope Filterung", "Filtro anisotropico" } },
        { "aniso.tip", new[] {
            "Texturas del suelo más nítidas a lo lejos.", "Sharper ground textures in the distance.",
            "Texturas do chão mais nítidas à distância.", "Textures du sol plus nettes au loin.",
            "Schärfere Bodentexturen in der Ferne.", "Texture del terreno più nitide in lontananza." } },
        { "pack_art", new[] { "Texturas mejoradas", "Improved textures", "Texturas melhoradas",
            "Textures améliorées", "Verbesserte Texturen", "Texture migliorate" } },
        { "pack_art.tip", new[] {
            "Usa las texturas de Mods-Extras\\texturas. En el juego, F6 las prende y apaga.",
            "Uses the textures in Mods-Extras\\texturas. In game, F6 turns them on and off.",
            "Usa as texturas de Mods-Extras\\texturas. No jogo, F6 liga e desliga.",
            "Utilise les textures de Mods-Extras\\texturas. En jeu, F6 les active ou les désactive.",
            "Nutzt die Texturen aus Mods-Extras\\texturas. Im Spiel schaltet F6 sie ein und aus.",
            "Usa le texture di Mods-Extras\\texturas. Nel gioco, F6 le attiva e disattiva." } },
        { "fps", new[] { "Mostrar FPS", "Show FPS", "Mostrar FPS", "Afficher les FPS", "FPS anzeigen", "Mostra FPS" } },
        { "fps.tip", new[] {
            "Los cuadros por segundo en una esquina.", "Frames per second in a corner.",
            "Os quadros por segundo num canto.", "Les images par seconde dans un coin.",
            "Bilder pro Sekunde in einer Ecke.", "I fotogrammi al secondo in un angolo." } },

        { "botones", new[] { "Botones en pantalla", "On-screen buttons", "Botões na tela",
            "Boutons à l'écran", "Tasten am Bildschirm", "Pulsanti a schermo" } },
        { "botones.tip", new[] {
            "Qué botones muestra el juego. Automático sigue al último mando o teclado que usaste.",
            "Which buttons the game shows. Automatic follows the last controller or keyboard you used.",
            "Quais botões o jogo mostra. Automático segue o último controle ou teclado que você usou.",
            "Les boutons affichés par le jeu. Automatique suit la dernière manette ou le clavier utilisé.",
            "Welche Tasten das Spiel zeigt. Automatisch folgt dem zuletzt benutzten Controller oder der Tastatur.",
            "Quali pulsanti mostra il gioco. Automatico segue l'ultimo controller o la tastiera che hai usato." } },
        { "mouse_mode", new[] { "Modo del ratón", "Mouse mode", "Modo do mouse", "Mode de la souris", "Mausmodus", "Modalità mouse" } },
        { "mouse_mode.tip", new[] {
            "Directo: el ratón gira la cámara. Stick emulado: el ratón se comporta como el stick derecho.",
            "Direct: the mouse turns the camera. Emulated stick: the mouse acts like the right stick.",
            "Direto: o mouse gira a câmera. Analógico emulado: o mouse age como o analógico direito.",
            "Direct : la souris tourne la caméra. Stick émulé : la souris se comporte comme le stick droit.",
            "Direkt: Die Maus dreht die Kamera. Emulierter Stick: Die Maus verhält sich wie der rechte Stick.",
            "Diretto: il mouse gira la telecamera. Levetta emulata: il mouse si comporta come la levetta destra." } },
        { "mouse_sens2", new[] { "Sensibilidad del ratón", "Mouse sensitivity", "Sensibilidade do mouse",
            "Sensibilité de la souris", "Mausempfindlichkeit", "Sensibilità del mouse" } },
        { "mouse_sens2.tip", new[] {
            "Velocidad de la cámara con el ratón.", "Camera speed with the mouse.", "Velocidade da câmera com o mouse.",
            "Vitesse de la caméra à la souris.", "Kamerageschwindigkeit mit der Maus.", "Velocità della telecamera con il mouse." } },
        { "mouse_sens_y", new[] { "Sensibilidad vertical", "Vertical sensitivity", "Sensibilidade vertical",
            "Sensibilité verticale", "Vertikale Empfindlichkeit", "Sensibilità verticale" } },
        { "mouse_sens_y.tip", new[] {
            "Respecto de la horizontal.", "Relative to the horizontal one.", "Em relação à horizontal.",
            "Par rapport à l'horizontale.", "Im Verhältnis zur horizontalen.", "Rispetto a quella orizzontale." } },
        { "mouse_aim", new[] { "Sensibilidad al apuntar", "Aiming sensitivity", "Sensibilidade ao mirar",
            "Sensibilité en visée", "Empfindlichkeit (Zielen)", "Sensibilità in mira" } },
        { "mouse_aim.tip", new[] {
            "Con el clic derecho apretado.", "While holding the right mouse button.", "Com o botão direito pressionado.",
            "Clic droit maintenu.", "Bei gedrückter rechter Maustaste.", "Con il tasto destro premuto." } },
        { "mouse_cap2", new[] { "Velocidad máxima de giro", "Max turn speed", "Velocidade máxima de giro",
            "Vitesse de rotation max.", "Max. Drehgeschwindigkeit", "Velocità max di rotazione" } },
        { "mouse_cap2.tip", new[] {
            "Tope de giro en un cuadro.", "Turn limit per frame.", "Limite de giro por quadro.",
            "Limite de rotation par image.", "Drehgrenze pro Bild.", "Limite di rotazione per fotogramma." } },
        { "mouse_invert_y", new[] { "Invertir eje Y", "Invert Y axis", "Inverter eixo Y",
            "Inverser l'axe Y", "Y-Achse umkehren", "Inverti asse Y" } },
        { "mouse_invert_y.tip", new[] {
            "Mover el ratón hacia arriba mira hacia abajo.", "Moving the mouse up looks down.",
            "Mover o mouse para cima olha para baixo.", "Monter la souris fait regarder vers le bas.",
            "Maus nach oben bewegen schaut nach unten.", "Muovere il mouse in alto guarda in basso." } },

        { "language", new[] { "Idioma del juego", "Game language", "Idioma do jogo",
            "Langue du jeu", "Spielsprache", "Lingua del gioco" } },
        { "language.tip", new[] {
            "Idioma de los textos y las voces del juego.",
            "Language of the game's text and voices.",
            "Idioma dos textos e das vozes do jogo (o jogo não tem português).",
            "Langue des textes et des voix du jeu.",
            "Sprache der Texte und Stimmen des Spiels.",
            "Lingua dei testi e delle voci del gioco." } },
        { "modo_rapido", new[] { "Modo experimental", "Experimental mode", "Modo experimental",
            "Mode expérimental", "Experimenteller Modus", "Modalità sperimentale" } },
        { "modo_rapido.tip", new[] {
            "Activalo en PC de gama baja: el juego y el dibujo trabajan a la vez en vez de esperarse "
            + "(+5-8 fps en un i5 de 4 núcleos). Es experimental: si ves fallas, apagalo.",
            "Turn it on for low-end PCs: the game and the renderer work at the same time instead of waiting "
            + "for each other (+5-8 fps on a 4-core i5). Experimental: if you see glitches, turn it off.",
            "Ative em PCs mais fracos: o jogo e o desenho trabalham ao mesmo tempo em vez de esperar um pelo "
            + "outro (+5-8 fps num i5 de 4 núcleos). É experimental: se notar falhas, desative.",
            "À activer sur les PC modestes : le jeu et le rendu travaillent en même temps au lieu de s'attendre "
            + "(+5-8 fps sur un i5 4 cœurs). Expérimental : en cas de problèmes, désactivez-le.",
            "Für schwache PCs: Spiel und Grafik arbeiten gleichzeitig, statt aufeinander zu warten "
            + "(+5-8 fps auf einem i5 mit 4 Kernen). Experimentell: Bei Fehlern ausschalten.",
            "Attivala sui PC meno potenti: il gioco e il disegno lavorano insieme invece di aspettarsi "
            + "(+5-8 fps su un i5 a 4 core). È sperimentale: se vedi problemi, disattivala." } },

        { "play", new[] { "JUGAR", "PLAY", "JOGAR", "JOUER", "SPIELEN", "GIOCA" } },
        { "save", new[] { "Guardar", "Save", "Salvar", "Enregistrer", "Speichern", "Salva" } },
        { "defaults", new[] { "Valores por defecto", "Defaults", "Padrões", "Par défaut", "Standardwerte", "Predefiniti" } },
        { "open_game", new[] { "Abrir Game", "Open Game", "Abrir Game", "Ouvrir Game", "Game öffnen", "Apri Game" } },
        { "open_mods", new[] { "Abrir Mods-Extras", "Open Mods-Extras", "Abrir Mods-Extras",
            "Ouvrir Mods-Extras", "Mods-Extras öffnen", "Apri Mods-Extras" } },
        { "saved", new[] { "Guardado en rdr_menu.ini.", "Saved to rdr_menu.ini.", "Salvo em rdr_menu.ini.",
            "Enregistré dans rdr_menu.ini.", "In rdr_menu.ini gespeichert.", "Salvato in rdr_menu.ini." } },
        { "defaults_msg", new[] { "Valores por defecto (todavía sin guardar).", "Default values (not saved yet).",
            "Valores padrão (ainda não salvos).", "Valeurs par défaut (pas encore enregistrées).",
            "Standardwerte (noch nicht gespeichert).", "Valori predefiniti (non ancora salvati)." } },

        { "st_game_missing", new[] {
            "✖  Juego: falta. Pegá en la carpeta Game tu copia del juego descomprimida (con default.xbe).",
            "✖  Game: missing. Put your extracted copy of the game (with default.xbe) in the Game folder.",
            "✖  Jogo: falta. Coloque na pasta Game sua cópia do jogo descompactada (com default.xbe).",
            "✖  Jeu : manquant. Placez votre copie décompressée du jeu (avec default.xbe) dans le dossier Game.",
            "✖  Spiel: fehlt. Lege deine entpackte Kopie des Spiels (mit default.xbe) in den Ordner Game.",
            "✖  Gioco: manca. Metti nella cartella Game la tua copia del gioco estratta (con default.xbe)." } },
        { "st_game_ok", new[] { "✔  Juego encontrado: {0}", "✔  Game found: {0}", "✔  Jogo encontrado: {0}",
            "✔  Jeu trouvé : {0}", "✔  Spiel gefunden: {0}", "✔  Gioco trovato: {0}" } },
        { "st_game_dat", new[] {
            "⚠  Está default.xbe pero faltan archivos .dat en {0}",
            "⚠  default.xbe is there but .dat files are missing in {0}",
            "⚠  O default.xbe está lá, mas faltam arquivos .dat em {0}",
            "⚠  default.xbe est présent mais il manque des fichiers .dat dans {0}",
            "⚠  default.xbe ist da, aber in {0} fehlen .dat-Dateien",
            "⚠  C'è default.xbe ma mancano file .dat in {0}" } },
        { "st_game_ver", new[] {
            "✖  Tu juego es otra versión (default.xbe de {0} bytes). Este port solo funciona con la versión PAL (Europa).",
            "✖  Your game is a different version (default.xbe, {0} bytes). This port only works with the PAL (Europe) version.",
            "✖  Seu jogo é outra versão (default.xbe de {0} bytes). Este port só funciona com a versão PAL (Europa).",
            "✖  Votre jeu est une autre version (default.xbe, {0} octets). Ce portage ne marche qu'avec la version PAL (Europe).",
            "✖  Dein Spiel ist eine andere Version (default.xbe, {0} Bytes). Nur die PAL-Version (Europa) wird unterstützt.",
            "✖  Il tuo gioco è un'altra versione (default.xbe di {0} byte). Questo port funziona solo con la versione PAL (Europa)." } },
        { "st_tex_ok", new[] { "✔  Texturas mejoradas: {0:0.0} GB", "✔  Improved textures: {0:0.0} GB",
            "✔  Texturas melhoradas: {0:0.0} GB", "✔  Textures améliorées : {0:0.0} Go",
            "✔  Verbesserte Texturen: {0:0.0} GB", "✔  Texture migliorate: {0:0.0} GB" } },
        { "st_tex_no", new[] {
            "–  Texturas mejoradas: no hay (opcional: textures.pack en Mods-Extras).",
            "–  Improved textures: none (optional: textures.pack in Mods-Extras).",
            "–  Texturas melhoradas: nenhuma (opcional: textures.pack em Mods-Extras).",
            "–  Textures améliorées : aucune (facultatif : textures.pack dans Mods-Extras).",
            "–  Verbesserte Texturen: keine (optional: textures.pack in Mods-Extras).",
            "–  Texture migliorate: nessuna (opzionale: textures.pack in Mods-Extras)." } },
        { "st_vid_ok", new[] { "✔  Videos mejorados: {0}", "✔  Improved videos: {0}", "✔  Vídeos melhorados: {0}",
            "✔  Vidéos améliorées : {0}", "✔  Verbesserte Videos: {0}", "✔  Video migliorati: {0}" } },
        { "st_vid_no", new[] {
            "–  Videos mejorados: no hay (opcional: archivos .mp4 en Mods-Extras).",
            "–  Improved videos: none (optional: .mp4 files in Mods-Extras).",
            "–  Vídeos melhorados: nenhum (opcional: arquivos .mp4 em Mods-Extras).",
            "–  Vidéos améliorées : aucune (facultatif : fichiers .mp4 dans Mods-Extras).",
            "–  Verbesserte Videos: keine (optional: .mp4-Dateien in Mods-Extras).",
            "–  Video migliorati: nessuno (opzionale: file .mp4 in Mods-Extras)." } },
        { "st_exe_ok", new[] { "✔  Programa: {0}", "✔  Program: {0}", "✔  Programa: {0}",
            "✔  Programme : {0}", "✔  Programm: {0}", "✔  Programma: {0}" } },
        { "st_exe_no", new[] {
            "✖  No encuentro RedDeadRevolver.exe junto a este programa.",
            "✖  RedDeadRevolver.exe not found next to this program.",
            "✖  RedDeadRevolver.exe não encontrado junto a este programa.",
            "✖  RedDeadRevolver.exe introuvable à côté de ce programme.",
            "✖  RedDeadRevolver.exe wurde neben diesem Programm nicht gefunden.",
            "✖  RedDeadRevolver.exe non trovato accanto a questo programma." } },
        { "err_save", new[] { "No pude guardar rdr_menu.ini:\n", "Could not save rdr_menu.ini:\n",
            "Não foi possível salvar rdr_menu.ini:\n", "Impossible d'enregistrer rdr_menu.ini :\n",
            "rdr_menu.ini konnte nicht gespeichert werden:\n", "Impossibile salvare rdr_menu.ini:\n" } },
        { "err_noexe", new[] { "No encuentro RedDeadRevolver.exe en esta carpeta.", "RedDeadRevolver.exe is not in this folder.",
            "RedDeadRevolver.exe não está nesta pasta.", "RedDeadRevolver.exe est introuvable dans ce dossier.",
            "RedDeadRevolver.exe ist nicht in diesem Ordner.", "RedDeadRevolver.exe non è in questa cartella." } },
        { "err_nogame", new[] {
            "Falta el juego.\n\nCopiá tu carpeta de Red Dead Revolver (la que tiene default.xbe, front.dat, swat.dat...) "
            + "dentro de la carpeta Game y volvé a intentar.",
            "The game is missing.\n\nCopy your Red Dead Revolver folder (the one with default.xbe, front.dat, swat.dat...) "
            + "into the Game folder and try again.",
            "Falta o jogo.\n\nCopie sua pasta do Red Dead Revolver (a que tem default.xbe, front.dat, swat.dat...) "
            + "para dentro da pasta Game e tente de novo.",
            "Le jeu est manquant.\n\nCopiez votre dossier Red Dead Revolver (celui avec default.xbe, front.dat, swat.dat...) "
            + "dans le dossier Game et réessayez.",
            "Das Spiel fehlt.\n\nKopiere deinen Red-Dead-Revolver-Ordner (mit default.xbe, front.dat, swat.dat...) "
            + "in den Ordner Game und versuche es erneut.",
            "Manca il gioco.\n\nCopia la tua cartella di Red Dead Revolver (quella con default.xbe, front.dat, swat.dat...) "
            + "nella cartella Game e riprova." } },
        { "err_run", new[] { "No pude abrir el juego:\n", "Could not start the game:\n", "Não foi possível abrir o jogo:\n",
            "Impossible de lancer le jeu :\n", "Das Spiel konnte nicht gestartet werden:\n", "Impossibile avviare il gioco:\n" } },
    };

    // The shown text of a value rdr_menu.ini stores in Spanish (numbers, sizes
    // and language names are the same in every language).
    static readonly Dictionary<string, string[]> V = new Dictionary<string, string[]> {
        { "Sí", new[] { "Sí", "Yes", "Sim", "Oui", "Ja", "Sì" } },
        { "No", new[] { "No", "No", "Não", "Non", "Nein", "No" } },
        { "Libre", new[] { "Libre", "Free", "Livre", "Libre", "Frei", "Libera" } },
        { "Sin límite", new[] { "Sin límite", "Unlimited", "Sem limite", "Illimitée", "Unbegrenzt", "Illimitata" } },
        { "Automático", new[] { "Automático", "Automatic", "Automático", "Automatique", "Automatisch", "Automatico" } },
        { "Teclado y ratón", new[] { "Teclado y ratón", "Keyboard and mouse", "Teclado e mouse",
            "Clavier et souris", "Tastatur und Maus", "Tastiera e mouse" } },
        { "Mando Xbox", new[] { "Mando Xbox", "Xbox controller", "Controle Xbox", "Manette Xbox", "Xbox-Controller", "Controller Xbox" } },
        { "Mando PS4/PS5", new[] { "Mando PS4/PS5", "PS4/PS5 controller", "Controle PS4/PS5", "Manette PS4/PS5",
            "PS4/PS5-Controller", "Controller PS4/PS5" } },
        { "Directo (como Black)", new[] { "Directo (como Black)", "Direct (like Black)", "Direto (como Black)",
            "Direct (comme Black)", "Direkt (wie Black)", "Diretto (come Black)" } },
        { "Stick emulado", new[] { "Stick emulado", "Emulated stick", "Analógico emulado", "Stick émulé",
            "Emulierter Stick", "Levetta emulata" } },
        { "x1 (como el mando)", new[] { "x1 (como el mando)", "x1 (like a controller)", "x1 (como o controle)",
            "x1 (comme la manette)", "x1 (wie Controller)", "x1 (come il controller)" } },
        { "No (4:3)", new[] { "No (4:3)", "No (4:3)", "Não (4:3)", "Non (4:3)", "Nein (4:3)", "No (4:3)" } },
        { "Sí (nativo del juego)", new[] { "Sí (nativo del juego)", "Yes (game's own)", "Sim (nativo do jogo)",
            "Oui (natif du jeu)", "Ja (spieleigen)", "Sì (nativo del gioco)" } },
        { "Sí (PC gama baja)", new[] { "Sí (PC gama baja)", "Yes (low-end PC)", "Sim (PC mais fraco)",
            "Oui (PC modeste)", "Ja (schwacher PC)", "Sì (PC poco potente)" } },
    };

    public static string S(string id)
    {
        string[] t;
        return T.TryGetValue(id, out t) ? t[Lang] : id;
    }

    public static string Value(string stored)
    {
        string[] t;
        return V.TryGetValue(stored, out t) ? t[Lang] : stored;
    }
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
    const long PalXbeSize = 4452352;     // the only default.xbe the port runs (RedDeadRevolver.exe checks it too)

    readonly string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
    string Ini { get { return Path.Combine(root, "rdr_menu.ini"); } }
    string LangIni { get { return Path.Combine(root, "launcher.ini"); } }
    string GameDir { get { return Path.Combine(root, "Game"); } }
    string ModsDir { get { return Path.Combine(root, "Mods-Extras"); } }

    // (group text id, options)
    readonly List<KeyValuePair<string, Opt[]>> groups = new List<KeyValuePair<string, Opt[]>>();
    readonly ToolTip tips = new ToolTip { AutoPopDelay = 15000, InitialDelay = 300 };
    Label stGame, stTex, stVid, stExe, msg;
    // The settings scroll inside body; the buttons stay in the footer, always visible.
    readonly Panel body = new Panel { Dock = DockStyle.Fill, AutoScroll = true, AutoScrollMargin = new Size(24, 12) };
    readonly Panel footer = new Panel { Dock = DockStyle.Bottom, Height = 94 };

    public Launcher()
    {
        groups.Add(new KeyValuePair<string, Opt[]>("g_image", new[] {
            new Opt("render_scale", "x2 (1280x960)", "x1 (640x480)", "x2 (1280x960)", "x3 (1920x1440)", "x4 (2560x1920)"),
            new Opt("widescreen", "Sí (nativo del juego)", "No (4:3)", "Sí (nativo del juego)"),
            new Opt("window", "1920x1080",
                "Libre", "640x480", "800x600", "960x720", "1024x768", "1280x720", "1280x960", "1366x768",
                "1440x1080", "1600x900", "1600x1200", "1920x1080", "2560x1080", "2560x1440", "3840x2160"),
            new Opt("fullscreen", "Sí", "No", "Sí"),
            new Opt("vsync", "Sí", "No", "Sí"),
            new Opt("aniso", "x16", "No", "x2", "x4", "x8", "x16"),
            new Opt("pack_art", "Sí", "No", "Sí"),
            new Opt("fps", "Sí", "No", "Sí"),
        }));
        groups.Add(new KeyValuePair<string, Opt[]>("g_controls", new[] {
            new Opt("botones", "Automático", "Automático", "Teclado y ratón", "Mando Xbox", "Mando PS4/PS5"),
            new Opt("mouse_mode", "Directo (como Black)", "Directo (como Black)", "Stick emulado"),
            new Opt("mouse_sens2", "1",
                "0.25", "0.5", "0.75", "1", "1.25", "1.5", "1.75", "2", "2.5", "3", "3.5", "4", "5", "6", "7",
                "8", "10", "12", "15", "20"),
            new Opt("mouse_sens_y", "100%", "25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%"),
            new Opt("mouse_aim", "200%", "25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%"),
            new Opt("mouse_cap2", "Sin límite", "x1 (como el mando)", "x2", "x4", "x8", "Sin límite"),
            new Opt("mouse_invert_y", "No", "No", "Sí"),
        }));
        groups.Add(new KeyValuePair<string, Opt[]>("g_game", new[] {
            new Opt("language", "Español", "English", "Español", "Français", "Deutsch", "Italiano"),
            new Opt("modo_rapido", "No", "No", "Sí (PC gama baja)"),
        }));
        Tr.Lang = LoadLang();
        Setup();
        BuildContent();
        LoadIni();
        Refresh_();
    }

    // ---------- launcher language ----------
    int LoadLang()
    {
        try {
            if (File.Exists(LangIni))
                foreach (var line in File.ReadAllLines(LangIni, Encoding.UTF8))
                    if (line.StartsWith("idioma=")) {
                        int i = Array.IndexOf(Tr.Codes, line.Substring(7).Trim());
                        if (i >= 0) return i;
                    }
        } catch { }
        int w = Array.IndexOf(Tr.Codes, CultureInfo.CurrentUICulture.TwoLetterISOLanguageName);
        return w >= 0 ? w : 1;               // English for any other Windows language
    }

    void SaveLang()
    {
        try { File.WriteAllText(LangIni, "idioma=" + Tr.Codes[Tr.Lang] + "\r\n", new UTF8Encoding(false)); } catch { }
    }

    // The game's language the defaults pick: the launcher's, or Spanish for Portuguese.
    string GameLangDefault()
    {
        string[] byLauncher = { "Español", "English", "Español", "Français", "Deutsch", "Italiano" };
        return byLauncher[Tr.Lang];
    }

    string DefOf(Opt o) { return o.Key == "language" ? GameLangDefault() : o.Def; }

    // ---------- interface ----------
    void Setup()
    {
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
    }

    // Every control with text, in the current language. Called again when the
    // language changes, keeping what is chosen in each list.
    void BuildContent()
    {
        var keep = new Dictionary<string, int>();
        foreach (var o in All())
            if (o.Box != null) keep[o.Key] = o.Box.SelectedIndex;
        int scroll = body.VerticalScroll.Value;
        body.SuspendLayout();
        footer.SuspendLayout();
        tips.RemoveAll();
        body.Controls.Clear();
        footer.Controls.Clear();
        body.AutoScrollPosition = new Point(0, 0);

        Text = Tr.S("title");
        var title = new Label {
            Text = "RED DEAD REVOLVER", Font = new Font("Georgia", 24f, FontStyle.Bold), ForeColor = Paper,
            AutoSize = true, Location = new Point(24, 16) };
        var sub = new Label {
            Text = Tr.S("subtitle"), Font = new Font("Segoe UI", 10.5f), ForeColor = Muted,
            AutoSize = true, Location = new Point(28, 62) };
        var bar = new Panel { BackColor = Accent, Location = new Point(24, 92), Size = new Size(812, 3) };
        // the launcher's language, top right
        var langBox = new ComboBox {
            DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(686, 56), Width = 150,
            BackColor = Bg, ForeColor = Paper, FlatStyle = FlatStyle.Flat };
        langBox.Items.AddRange(Tr.Names);
        langBox.SelectedIndex = Tr.Lang;
        var langLbl = new Label {
            Text = Tr.S("lang"), ForeColor = Muted, AutoSize = false, TextAlign = ContentAlignment.MiddleRight,
            Location = new Point(560, 58), Size = new Size(122, 24) };
        langBox.SelectedIndexChanged += delegate {
            if (langBox.SelectedIndex < 0 || langBox.SelectedIndex == Tr.Lang) return;
            Tr.Lang = langBox.SelectedIndex;
            SaveLang();
            BeginInvoke((MethodInvoker)delegate { BuildContent(); Refresh_(); });
        };
        body.Controls.AddRange(new Control[] { title, sub, bar, langLbl, langBox });

        // status
        var st = Box(Tr.S("g_status"), 24, 108, 812, 150);
        stGame = Status(st, 0); stTex = Status(st, 1); stVid = Status(st, 2); stExe = Status(st, 3);

        // settings: two columns
        int y = 272, colW = 400;
        var left = Box(Tr.S(groups[0].Key), 24, y, colW, 402);
        AddOpts(left, groups[0].Value);
        var right = Box(Tr.S(groups[1].Key), 24 + colW + 12, y, colW, 296);
        AddOpts(right, groups[1].Value);
        var game = Box(Tr.S(groups[2].Key), 24 + colW + 12, y + 306, colW, 96);
        AddOpts(game, groups[2].Value);

        // buttons, in the footer
        int by = 12;
        var play = Btn(Tr.S("play"), 24, by, 180, 46, true);
        play.Click += delegate { if (Save()) Play(); };
        var save = Btn(Tr.S("save"), 216, by, 120, 46, false);
        save.Click += delegate { if (Save()) msg.Text = Tr.S("saved"); };
        var defs = Btn(Tr.S("defaults"), 348, by, 170, 46, false);
        defs.Click += delegate { Defaults(); msg.Text = Tr.S("defaults_msg"); };
        var fGame = Btn(Tr.S("open_game"), 530, by, 145, 46, false);
        fGame.Click += delegate { OpenDir(GameDir); };
        var fMods = Btn(Tr.S("open_mods"), 687, by, 149, 46, false);
        fMods.Click += delegate { OpenDir(ModsDir); };
        msg = new Label { AutoSize = false, Location = new Point(24, by + 54), Size = new Size(812, 24), ForeColor = Muted };
        footer.Controls.AddRange(new Control[] { play, save, defs, fGame, fMods, msg });

        foreach (var o in All()) {
            int k;
            if (keep.TryGetValue(o.Key, out k) && k >= 0) o.Box.SelectedIndex = k;
        }
        body.ResumeLayout();
        footer.ResumeLayout();
        if (keep.Count > 0)
            body.AutoScrollPosition = new Point(0, scroll);
        else {
            ClientSize = new Size(860, y + 418 + footer.Height);   // same size as before
            MinimumSize = new Size(560, 360);
        }
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
        var l = new Label { AutoSize = false, AutoEllipsis = true,
                            Location = new Point(14, 34 + row * 27), Size = new Size(p.Width - 28, 25) };
        p.Controls.Add(l);
        return l;
    }

    void AddOpts(Panel p, Opt[] opts)
    {
        int y = 34;
        foreach (var o in opts) {
            var l = new Label { Text = Tr.S(o.Key), AutoSize = false, AutoEllipsis = true,
                                Location = new Point(12, y + 3), Size = new Size(190, 24) };
            o.Box = new ComboBox {
                DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(204, y), Width = p.Width - 216,
                BackColor = Bg, ForeColor = Paper, FlatStyle = FlatStyle.Flat };
            o.Box.Items.AddRange(o.Choices.Select(c => (object)Tr.Value(c)).ToArray());
            string tip = Tr.S(o.Key) + "\n" + Tr.S(o.Key + ".tip");
            tips.SetToolTip(l, tip);
            tips.SetToolTip(o.Box, tip);
            p.Controls.Add(l);
            p.Controls.Add(o.Box);
            y += 36;
        }
    }

    Button Btn(string text, int x, int y, int w, int h, bool main)
    {
        var b = new Button {
            Text = text, Location = new Point(x, y), Size = new Size(w, h), FlatStyle = FlatStyle.Flat,
            BackColor = main ? Accent : Panel, ForeColor = Paper, AutoEllipsis = true,
            Font = new Font("Segoe UI", main ? 12f : 9.5f, main ? FontStyle.Bold : FontStyle.Regular) };
        b.FlatAppearance.BorderColor = main ? Accent : Muted;
        return b;
    }

    // ---------- status ----------
    void Set(Label l, Color c, string text) { l.ForeColor = c; l.Text = text; tips.SetToolTip(l, text); }

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
            Set(stGame, Bad, Tr.S("st_game_missing"));
        else {
            long size = 0;
            try { size = new FileInfo(Path.Combine(g, "default.xbe")).Length; } catch { }
            bool dat = File.Exists(Path.Combine(g, "front.dat")) && File.Exists(Path.Combine(g, "swat.dat"));
            if (size != PalXbeSize)
                Set(stGame, Bad, string.Format(Tr.S("st_game_ver"), size.ToString("N0")));
            else
                Set(stGame, dat ? Ok : Warn, string.Format(Tr.S(dat ? "st_game_ok" : "st_game_dat"), Short(g)));
        }
        var pack = Find(ModsDir, "textures.pack", 4);
        if (pack != null)
            Set(stTex, Ok, string.Format(Tr.S("st_tex_ok"), new FileInfo(pack).Length / 1073741824.0));
        else
            Set(stTex, Muted, Tr.S("st_tex_no"));
        int n = FilesIn(ModsDir, "*.mp4", 4).Select(f => Path.GetFileName(f).ToLowerInvariant()).Distinct().Count();
        Set(stVid, n > 0 ? Ok : Muted, n > 0 ? string.Format(Tr.S("st_vid_ok"), n) : Tr.S("st_vid_no"));
        var exe = FindExe();
        Set(stExe, exe != null ? Ok : Bad, exe != null ? string.Format(Tr.S("st_exe_ok"), Path.GetFileName(exe))
                                                       : Tr.S("st_exe_no"));
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
            o.Box.SelectedIndex = k >= 0 ? k : Array.IndexOf(o.Choices, DefOf(o));
        }
    }

    void Defaults()
    {
        foreach (var o in All()) o.Box.SelectedIndex = Array.IndexOf(o.Choices, DefOf(o));
    }

    bool Save()
    {
        try {
            var lines = File.Exists(Ini) ? File.ReadAllLines(Ini, Encoding.UTF8).ToList()
                                         : new List<string> { "# Ajustes del menú F2 (se reescribe solo). Configuración.exe también los cambia." };
            foreach (var o in All()) {
                string val = o.Choices[Math.Max(0, o.Box.SelectedIndex)];
                int at = lines.FindIndex(l => l.StartsWith(o.Key + "="));
                if (at >= 0) lines[at] = o.Key + "=" + val; else lines.Add(o.Key + "=" + val);
            }
            File.WriteAllLines(Ini, lines, new UTF8Encoding(false));
            return true;
        } catch (Exception e) {
            MessageBox.Show(this, Tr.S("err_save") + e.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }
    }

    // ---------- actions ----------
    void Play()
    {
        Refresh_();
        var exe = FindExe();
        if (exe == null) {
            MessageBox.Show(this, Tr.S("err_noexe"), Text);
            return;
        }
        if (FindGame() == null) {
            MessageBox.Show(this, Tr.S("err_nogame"), Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            OpenDir(GameDir);
            return;
        }
        try {
            Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = root, UseShellExecute = false });
            Close();
        } catch (Exception e) {
            MessageBox.Show(this, Tr.S("err_run") + e.Message, Text);
        }
    }

    void OpenDir(string d)
    {
        try { Directory.CreateDirectory(d); Process.Start("explorer.exe", "\"" + d + "\""); } catch { }
    }

    protected override void OnActivated(EventArgs e) { base.OnActivated(e); if (stGame != null) Refresh_(); }
}

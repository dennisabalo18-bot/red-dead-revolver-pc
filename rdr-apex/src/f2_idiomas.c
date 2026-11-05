/*
 * f2_idiomas.c - the F2 menu in the player's language.
 *
 * Every row of the F2 menu (host_menu.c's own, main.c's and mouselook.c's)
 * is written in Spanish, and rdr_menu.ini keeps the choices that way: the
 * menu and Configuración.exe both read them back by their text. Only what
 * the panel shows is translated, through xbox_MenuSetTranslator.
 *
 * The language is the launcher's (launcher.ini next to the exe, idioma=xx,
 * written by Configuración.exe's selector); without one, Windows' display
 * language; English for any language not here. Spanish shows the rows as
 * they are.
 */
#include <stdio.h>
#include <string.h>
#include <windows.h>

void xbox_MenuSetTranslator(const char *(*tr)(const char *utf8));

enum { EN, PT, FR, DE, IT, N_LANG };
static const char *const k_codes[N_LANG] = { "en", "pt", "fr", "de", "it" };
static int s_lang = -1;          /* -1: Spanish, nothing translated */

typedef struct { const char *es; const char *t[N_LANG]; } Text;

static const Text k_texts[] = {
    /* the panel */
    { "AJUSTES", { "SETTINGS", "CONFIGURAÇÕES", "PARAMÈTRES", "EINSTELLUNGEN", "IMPOSTAZIONI" } },
    { "F2 / Esc: cerrar", { "F2 / Esc: close", "F2 / Esc: fechar", "F2 / Échap : fermer",
                            "F2 / Esc: schließen", "F2 / Esc: chiudi" } },
    { "↑↓ elegir   ←→ cambiar   (se guarda solo)",
      { "↑↓ select   ←→ change   (saved automatically)",
        "↑↓ escolher   ←→ mudar   (salva sozinho)",
        "↑↓ choisir   ←→ modifier   (enregistré automatiquement)",
        "↑↓ wählen   ←→ ändern   (wird automatisch gespeichert)",
        "↑↓ scegli   ←→ cambia   (si salva da solo)" } },
    /* F6's notice */
    { "Texturas mejoradas (modernas)", { "Improved textures (modern)", "Texturas melhoradas (modernas)",
        "Textures améliorées (modernes)", "Verbesserte Texturen (modern)", "Texture migliorate (moderne)" } },
    { "Texturas originales (antiguas)", { "Original textures (classic)", "Texturas originais (antigas)",
        "Textures d'origine (anciennes)", "Originaltexturen (klassisch)", "Texture originali (classiche)" } },

    /* sections */
    { "Gráficos", { "Graphics", "Gráficos", "Graphismes", "Grafik", "Grafica" } },
    { "Juego", { "Game", "Jogo", "Jeu", "Spiel", "Gioco" } },
    { "Velocidad", { "Speed", "Velocidade", "Vitesse", "Geschwindigkeit", "Velocità" } },
    { "Texturas", { "Textures", "Texturas", "Textures", "Texturen", "Texture" } },
    { "Rendimiento", { "Performance", "Desempenho", "Performances", "Leistung", "Prestazioni" } },
    { "Ratón", { "Mouse", "Mouse", "Souris", "Maus", "Mouse" } },

    /* rows */
    { "Resolución interna", { "Internal resolution", "Resolução interna", "Résolution interne",
        "Interne Auflösung", "Risoluzione interna" } },
    { "Panorámico 16:9 (al reiniciar)", { "Widescreen 16:9 (on restart)", "Widescreen 16:9 (ao reiniciar)",
        "Écran large 16:9 (au redémarrage)", "Breitbild 16:9 (nach Neustart)", "Widescreen 16:9 (al riavvio)" } },
    { "Tamaño de ventana", { "Window size", "Tamanho da janela", "Taille de la fenêtre", "Fenstergröße",
        "Dimensione finestra" } },
    { "Pantalla completa (F11)", { "Fullscreen (F11)", "Tela cheia (F11)", "Plein écran (F11)", "Vollbild (F11)",
        "Schermo intero (F11)" } },
    { "Filtrado anisotrópico", { "Anisotropic filtering", "Filtragem anisotrópica", "Filtrage anisotrope",
        "Anisotrope Filterung", "Filtro anisotropico" } },
    { "Volcar texturas a carpeta", { "Dump textures to folder", "Exportar texturas para pasta",
        "Extraire les textures", "Texturen in Ordner speichern", "Esporta texture in cartella" } },
    { "VSync (sincronía vertical)", { "VSync (vertical sync)", "VSync (sincronia vertical)",
        "VSync (synchro verticale)", "VSync (vertikale Synchronisation)", "VSync (sincronia verticale)" } },
    { "Mostrar FPS", { "Show FPS", "Mostrar FPS", "Afficher les FPS", "FPS anzeigen", "Mostra FPS" } },
    { "Idioma (al reiniciar)", { "Language (on restart)", "Idioma (ao reiniciar)", "Langue (au redémarrage)",
        "Sprache (nach Neustart)", "Lingua (al riavvio)" } },
    { "Texturas mejoradas", { "Improved textures", "Texturas melhoradas", "Textures améliorées",
        "Verbesserte Texturen", "Texture migliorate" } },
    { "Botones en pantalla", { "On-screen buttons", "Botões na tela", "Boutons à l'écran",
        "Tasten am Bildschirm", "Pulsanti a schermo" } },
    { "Modo experimental (al reiniciar)", { "Experimental mode (on restart)", "Modo experimental (ao reiniciar)",
        "Mode expérimental (au redémarrage)", "Experimenteller Modus (nach Neustart)",
        "Modalità sperimentale (al riavvio)" } },
    { "Sensibilidad", { "Sensitivity", "Sensibilidade", "Sensibilité", "Empfindlichkeit", "Sensibilità" } },
    { "Sensibilidad vertical", { "Vertical sensitivity", "Sensibilidade vertical", "Sensibilité verticale",
        "Vertikale Empfindlichkeit", "Sensibilità verticale" } },
    { "Sensibilidad al apuntar (clic der.)", { "Aiming sensitivity (right click)",
        "Sensibilidade ao mirar (botão dir.)", "Sensibilité en visée (clic droit)",
        "Empfindlichkeit beim Zielen (Rechtsklick)", "Sensibilità in mira (tasto destro)" } },
    { "Velocidad máx. de giro", { "Max turn speed", "Velocidade máx. de giro", "Vitesse de rotation max.",
        "Max. Drehgeschwindigkeit", "Velocità max di rotazione" } },
    { "Invertir eje Y", { "Invert Y axis", "Inverter eixo Y", "Inverser l'axe Y", "Y-Achse umkehren",
        "Inverti asse Y" } },
    { "Modo del ratón", { "Mouse mode", "Modo do mouse", "Mode de la souris", "Mausmodus", "Modalità mouse" } },

    /* choices */
    { "Sí", { "Yes", "Sim", "Oui", "Ja", "Sì" } },
    { "No", { "No", "Não", "Non", "Nein", "No" } },
    { "Libre", { "Free", "Livre", "Libre", "Frei", "Libera" } },
    { "Sin límite", { "Unlimited", "Sem limite", "Illimitée", "Unbegrenzt", "Illimitata" } },
    { "Automático", { "Automatic", "Automático", "Automatique", "Automatisch", "Automatico" } },
    { "Teclado y ratón", { "Keyboard and mouse", "Teclado e mouse", "Clavier et souris", "Tastatur und Maus",
        "Tastiera e mouse" } },
    { "Mando Xbox", { "Xbox controller", "Controle Xbox", "Manette Xbox", "Xbox-Controller", "Controller Xbox" } },
    { "Mando PS4/PS5", { "PS4/PS5 controller", "Controle PS4/PS5", "Manette PS4/PS5", "PS4/PS5-Controller",
        "Controller PS4/PS5" } },
    { "Directo (como Black)", { "Direct (like Black)", "Direto (como Black)", "Direct (comme Black)",
        "Direkt (wie Black)", "Diretto (come Black)" } },
    { "Stick emulado", { "Emulated stick", "Analógico emulado", "Stick émulé", "Emulierter Stick",
        "Levetta emulata" } },
    { "x1 (como el mando)", { "x1 (like a controller)", "x1 (como o controle)", "x1 (comme la manette)",
        "x1 (wie Controller)", "x1 (come il controller)" } },
    { "No (4:3)", { "No (4:3)", "Não (4:3)", "Non (4:3)", "Nein (4:3)", "No (4:3)" } },
    { "Sí (nativo del juego)", { "Yes (game's own)", "Sim (nativo do jogo)", "Oui (natif du jeu)",
        "Ja (spieleigen)", "Sì (nativo del gioco)" } },
    { "Sí (PC gama baja)", { "Yes (low-end PC)", "Sim (PC mais fraco)", "Oui (PC modeste)",
        "Ja (schwacher PC)", "Sì (PC poco potente)" } },
    { "x4 (Ctrl+F8 dos veces)", { "x4 (Ctrl+F8 twice)", "x4 (Ctrl+F8 duas vezes)", "x4 (Ctrl+F8 deux fois)",
        "x4 (zweimal Ctrl+F8)", "x4 (Ctrl+F8 due volte)" } },
    { "4:3 (original)", { "4:3 (original)", "4:3 (original)", "4:3 (d'origine)", "4:3 (Original)",
        "4:3 (originale)" } },
};

static const char *translate(const char *es)
{
    size_t i;
    if (s_lang < 0 || !es)
        return NULL;
    for (i = 0; i < sizeof k_texts / sizeof k_texts[0]; i++)
        if (!strcmp(k_texts[i].es, es))
            return k_texts[i].t[s_lang];
    return NULL;
}

/* "es", "en"... from launcher.ini next to the exe, or "" */
static void launcher_lang(char *out, size_t n)
{
    wchar_t path[MAX_PATH], *slash;
    char line[64];
    FILE *f;
    out[0] = 0;
    if (!GetModuleFileNameW(NULL, path, MAX_PATH))
        return;
    slash = wcsrchr(path, L'\\');
    if (!slash || (size_t)(slash - path) + 14 >= MAX_PATH)
        return;
    wcscpy(slash + 1, L"launcher.ini");
    if (!(f = _wfopen(path, L"r")))
        return;
    while (fgets(line, sizeof line, f))
        if (!strncmp(line, "idioma=", 7)) {
            snprintf(out, n, "%.2s", line + 7);
            break;
        }
    fclose(f);
}

void f2_idiomas_init(void)
{
    char code[8];
    int i;
    launcher_lang(code, sizeof code);
    if (!code[0]) {
        switch (PRIMARYLANGID(GetUserDefaultUILanguage())) {
        case LANG_SPANISH:    strcpy(code, "es"); break;
        case LANG_PORTUGUESE: strcpy(code, "pt"); break;
        case LANG_FRENCH:     strcpy(code, "fr"); break;
        case LANG_GERMAN:     strcpy(code, "de"); break;
        case LANG_ITALIAN:    strcpy(code, "it"); break;
        default:              strcpy(code, "en"); break;
        }
    }
    s_lang = -1;
    for (i = 0; i < N_LANG; i++)
        if (!strcmp(code, k_codes[i]))
            s_lang = i;
    if (s_lang < 0 && strcmp(code, "es"))
        s_lang = EN;
    xbox_MenuSetTranslator(translate);
    fprintf(stderr, "[MENU] language: %s\n", s_lang < 0 ? "es" : k_codes[s_lang]);
}

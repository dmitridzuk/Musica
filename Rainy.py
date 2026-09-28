import webbrowser
import ntpath
import json
import os
import time
import random
import threading
import atexit

import dearpygui.dearpygui as dpg
from mutagen.mp3 import MP3
from tkinter import Tk, filedialog
import pygame

# ---------- Пути ----------
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(BASE_DIR, "data")
SONGS_FILE    = os.path.join(DATA_DIR, "songs.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
FONT_PATH     = os.path.join(BASE_DIR, "fonts", "JetBrainsMono-Bold.ttf")
ICON_PATH     = os.path.join(BASE_DIR, "icon.ico")

os.makedirs(DATA_DIR, exist_ok=True)

if not os.path.exists(SONGS_FILE):
    with open(SONGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"songs": []}, f, indent=4)

# ---------- Состояние ----------
state = None              # None | "playing" | "paused"
current_song = None
slider_thread = None
slider_running = False

_DEFAULT_MUSIC_VOLUME = 0.5

# ---------- Инициализация ----------
dpg.create_context()
dpg.create_viewport(title="Rainy Music", width=1280, height=800)
pygame.mixer.init()

# ---------- Работа с данными ----------
def load_songs():
    try:
        with open(SONGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("songs", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_songs(songs):
    with open(SONGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"songs": songs}, f, indent=4, ensure_ascii=False)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"volume": _DEFAULT_MUSIC_VOLUME * 100}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# ---------- Утилиты ----------
def fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"

def update_track_count():
    count = len(load_songs())
    try:
        dpg.set_value("track_count", f"{count} track{'s' if count != 1 else ''}")
    except SystemError:
        pass

def add_song_row(path: str):
    norm = path.replace("\\", "/")
    dpg.add_button(
        label=f"  {ntpath.basename(path)}",
        callback=play,
        width=-1,
        height=36,
        user_data=norm,
        parent="list",
    )
    dpg.add_spacer(height=4, parent="list")

def refresh_list(filter_text: str = ""):
    dpg.delete_item("list", children_only=True)
    songs = load_songs()
    filter_text = (filter_text or "").strip().lower()
    for path in songs:
        if not filter_text or filter_text in ntpath.basename(path).lower():
            add_song_row(path)
    highlight_current()
    update_track_count()

def highlight_current():
    for child in dpg.get_item_children("list", 1) or []:
        if dpg.get_item_type(child) == "mvAppItemType::mvButton":
            path = dpg.get_item_user_data(child)
            if path == current_song:
                dpg.bind_item_theme(child, "theme_active_song")
            else:
                dpg.bind_item_theme(child, "theme_song")

# ---------- Плеер ----------
def update_slider():
    global slider_running
    while pygame.mixer.music.get_busy() and slider_running:
        pos = pygame.mixer.music.get_pos() / 1000.0
        total = dpg.get_item_configuration("pos")["max_value"]
        try:
            dpg.set_value("pos", pos)
            dpg.set_value("time_text", f"{fmt_time(pos)} / {fmt_time(total)}")
        except SystemError:
            break
        time.sleep(0.5)

    if slider_running and not pygame.mixer.music.get_busy() and state == "playing":
        slider_running = False
        next_song(auto=True)
        return

    slider_running = False
    reset_ui()

def reset_ui():
    global state
    state = None
    try:
        dpg.set_value("pos", 0)
        dpg.configure_item("pos", max_value=100)
        dpg.configure_item("play", label="Play")
        dpg.bind_item_theme("play", "btn_accent")
        dpg.set_value("csong", "Nothing is playing")
        dpg.set_value("cstate", "Stopped")
        dpg.configure_item("cstate", color=(200, 90, 120))
        dpg.set_value("time_text", "00:00 / 00:00")
    except SystemError:
        pass

def start_slider_thread():
    global slider_thread, slider_running
    slider_running = True
    slider_thread = threading.Thread(target=update_slider, daemon=True)
    slider_thread.start()

def play(sender=None, app_data=None, user_data=None):
    global state, current_song

    if not user_data:
        return

    try:
        if not os.path.exists(user_data):
            print(f"[ERR] Файл не найден: {user_data}")
            return

        pygame.mixer.music.load(user_data)
        audio = MP3(user_data)
        duration = audio.info.length

        dpg.set_value("pos", 0)
        dpg.configure_item("pos", max_value=duration)
        pygame.mixer.music.play()

        current_song = user_data
        state = "playing"

        dpg.configure_item("play", label="Pause")
        dpg.bind_item_theme("play", "btn_accent")
        dpg.set_value("csong", ntpath.basename(user_data))
        dpg.set_value("cstate", "Playing")
        dpg.configure_item("cstate", color=(167, 139, 250))
        dpg.set_value("time_text", f"00:00 / {fmt_time(duration)}")

        highlight_current()
        start_slider_thread()
    except Exception as e:
        print(f"[ERR] Ошибка воспроизведения: {e}")

def play_pause():
    global state
    if state == "playing":
        pygame.mixer.music.pause()
        state = "paused"
        dpg.configure_item("play", label="Play")
        dpg.bind_item_theme("play", "btn_accent")
        dpg.set_value("cstate", "Paused")
        dpg.configure_item("cstate", color=(244, 114, 182))
    elif state == "paused":
        pygame.mixer.music.unpause()
        state = "playing"
        dpg.configure_item("play", label="Pause")
        dpg.bind_item_theme("play", "btn_accent")
        dpg.set_value("cstate", "Playing")
        dpg.configure_item("cstate", color=(167, 139, 250))
    else:
        songs = load_songs()
        if songs:
            play(user_data=random.choice(songs))

def next_song(auto=False):
    global current_song
    songs = load_songs()
    if not songs:
        return
    if current_song in songs:
        idx = (songs.index(current_song) + 1) % len(songs)
    else:
        idx = 0
    play(user_data=songs[idx])

def pre_song():
    global current_song
    songs = load_songs()
    if not songs:
        return
    if current_song in songs:
        idx = (songs.index(current_song) - 1) % len(songs)
    else:
        idx = 0
    play(user_data=songs[idx])

def stop():
    pygame.mixer.music.stop()
    reset_ui()
    highlight_current()

def update_volume(sender, app_data):
    pygame.mixer.music.set_volume(app_data / 100.0)
    settings = load_settings()
    settings["volume"] = app_data
    save_settings(settings)

def seek(sender, app_data):
    if state in ("playing", "paused"):
        try:
            pygame.mixer.music.play(start=app_data)
            if state == "paused":
                pygame.mixer.music.pause()
        except Exception as e:
            print(f"[ERR] Не удалось перемотать: {e}")

# ---------- Работа с файлами ----------
def add_files():
    root = Tk()
    root.withdraw()
    files = filedialog.askopenfilenames(
        filetypes=[("Music Files", ("*.mp3", "*.wav", "*.ogg"))]
    )
    root.destroy()

    songs = load_songs()
    for filename in files:
        if filename.lower().endswith((".mp3", ".wav", ".ogg")):
            norm = filename.replace("\\", "/")
            if norm not in songs:
                songs.append(norm)
    save_songs(songs)
    refresh_list(dpg.get_value("search_input"))

def add_folder():
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory()
    root.destroy()

    if not folder:
        return

    songs = load_songs()
    for filename in os.listdir(folder):
        if filename.lower().endswith((".mp3", ".wav", ".ogg")):
            full = os.path.join(folder, filename).replace("\\", "/")
            if full not in songs:
                songs.append(full)
    save_songs(songs)
    refresh_list(dpg.get_value("search_input"))

def search(sender, app_data, user_data):
    refresh_list(app_data)

def remove_all():
    save_songs([])
    refresh_list()

# ---------- Горячие клавиши ----------
def on_key(sender, app_data):
    key = app_data
    if key == dpg.mvKey_Spacebar:
        play_pause()
    elif key == dpg.mvKey_Right:
        next_song()
    elif key == dpg.mvKey_Left:
        pre_song()
    elif key == dpg.mvKey_S:
        stop()

# ==========================================================
#                        ТЕМЫ
# ==========================================================

# Базовая тема — фиолетово-розовая, крупная
with dpg.theme(tag="base"):
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_color(dpg.mvThemeCol_WindowBg,       (20, 17, 24))
        dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        (28, 23, 35))
        dpg.add_theme_color(dpg.mvThemeCol_PopupBg,        (28, 23, 35))
        dpg.add_theme_color(dpg.mvThemeCol_Border,         (0, 0, 0, 0))
        dpg.add_theme_color(dpg.mvThemeCol_Text,           (237, 233, 254))
        dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,   (140, 130, 170))
        dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        (40, 33, 52))
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (60, 50, 80))
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,  (80, 65, 105))

        dpg.add_theme_color(dpg.mvThemeCol_Button,         (80, 65, 105))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,  (110, 85, 150))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,   (139, 92, 246))

        dpg.add_theme_color(dpg.mvThemeCol_TitleBg,        (20, 17, 24))
        dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,  (60, 45, 90))
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,    (0, 0, 0, 0))
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,  (100, 80, 150))
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (140, 110, 200))
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive,  (167, 139, 250))
        dpg.add_theme_color(dpg.mvThemeCol_CheckMark,      (244, 114, 182))
        dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,     (244, 114, 182))
        dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (255, 150, 200))

        # Крупные размеры
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,  8)
        dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,  12)
        dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 10)
        dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,   8)
        dpg.add_theme_style(dpg.mvStyleVar_FramePadding,   12, 9)
        dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,    12, 10)
        dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,  16, 18)
        dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize,  14)
        dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)
        dpg.add_theme_style(dpg.mvStyleVar_WindowTitleAlign, 0.5, 0.5)

# Акцентная кнопка (Play/Pause)
with dpg.theme(tag="btn_accent"):
    with dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button,        (167, 139, 250))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (196, 181, 253))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (139, 92, 246))
        dpg.add_theme_color(dpg.mvThemeCol_Text,          (20, 17, 24))
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 10)

# Вторичная кнопка (Pre/Next/Stop)
with dpg.theme(tag="btn_secondary"):
    with dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button,        (45, 37, 60))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (70, 58, 95))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (100, 80, 140))
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 10)

# Кнопка трека — спокойная
with dpg.theme(tag="theme_song"):
    with dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button,        (40, 33, 52, 120))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 65, 105, 200))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (120, 90, 170, 200))
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)

# Активный трек — фиолетово-розовая подсветка
with dpg.theme(tag="theme_active_song"):
    with dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button,        (167, 139, 250, 210))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (196, 181, 253, 240))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (139, 92, 246, 240))
        dpg.add_theme_color(dpg.mvThemeCol_Text,          (20, 17, 24))
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)

# Слайдеры (тонкие, акцентные)
with dpg.theme(tag="slider_thin"):
    with dpg.theme_component(dpg.mvSliderFloat):
        dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        (60, 50, 80, 150))
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (90, 75, 120, 180))
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,  (120, 90, 170, 200))
        dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,     (244, 114, 182))
        dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (255, 160, 210))
        dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 6)
        dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 24)

# Кнопки сайдбара — «призрачные», без яркой заливки
with dpg.theme(tag="btn_ghost"):
    with dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button,        (40, 33, 52, 0))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 65, 105, 200))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (139, 92, 246, 220))
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)

# ==========================================================
#                     ШРИФТЫ
# ==========================================================
font_ok = os.path.exists(FONT_PATH)
if font_ok:
    with dpg.font_registry():
        font_body = dpg.add_font(FONT_PATH, 16)
        font_h1   = dpg.add_font(FONT_PATH, 22)
        font_h2   = dpg.add_font(FONT_PATH, 18)

# ==========================================================
#                        UI
# ==========================================================
with dpg.window(tag="main", label="Rainy Music", no_title_bar=False):

    # ---------- Плашка Now Playing ----------
    with dpg.child_window(autosize_x=True, height=96, no_scrollbar=True, border=False):
        dpg.add_text("NOW PLAYING", color=(140, 130, 170))
        with dpg.group(horizontal=True):
            dpg.add_text("Nothing is playing", tag="csong", color=(237, 233, 254))
            # растяжка — тайминг вправо
            dpg.add_spacer(width=20)
            dpg.add_text("00:00 / 00:00", tag="time_text", color=(180, 165, 220))

    dpg.add_spacer(height=6)

    with dpg.group(horizontal=True):

        # ---------- Сайдбар ----------
        with dpg.child_window(width=260, tag="sidebar"):
            dpg.add_text("Rainy Music", color=(167, 139, 250))
            dpg.add_text("by GVDmitriy", color=(140, 130, 170))
            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_spacer(height=10)

            dpg.add_button(label="Support",     width=-1, height=36,
                           callback=lambda: webbrowser.open(url="https://vk.ru/cfg_alone"))
            dpg.add_spacer(height=8)
            dpg.add_button(label="Add File",    width=-1, height=40, callback=add_files)
            dpg.add_button(label="Add Folder",  width=-1, height=40, callback=add_folder)
            dpg.add_button(label="Remove All",  width=-1, height=40, callback=remove_all)

            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_spacer(height=10)
            dpg.add_text("STATUS", color=(140, 130, 170))
            dpg.add_text("Stopped", tag="cstate", color=(200, 90, 120))

            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_spacer(height=10)
            dpg.add_text("HOTKEYS", color=(140, 130, 170))
            dpg.add_text("Space      Play / Pause", color=(180, 165, 220))
            dpg.add_text("Left / Right   Pre / Next", color=(180, 165, 220))
            dpg.add_text("S             Stop", color=(180, 165, 220))

            # применяем «призрачный» стиль к кнопкам сайдбара
            for btn in dpg.get_item_children("sidebar", 1):
                if dpg.get_item_type(btn) == "mvAppItemType::mvButton":
                    dpg.bind_item_theme(btn, "btn_ghost")

        # ---------- Основная область ----------
        with dpg.child_window(autosize_x=True, border=False):

            # Панель управления
            with dpg.child_window(autosize_x=True, height=140, no_scrollbar=True, border=False):
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Play", width=120, height=46, tag="play", callback=play_pause)
                    dpg.add_button(label="Pre",  width=100, height=46, callback=pre_song)
                    dpg.add_button(label="Next", width=100, height=46, callback=next_song)
                    dpg.add_button(label="Stop", width=100, height=46, callback=stop)

                dpg.add_spacer(height=10)

                with dpg.group(horizontal=True):
                    dpg.add_text("Vol", color=(244, 114, 182))
                    dpg.add_slider_float(tag="volume", width=180, height=22,
                                         format="%.0f%%",
                                         default_value=load_settings().get("volume", 50),
                                         callback=update_volume)
                    dpg.add_spacer(width=16)
                    dpg.add_slider_float(tag="pos", width=-1, height=22, format="",
                                         callback=seek)

            dpg.add_spacer(height=8)

            # Библиотека
            with dpg.child_window(autosize_x=True, delay_search=True, border=False):
                with dpg.group(horizontal=True):
                    dpg.add_text("LIBRARY", color=(140, 130, 170))
                    dpg.add_spacer(width=8)
                    dpg.add_text("0 tracks", tag="track_count", color=(244, 114, 182))

                dpg.add_spacer(height=6)

                with dpg.group(horizontal=True):
                    dpg.add_text("Search:", color=(244, 114, 182))
                    dpg.add_input_text(tag="search_input", hint="Type song name...",
                                       width=-1, callback=search, height=36)

                dpg.add_spacer(height=8)

                with dpg.child_window(autosize_x=True, delay_search=True, tag="list"):
                    refresh_list()

    # привязка тем
    dpg.bind_item_theme("play", "btn_accent")
    dpg.bind_item_theme("volume", "slider_thin")
    dpg.bind_item_theme("pos", "slider_thin")
    dpg.bind_item_theme("list", "theme_song")

dpg.bind_theme("base")

# Шрифты: базовый на всё, крупные — точечно
if font_ok:
    dpg.bind_font(font_body)
    dpg.bind_item_font("csong", font_h1)
    # заголовки-секции
    for tag in ("main",):
        pass  # placeholder, ниже точечно

# Стартовая громкость
pygame.mixer.music.set_volume(load_settings().get("volume", 50) / 100.0)

# ---------- Горячие клавиши ----------
with dpg.handler_registry():
    dpg.add_key_press_handler(callback=on_key)

# ---------- Корректный выход ----------
def safe_exit():
    global slider_running
    slider_running = False
    try:
        pygame.mixer.music.stop()
        pygame.quit()
    except Exception:
        pass

atexit.register(safe_exit)

# ---------- Запуск ----------
dpg.setup_dearpygui()
if os.path.exists(ICON_PATH):
    try:
        dpg.set_viewport_large_icon(ICON_PATH)
        dpg.set_viewport_small_icon(ICON_PATH)
    except Exception:
        pass
dpg.show_viewport()
dpg.set_primary_window("main", True)
dpg.maximize_viewport()
dpg.start_dearpygui()
dpg.destroy_context()
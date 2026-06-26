import copy
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QGuiApplication, QKeySequence, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)


HEX_RE = re.compile(r"^#[0-9A-F]{6}$")
MIN_BBOX_SIZE = 16
APP_DIR = Path(__file__).resolve().parent
LIBRARY_FILE = APP_DIR / "prompt_library.json"
PREVIEW_DIR = APP_DIR / "prompt_previews"
LANG_FILE = APP_DIR / "translations.json"
SETTINGS_FILE = APP_DIR / "comfy_settings.json"
DRAFT_FILE = APP_DIR / "draft.json"
WORKFLOW_FILE = APP_DIR / "ideogram4NSFWComfyui_v11.json"
DEFAULT_LANGUAGE = "en"
LANGUAGE_NAMES = {"en": "English", "ru": "Русский"}
MAX_UNDO = 60

DEFAULT_SETTINGS = {
    "comfy_host": "127.0.0.1",
    "comfy_port": 8188,
    "comfy_https": False,
    "theme": "light",
    "language": DEFAULT_LANGUAGE,
}

# Models / samplers / custom nodes the bundled workflow needs to run in ComfyUI.
REQUIRED_COMFY = {
    "nodes": [
        "Ideogram4PromptBuilderKJ",
        "Ideogram4Scheduler",
        "UNETLoader",
        "VAELoader",
        "CLIPLoader",
        "CLIPLoaderGGUF",
        "DualModelGuider",
        "SamplerCustomAdvanced",
        "KSamplerSelect",
        "RandomNoise",
        "VAEDecode",
    ],
    "unet": [
        "ideogram4_fp8_scaled.safetensors",
        "ideogram4_unconditional_fp8_scaled.safetensors",
    ],
    "vae": ["flux2-vae.safetensors"],
    "clip": ["qwen3vl_8b_fp8_scaled.safetensors"],
    "clip_gguf": ["Qwen3VL-8B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf"],
    "samplers": ["euler"],
}

# Quick-insert element templates (item 12).
ELEMENT_TEMPLATES = {
    "Character": {
        "type": "obj",
        "desc": "A full-body character with realistic proportions and natural posture.",
        "bbox": [120, 320, 950, 690],
    },
    "Title text": {
        "type": "text",
        "text": "TITLE",
        "desc": "Bold display lettering across the top of the composition.",
        "bbox": [70, 120, 200, 880],
    },
    "Background object": {
        "type": "obj",
        "desc": "A secondary object that anchors the background of the scene.",
        "bbox": [400, 100, 800, 500],
    },
}

THEMES = {
    "light": {
        "bg": "#F4F6F4", "panel": "#FFFFFF", "text": "#182024", "muted": "#5D666F",
        "border": "#DDE3DD", "field_border": "#CBD5CE", "accent": "#176B87",
        "accent_dark": "#0F5269", "list_sel_bg": "#DCEFF3", "list_sel_fg": "#0F5269",
        "hover_bg": "#F0F7F8", "canvas_bg": "#F3F6F3", "canvas_grid": "#D4DCD4",
        "canvas_label": "#98A39B", "error": "#C0392B",
    },
    "dark": {
        "bg": "#1E2227", "panel": "#272C33", "text": "#E6EAED", "muted": "#9AA4AD",
        "border": "#363C44", "field_border": "#3C434C", "accent": "#3AA6C4",
        "accent_dark": "#2C8BA6", "list_sel_bg": "#234049", "list_sel_fg": "#CDEBF3",
        "hover_bg": "#2E3942", "canvas_bg": "#22272D", "canvas_grid": "#3A424A",
        "canvas_label": "#6C757D", "error": "#E06A5C",
    },
}


def build_stylesheet(theme):
    c = THEMES.get(theme, THEMES["light"])
    return f"""
        QMainWindow, QWidget {{ background: {c['bg']}; color: {c['text']}; font-family: Segoe UI; font-size: 10.5pt; }}
        QToolBar {{ background: {c['panel']}; border: 0; border-bottom: 1px solid {c['border']}; spacing: 8px; padding: 8px; }}
        QToolButton {{ border-radius: 7px; padding: 6px 10px; color: {c['text']}; }}
        QToolBar QToolButton:hover {{ background: {c['hover_bg']}; }}
        QGroupBox {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; margin-top: 18px; padding: 14px; font-weight: 700; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 7px; color: {c['accent']}; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget {{
            background: {c['panel']}; border: 1px solid {c['field_border']}; border-radius: 8px; padding: 7px;
            selection-background-color: {c['accent']}; color: {c['text']};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {c['accent']};
        }}
        QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{ border: 1px solid {c['error']}; }}
        QPushButton {{
            background: {c['panel']}; border: 1px solid {c['field_border']}; border-radius: 8px; padding: 8px 12px; color: {c['text']};
        }}
        QPushButton:hover {{ border-color: {c['accent']}; background: {c['hover_bg']}; }}
        QPushButton:disabled {{ color: {c['muted']}; }}
        QPushButton#PrimaryButton {{ background: {c['accent']}; color: white; border-color: {c['accent']}; font-weight: 700; }}
        QPushButton#PrimaryButton:hover {{ background: {c['accent_dark']}; }}
        QListWidget::item {{ padding: 8px; border-radius: 6px; }}
        QListWidget::item:selected {{ background: {c['list_sel_bg']}; color: {c['list_sel_fg']}; }}
        QRadioButton, QCheckBox {{ background: transparent; }}
        QLabel {{ background: transparent; }}
    """


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                settings.update({k: data[k] for k in DEFAULT_SETTINGS if k in data})
        except (OSError, json.JSONDecodeError):
            pass
    return settings


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


DEFAULT_TRANSLATIONS = {
    "en": {
        "app.title": "Ideogram 4 Prompt Builder",
        "tb.example": "Example",
        "tb.import": "Import JSON",
        "tb.save_json": "Save JSON",
        "tb.copy": "Copy",
        "tb.save_library": "Save to library",
        "tb.library": "Library",
        "tb.language": "Language:",
        "grp.high": "High level description",
        "high.placeholder": "One- or two-sentence summary of the full image...",
        "grp.presets": "Presets",
        "preset.no_safety": "Add \"No safety filter.\"",
        "grp.style": "Style",
        "style.photo": "Photo",
        "style.art": "Art",
        "style.aesthetics": "Aesthetics",
        "style.lighting": "Lighting",
        "style.photo_field": "Photo",
        "style.art_style": "Art style",
        "style.medium": "Medium",
        "style.palette": "Palette",
        "grp.composition": "Composition",
        "comp.background": "Background",
        "comp.background_placeholder": "Describe the environment or background before listing foreground elements...",
        "comp.add_element": "Add element",
        "comp.remove_element": "Remove element",
        "comp.hint": "Drag the rectangle to move the element. Drag the round handles to resize the bbox.",
        "el.type": "Type",
        "el.label": "Label",
        "el.text": "Text",
        "el.description": "Description",
        "el.palette": "Palette",
        "el.use_bbox": "Use bbox",
        "el.bbox": "BBox",
        "el.element": "Element",
        "out.title": "Ready JSON",
        "out.pretty": "Pretty",
        "out.compact": "Compact",
        "out.copy_compact": "Copy compact",
        "out.save_json_btn": "Save .json",
        "canvas.label": "bbox canvas 0-1000",
        "val.ok": "JSON assembled in Ideogram 4 key order and ready for ComfyUI.",
        "val.no_high": "Add high_level_description for better scene adherence.",
        "val.bg_required": "background is required.",
        "val.add_element": "Add at least one element.",
        "val.style_missing": "style_description is missing: {fields}.",
        "val.photo_or_art": "Exactly one key required: photo or art_style.",
        "val.hex_upper": "Color {color} must be uppercase #RRGGBB.",
        "val.text_literal": "{title}: text element requires a literal text.",
        "val.desc_required": "{title}: desc is required.",
        "val.bbox_order": "{title}: bbox must have y_max/x_max greater than y_min/x_min.",
        "val.el_hex": "{title}: color {color} must be uppercase #RRGGBB.",
        "val.element_word": "element {index}",
        "pal.placeholder": "#1E73BE, #FDFDFD",
        "pal.add": "Add color",
        "pal.configure": "Configure color",
        "pal.swatch_tip": "{color}: click to configure",
        "pal.remove": "Remove color",
        "dlg.save_json_title": "Save JSON",
        "dlg.json_filter": "JSON files (*.json);;All files (*)",
        "dlg.import_title": "Import JSON",
        "imp.error_title": "Import error",
        "trn.error_title": "Translate error",
        "trn.error_msg": "Translation failed:\n{err}",
        "trn.to_ru": "Translate to RU",
        "trn.to_en": "Translate to EN",
        "lib.name_prompt": "Prompt name:",
        "lib.untitled": "Untitled",
        "lib.preview_q_title": "Preview",
        "lib.preview_q": "Attach a preview image to this prompt?",
        "lib.save_fail": "Failed to save:\n{err}",
        "lib.saved": "Prompt \"{name}\" saved.",
        "prev.pick_title": "Choose preview image",
        "prev.filter": "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)",
        "prev.save_fail": "Failed to save image:\n{err}",
        "prev.title": "Preview",
        "libd.title": "Prompt library",
        "libd.saved_prompts": "Saved prompts",
        "libd.no_preview": "No preview",
        "libd.preview_unavailable": "Preview unavailable",
        "libd.use": "Load into editor",
        "libd.rename": "Rename",
        "libd.set_preview": "Set preview",
        "libd.clear_preview": "Clear preview",
        "libd.delete": "Delete",
        "libd.close": "Close",
        "libd.rename_title": "Rename",
        "libd.rename_label": "Name:",
        "libd.delete_title": "Delete prompt",
        "libd.delete_q": "Delete \"{name}\" from the library?",
        "libd.meta": "Updated: {updated}\nElements: {count}\n\n{high}",
        "libd.no_high": "(no high_level_description)",
        "libd.search": "Search...",
        "libd.tags": "Tags (comma-separated):",
        "libd.tags_col": "Tags",
        "libd.paste_preview": "Paste preview from clipboard",
        "libd.export": "Export library...",
        "libd.import": "Import library...",
        "libd.no_clipboard_image": "No image in the clipboard.",
        "libd.export_done": "Library exported to:\n{path}",
        "libd.import_done": "Imported {count} prompt(s).",
        "libd.export_fail": "Export failed:\n{err}",
        "libd.import_fail": "Import failed:\n{err}",
        "libd.export_filter": "ZIP archive (*.zip)",
        "tb.undo": "Undo",
        "tb.redo": "Redo",
        "tb.duplicate": "Duplicate element",
        "tb.move_up": "Move up",
        "tb.move_down": "Move down",
        "tb.theme": "Theme",
        "tb.comfy_settings": "ComfyUI settings",
        "tb.generate": "Generate in ComfyUI",
        "tb.check_comfy": "Check ComfyUI",
        "tb.template": "Add from template",
        "tb.overwrite": "Update in library",
        "menu.file": "File",
        "menu.edit": "Edit",
        "menu.library": "Library",
        "menu.comfy": "ComfyUI",
        "menu.view": "View",
        "canvas.load_ref": "Reference image...",
        "canvas.paste_ref": "Paste reference",
        "canvas.clear_ref": "Clear reference",
        "canvas.zoom": "Grid scale",
        "canvas.ref_load_fail": "Could not load image.",
        "counter.colors": "{count}/{limit} colors",
        "set.title": "ComfyUI connection settings",
        "set.host": "Host:",
        "set.port": "Port:",
        "set.https": "Use HTTPS",
        "set.test": "Test connection",
        "set.test_ok": "Connection OK. ComfyUI is reachable.",
        "set.test_fail": "Connection failed:\n{err}",
        "set.saved": "Settings saved.",
        "comfy.checking": "Checking ComfyUI...",
        "comfy.check_title": "ComfyUI dependency check",
        "comfy.all_ok": "All required nodes and models are installed.",
        "comfy.unreachable": "ComfyUI is unreachable at {url}:\n{err}",
        "comfy.missing_header": "Missing on the server:",
        "comfy.missing_nodes": "Custom nodes: {items}",
        "comfy.missing_unet": "UNET models: {items}",
        "comfy.missing_vae": "VAE: {items}",
        "comfy.missing_clip": "CLIP: {items}",
        "comfy.missing_clip_gguf": "CLIP GGUF: {items}",
        "comfy.missing_samplers": "Samplers: {items}",
        "comfy.generating": "Generating in ComfyUI...",
        "comfy.gen_title": "Generation",
        "comfy.gen_fail": "Generation failed:\n{err}",
        "comfy.gen_done": "Image generated.",
        "tab.json": "JSON",
        "tab.result": "Result",
        "result.empty": "Generated image will appear here.",
        "result.save_lib": "Save to library",
        "result.save_file": "Save image...",
        "result.saved_file": "Image saved to:\n{path}",
        "result.png_filter": "PNG image (*.png)",
        "comfy.workflow_missing": "Workflow file not found:\n{path}",
        "comfy.deps_missing_continue": "Some dependencies are missing. Generate anyway?",
        "comfy.save_to_lib_q": "Save the generated image to the library?",
        "draft.restore_title": "Restore draft",
        "draft.restore_q": "An unsaved draft was found. Restore it?",
        "tpl.choose_title": "Element template",
        "tpl.choose_label": "Choose a template:",
        "common.cancel": "Cancel",
        "common.ok": "OK",
        "common.close": "Close",
    },
    "ru": {
        "app.title": "Ideogram 4 Prompt Builder",
        "tb.example": "Пример",
        "tb.import": "Импорт JSON",
        "tb.save_json": "Сохранить JSON",
        "tb.copy": "Копировать",
        "tb.save_library": "Сохранить в библиотеку",
        "tb.library": "Библиотека",
        "tb.language": "Язык:",
        "grp.high": "Общее описание",
        "high.placeholder": "Краткое описание всей сцены в одно-два предложения...",
        "grp.presets": "Пресеты",
        "preset.no_safety": "Добавить \"No safety filter.\"",
        "grp.style": "Стиль",
        "style.photo": "Фото",
        "style.art": "Арт",
        "style.aesthetics": "Эстетика",
        "style.lighting": "Освещение",
        "style.photo_field": "Фото",
        "style.art_style": "Арт-стиль",
        "style.medium": "Носитель",
        "style.palette": "Палитра",
        "grp.composition": "Композиция",
        "comp.background": "Фон",
        "comp.background_placeholder": "Опишите окружение или фон перед перечислением объектов переднего плана...",
        "comp.add_element": "Добавить элемент",
        "comp.remove_element": "Удалить элемент",
        "comp.hint": "Перетаскивайте прямоугольник, чтобы переместить элемент. Тяните круглые маркеры, чтобы масштабировать bbox.",
        "el.type": "Тип",
        "el.label": "Метка",
        "el.text": "Текст",
        "el.description": "Описание",
        "el.palette": "Палитра",
        "el.use_bbox": "Использовать bbox",
        "el.bbox": "BBox",
        "el.element": "Элемент",
        "out.title": "Готовый JSON",
        "out.pretty": "Pretty",
        "out.compact": "Compact",
        "out.copy_compact": "Копировать compact",
        "out.save_json_btn": "Сохранить .json",
        "canvas.label": "bbox canvas 0-1000",
        "val.ok": "JSON собран в порядке ключей Ideogram 4 и готов для ComfyUI.",
        "val.no_high": "Добавьте high_level_description для лучшего следования сцене.",
        "val.bg_required": "background обязателен.",
        "val.add_element": "Добавьте хотя бы один элемент.",
        "val.style_missing": "В style_description не хватает: {fields}.",
        "val.photo_or_art": "Нужен ровно один ключ: photo или art_style.",
        "val.hex_upper": "Цвет {color} должен быть uppercase #RRGGBB.",
        "val.text_literal": "{title}: для text-элемента нужен literal text.",
        "val.desc_required": "{title}: desc обязателен.",
        "val.bbox_order": "{title}: bbox должен иметь y_max/x_max больше y_min/x_min.",
        "val.el_hex": "{title}: цвет {color} должен быть uppercase #RRGGBB.",
        "val.element_word": "element {index}",
        "pal.placeholder": "#1E73BE, #FDFDFD",
        "pal.add": "Добавить цвет",
        "pal.configure": "Настроить цвет",
        "pal.swatch_tip": "{color}: нажмите, чтобы настроить",
        "pal.remove": "Удалить цвет",
        "dlg.save_json_title": "Сохранить JSON",
        "dlg.json_filter": "JSON файлы (*.json);;Все файлы (*)",
        "dlg.import_title": "Импорт JSON",
        "imp.error_title": "Ошибка импорта",
        "trn.error_title": "Ошибка перевода",
        "trn.error_msg": "Не удалось выполнить перевод:\n{err}",
        "trn.to_ru": "Перевести на RU",
        "trn.to_en": "Перевести на EN",
        "lib.name_prompt": "Название промта:",
        "lib.untitled": "Без названия",
        "lib.preview_q_title": "Превью",
        "lib.preview_q": "Добавить изображение превью к этому промту?",
        "lib.save_fail": "Не удалось сохранить:\n{err}",
        "lib.saved": "Промт «{name}» сохранён.",
        "prev.pick_title": "Выбрать изображение превью",
        "prev.filter": "Изображения (*.png *.jpg *.jpeg *.webp *.bmp);;Все файлы (*)",
        "prev.save_fail": "Не удалось сохранить изображение:\n{err}",
        "prev.title": "Превью",
        "libd.title": "Библиотека промтов",
        "libd.saved_prompts": "Сохранённые промты",
        "libd.no_preview": "Нет превью",
        "libd.preview_unavailable": "Превью недоступно",
        "libd.use": "Загрузить в редактор",
        "libd.rename": "Переименовать",
        "libd.set_preview": "Задать превью",
        "libd.clear_preview": "Убрать превью",
        "libd.delete": "Удалить",
        "libd.close": "Закрыть",
        "libd.rename_title": "Переименовать",
        "libd.rename_label": "Название:",
        "libd.delete_title": "Удалить промт",
        "libd.delete_q": "Удалить «{name}» из библиотеки?",
        "libd.meta": "Обновлено: {updated}\nЭлементов: {count}\n\n{high}",
        "libd.no_high": "(без high_level_description)",
        "libd.search": "Поиск...",
        "libd.tags": "Теги (через запятую):",
        "libd.tags_col": "Теги",
        "libd.paste_preview": "Вставить превью из буфера",
        "libd.export": "Экспорт библиотеки...",
        "libd.import": "Импорт библиотеки...",
        "libd.no_clipboard_image": "В буфере обмена нет изображения.",
        "libd.export_done": "Библиотека экспортирована в:\n{path}",
        "libd.import_done": "Импортировано промтов: {count}.",
        "libd.export_fail": "Не удалось экспортировать:\n{err}",
        "libd.import_fail": "Не удалось импортировать:\n{err}",
        "libd.export_filter": "ZIP архив (*.zip)",
        "tb.undo": "Отменить",
        "tb.redo": "Повторить",
        "tb.duplicate": "Дублировать элемент",
        "tb.move_up": "Вверх",
        "tb.move_down": "Вниз",
        "tb.theme": "Тема",
        "tb.comfy_settings": "Настройки ComfyUI",
        "tb.generate": "Сгенерировать в ComfyUI",
        "tb.check_comfy": "Проверить ComfyUI",
        "tb.template": "Добавить из шаблона",
        "tb.overwrite": "Обновить в библиотеке",
        "menu.file": "Файл",
        "menu.edit": "Правка",
        "menu.library": "Библиотека",
        "menu.comfy": "ComfyUI",
        "menu.view": "Вид",
        "canvas.load_ref": "Референс-изображение...",
        "canvas.paste_ref": "Вставить референс",
        "canvas.clear_ref": "Убрать референс",
        "canvas.zoom": "Масштаб сетки",
        "canvas.ref_load_fail": "Не удалось загрузить изображение.",
        "counter.colors": "{count}/{limit} цветов",
        "set.title": "Настройки соединения с ComfyUI",
        "set.host": "Хост:",
        "set.port": "Порт:",
        "set.https": "Использовать HTTPS",
        "set.test": "Проверить соединение",
        "set.test_ok": "Соединение установлено. ComfyUI доступен.",
        "set.test_fail": "Не удалось подключиться:\n{err}",
        "set.saved": "Настройки сохранены.",
        "comfy.checking": "Проверка ComfyUI...",
        "comfy.check_title": "Проверка зависимостей ComfyUI",
        "comfy.all_ok": "Все необходимые ноды и модели установлены.",
        "comfy.unreachable": "ComfyUI недоступен по адресу {url}:\n{err}",
        "comfy.missing_header": "Отсутствует на сервере:",
        "comfy.missing_nodes": "Кастомные ноды: {items}",
        "comfy.missing_unet": "UNET-модели: {items}",
        "comfy.missing_vae": "VAE: {items}",
        "comfy.missing_clip": "CLIP: {items}",
        "comfy.missing_clip_gguf": "CLIP GGUF: {items}",
        "comfy.missing_samplers": "Семплеры: {items}",
        "comfy.generating": "Генерация в ComfyUI...",
        "comfy.gen_title": "Генерация",
        "comfy.gen_fail": "Не удалось сгенерировать:\n{err}",
        "comfy.gen_done": "Изображение сгенерировано.",
        "tab.json": "JSON",
        "tab.result": "Результат",
        "result.empty": "Здесь появится сгенерированное изображение.",
        "result.save_lib": "Сохранить в библиотеку",
        "result.save_file": "Сохранить изображение...",
        "result.saved_file": "Изображение сохранено в:\n{path}",
        "result.png_filter": "PNG изображение (*.png)",
        "comfy.workflow_missing": "Файл workflow не найден:\n{path}",
        "comfy.deps_missing_continue": "Некоторые зависимости отсутствуют. Всё равно сгенерировать?",
        "comfy.save_to_lib_q": "Сохранить сгенерированное изображение в библиотеку?",
        "draft.restore_title": "Восстановить черновик",
        "draft.restore_q": "Найден несохранённый черновик. Восстановить его?",
        "tpl.choose_title": "Шаблон элемента",
        "tpl.choose_label": "Выберите шаблон:",
        "common.cancel": "Отмена",
        "common.ok": "ОК",
        "common.close": "Закрыть",
    },
}


def ensure_translation_file():
    """Write the bundled translations to disk if no file exists yet."""
    if not LANG_FILE.exists():
        try:
            with open(LANG_FILE, "w", encoding="utf-8") as handle:
                json.dump(DEFAULT_TRANSLATIONS, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass


def load_translations():
    """Load translations from the external file, falling back to bundled defaults."""
    ensure_translation_file()
    try:
        with open(LANG_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict) or not data:
        return {lang: dict(strings) for lang, strings in DEFAULT_TRANSLATIONS.items()}
    return data


TRANSLATIONS = load_translations()
_saved_lang = load_settings().get("language", DEFAULT_LANGUAGE)
if _saved_lang in TRANSLATIONS:
    CURRENT_LANG = _saved_lang
elif DEFAULT_LANGUAGE in TRANSLATIONS:
    CURRENT_LANG = DEFAULT_LANGUAGE
else:
    CURRENT_LANG = next(iter(TRANSLATIONS))


def available_languages():
    return list(TRANSLATIONS.keys())


def tr(key):
    """Translate a key into the current language, falling back to English then the key."""
    for source in (TRANSLATIONS.get(CURRENT_LANG), TRANSLATIONS.get("en"),
                   DEFAULT_TRANSLATIONS.get(CURRENT_LANG), DEFAULT_TRANSLATIONS.get("en")):
        if source and key in source:
            return source[key]
    return key


EXAMPLE_CAPTION = {
    "high_level_description": (
        "A surreal streetwear mixed-media collage poster featuring a relaxed skateboarder mid-air "
        "against a vibrant blue sky, backed by giant puffy 3D letters spelling 'COMFY'."
    ),
    "style_description": {
        "aesthetics": "retro magazine cutout style, mixed-media digital collage, high-contrast streetwear graphic",
        "lighting": "high-contrast flash mixed with harsh midday sunlight, flat bright graphic lighting on typography",
        "photo": "vintage grainy 35mm film, distressed halftone scan textures",
        "medium": "mixed-media digital collage",
        "color_palette": ["#1E73BE", "#FDFDFD", "#C82A2A", "#657C9C", "#EFEFEF"],
    },
    "compositional_deconstruction": {
        "background": "A vibrant, clear blue sky layered with vintage grainy film texture and subtle halftone dot patterns.",
        "elements": [
            {
                "type": "obj",
                "bbox": [128, 149, 354, 810],
                "desc": "Massive 3D puffy white typography spelling 'COMFY' across the upper half of the canvas.",
                "color_palette": ["#FDFDFD", "#E0E0E0", "#D3DBE2"],
            },
            {
                "type": "obj",
                "bbox": [287, 210, 756, 819],
                "desc": "A sharp photographic cutout of a skateboarder mid-air with a distinct white cutout border.",
                "color_palette": ["#FDFDFD", "#657C9C", "#2B2B2B", "#DCA57D"],
            },
            {
                "type": "text",
                "bbox": [105, 830, 905, 980],
                "text": "BEYOND THE COMFORT ZONE",
                "desc": "Bold black sans-serif text printed on a wide torn paper strip along the lower third.",
                "color_palette": ["#EFEFEF", "#1A1A1A", "#999999"],
            },
        ],
    },
}


PROMPT_PRESETS = {
    "Adult beach photo": {
        "mode": "photo",
        "high": (
            "A nude beach photograph of an adult woman standing on pale sand near the shoreline, "
            "looking directly at the camera with the ocean horizon and clear blue sky behind her."
        ),
        "aesthetics": "natural, sunlit, candid, tasteful adult glamour photography",
        "lighting": "bright coastal daylight, clean shadows, soft reflected light from pale sand",
        "photo": "full-body beach photography, 50mm lens, natural skin texture, realistic proportions",
        "medium": "photograph",
        "palette": ["#E7B48D", "#F5D0B8", "#F2E8DA", "#62A9D5", "#F6E8C8"],
        "background": "A quiet tropical shoreline with pale sand, soft foamy waves, a distant ocean horizon, and a clear blue sky.",
        "elements": [
            {
                "type": "obj",
                "label": "Adult woman",
                "bbox": [120, 320, 950, 690],
                "desc": "An adult woman with realistic skin texture and natural posture, standing barefoot on pale sand near the shoreline.",
                "color_palette": ["#E7B48D", "#F5D0B8", "#F2E8DA"],
            }
        ],
    },
    "Boudoir editorial": {
        "mode": "photo",
        "high": "A sensual boudoir editorial photograph of an adult woman reclining on rumpled white sheets in a softly lit private bedroom.",
        "aesthetics": "intimate, elegant, editorial, warm, sensual",
        "lighting": "soft window light, gentle highlights on skin, low contrast shadows",
        "photo": "85mm portrait lens, shallow depth of field, natural skin detail, tasteful composition",
        "medium": "photograph",
        "palette": ["#F7EFE7", "#D8A181", "#8B5E4A", "#FFFFFF", "#2F2522"],
        "background": "A quiet private bedroom with rumpled white sheets, warm neutral walls, and soft morning light through sheer curtains.",
        "elements": [
            {
                "type": "obj",
                "label": "Adult model",
                "bbox": [180, 170, 880, 840],
                "desc": "An adult woman reclining on white sheets in an elegant boudoir pose, styled as a tasteful editorial photograph.",
                "color_palette": ["#F7EFE7", "#D8A181", "#8B5E4A"],
            }
        ],
    },
    "Fine-art nude": {
        "mode": "photo",
        "high": (
            "A fine-art nude studio photograph of an adult figure posed against a dark seamless backdrop, "
            "emphasizing silhouette, form, and sculptural lighting."
        ),
        "aesthetics": "minimal, sculptural, gallery-grade, refined, dramatic",
        "lighting": "single softbox side light, strong chiaroscuro, controlled studio shadows",
        "photo": "black and white fine-art photography, medium format look, crisp tonal range",
        "medium": "photograph",
        "palette": ["#111111", "#E6E0D8", "#8F8A84", "#FFFFFF"],
        "background": "A dark seamless studio backdrop with subtle falloff and no visible props.",
        "elements": [
            {
                "type": "obj",
                "label": "Adult figure",
                "bbox": [90, 250, 960, 760],
                "desc": "An adult nude figure posed with an elegant sculptural silhouette, photographed as fine art with emphasis on form and light.",
                "color_palette": ["#111111", "#E6E0D8", "#8F8A84"],
            }
        ],
    },
    "Pin-up poster": {
        "mode": "art",
        "high": "A retro adult pin-up poster illustration with a confident glamour model, bold typography, and polished mid-century advertising composition.",
        "aesthetics": "playful, glossy, retro, high-contrast, adult glamour",
        "lighting": "painted studio highlights, warm key light, crisp graphic shadows",
        "art_style": "mid-century pin-up illustration, clean outlines, poster-ready typography",
        "medium": "illustration",
        "palette": ["#F2B99B", "#E4433B", "#1D3557", "#FFF1C7", "#FFFFFF"],
        "background": "A clean vintage poster background with a radial burst, decorative stars, and generous negative space for title text.",
        "elements": [
            {
                "type": "obj",
                "label": "Pin-up model",
                "bbox": [160, 260, 900, 720],
                "desc": "A confident adult pin-up model in a stylized glamour pose, rendered with polished retro illustration details.",
                "color_palette": ["#F2B99B", "#E4433B", "#1D3557"],
            },
            {
                "type": "text",
                "label": "Title",
                "text": "MIDNIGHT GLAMOUR",
                "bbox": [70, 120, 170, 880],
                "desc": "Large cream-colored retro display lettering arched across the top of the poster.",
                "color_palette": ["#FFF1C7", "#1D3557"],
            },
        ],
    },
}


def normalize_hex(value):
    value = value.strip().upper()
    if value and not value.startswith("#"):
        value = f"#{value}"
    return value


def parse_palette(value, limit):
    colors = []
    for raw in value.split(","):
        color = normalize_hex(raw)
        if color:
            colors.append(color)
    return colors[:limit]


def palette_text(colors):
    return ", ".join(colors or [])


def clamp(value, lower=0, upper=1000):
    return max(lower, min(upper, int(round(value))))


def google_translate_text(text, target_language):
    query = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": target_language,
            "dt": "t",
            "q": text,
        }
    )
    request = urllib.request.Request(
        f"https://translate.googleapis.com/translate_a/single?{query}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return "".join(part[0] for part in payload[0] if part and part[0]).strip()


_TRANSLATION_CACHE = {}


def cached_translate(text, target_language):
    """Translate with an in-memory cache (item 13) to avoid repeat network calls."""
    key = (target_language, text)
    if key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[key]
    result = google_translate_text(text, target_language)
    if result:
        _TRANSLATION_CACHE[key] = result
    return result


# --- ComfyUI integration --------------------------------------------------

class ComfyError(Exception):
    pass


def comfy_base_url(settings):
    scheme = "https" if settings.get("comfy_https") else "http"
    return f"{scheme}://{settings.get('comfy_host', '127.0.0.1')}:{settings.get('comfy_port', 8188)}"


def comfy_get(settings, path, timeout=10):
    url = f"{comfy_base_url(settings)}{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "IdeogramPromptBuilder"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def comfy_post(settings, path, payload, timeout=15):
    url = f"{comfy_base_url(settings)}{path}"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "User-Agent": "IdeogramPromptBuilder"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def comfy_test_connection(settings):
    """Raise ComfyError if the server is not reachable, else return system stats."""
    try:
        return comfy_get(settings, "/system_stats", timeout=6)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise ComfyError(str(error))


def comfy_object_info(settings):
    try:
        return comfy_get(settings, "/object_info", timeout=20)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise ComfyError(str(error))


def _combo_values(object_info, node, input_name):
    """Return the list of allowed values for a combo input of a node, or []."""
    try:
        spec = object_info[node]["input"]
        for section in ("required", "optional"):
            if input_name in spec.get(section, {}):
                values = spec[section][input_name][0]
                return values if isinstance(values, list) else []
    except (KeyError, TypeError, IndexError):
        pass
    return []


def check_comfy_dependencies(settings):
    """Compare REQUIRED_COMFY against a live server. Returns dict of missing items."""
    info = comfy_object_info(settings)
    available_nodes = set(info.keys())
    missing = {
        "nodes": [n for n in REQUIRED_COMFY["nodes"] if n not in available_nodes],
        "unet": [], "vae": [], "clip": [], "clip_gguf": [], "samplers": [],
    }

    unet_values = set(_combo_values(info, "UNETLoader", "unet_name"))
    for model in REQUIRED_COMFY["unet"]:
        if unet_values and model not in unet_values:
            missing["unet"].append(model)

    vae_values = set(_combo_values(info, "VAELoader", "vae_name"))
    for model in REQUIRED_COMFY["vae"]:
        if vae_values and model not in vae_values:
            missing["vae"].append(model)

    clip_values = set(_combo_values(info, "CLIPLoader", "clip_name"))
    for model in REQUIRED_COMFY["clip"]:
        if clip_values and model not in clip_values:
            missing["clip"].append(model)

    gguf_values = set(_combo_values(info, "CLIPLoaderGGUF", "clip_name"))
    for model in REQUIRED_COMFY["clip_gguf"]:
        if "CLIPLoaderGGUF" not in available_nodes:
            missing["clip_gguf"].append(model)
        elif gguf_values and model not in gguf_values:
            missing["clip_gguf"].append(model)

    sampler_values = set(_combo_values(info, "KSamplerSelect", "sampler_name"))
    for sampler in REQUIRED_COMFY["samplers"]:
        if sampler_values and sampler not in sampler_values:
            missing["samplers"].append(sampler)

    return missing


def _input_name_by_slot(node, slot):
    inputs = node.get("inputs", [])
    if 0 <= slot < len(inputs):
        return inputs[slot].get("name")
    return None


WIDGET_SCALAR_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}


def _is_widget_type(type_spec):
    # Combos arrive either as a raw list of options or as the literal "COMBO" string,
    # depending on the ComfyUI version; both render a widget.
    return isinstance(type_spec, list) or type_spec in WIDGET_SCALAR_TYPES


def _make_api_entry(node, object_info):
    """Convert a UI node into an API entry, mapping widget values to input names.

    When ``object_info`` describes the node class, widget values are mapped to the
    authoritative widget input order (combos and INT/FLOAT/STRING/BOOLEAN), skipping the
    extra value that ``control_after_generate`` inputs (e.g. seeds) store. Links override
    these defaults later. Falls back to the UI ``inputs`` widget flags when the class is
    unknown.
    """
    entry = {"class_type": node["type"], "inputs": {}}
    widgets = node.get("widgets_values", []) or []
    if not isinstance(widgets, list):
        return entry
    spec = (object_info.get(node["type"], {}) or {}).get("input", {}) if object_info else {}
    if spec:
        ordered = list(spec.get("required", {}).items()) + list(spec.get("optional", {}).items())
        idx = 0
        for name, definition in ordered:
            type_spec = definition[0] if definition else None
            if not _is_widget_type(type_spec):
                continue
            if idx >= len(widgets):
                break
            entry["inputs"][name] = widgets[idx]
            idx += 1
            options = definition[1] if len(definition) > 1 and isinstance(definition[1], dict) else {}
            if options.get("control_after_generate"):
                idx += 1  # widgets_values stores the control value right after the widget
        return entry
    wi = 0
    for inp in node.get("inputs", []):
        if inp.get("widget"):
            if wi < len(widgets):
                entry["inputs"][inp["name"]] = widgets[wi]
            wi += 1
    return entry


def workflow_to_api_prompt(workflow, compact_caption, seed, object_info=None):
    """Convert the bundled UI workflow (with its subgraph) into a ComfyUI API prompt.

    Subgraph instances are flattened: internal nodes are namespaced, internal links are
    wired by id, and the subgraph boundary (instance inputs/outputs) is resolved so that
    top-level wiring crosses into the subgraph correctly. The builder's caption is injected
    into CLIPTextEncode (which prunes the original prompt-builder branch) and a fresh seed
    into RandomNoise.
    """
    subgraph_defs = {sg["id"]: sg for sg in workflow.get("definitions", {}).get("subgraphs", [])}
    prompt = {}

    def key(scope, nid):
        return str(nid) if scope is None else f"{scope}_{nid}"

    instances = []  # (instance_node, subgraph_def, scope)
    for node in workflow.get("nodes", []):
        node_type = node.get("type")
        if node_type == "MarkdownNote":
            continue
        if node_type in subgraph_defs:
            sg = subgraph_defs[node_type]
            scope = str(node["id"])
            instances.append((node, sg, scope))
            for child in sg.get("nodes", []):
                if child.get("type") == "MarkdownNote":
                    continue
                prompt[key(scope, child["id"])] = _make_api_entry(child, object_info)
        else:
            prompt[str(node["id"])] = _make_api_entry(node, object_info)

    # Wire internal subgraph links and build boundary maps per instance.
    boundary_in = {}   # scope -> {input_name: [(internal_node_id, internal_slot), ...]}
    boundary_out = {}  # scope -> {output_name: (internal_node_id, internal_slot)}
    for node, sg, scope in instances:
        internal_ids = {n["id"] for n in sg.get("nodes", [])}
        node_by_id = {n["id"]: n for n in sg.get("nodes", [])}
        link_by_id = {l["id"]: l for l in sg.get("links", [])}

        for link in sg.get("links", []):
            origin, target = link.get("origin_id"), link.get("target_id")
            if origin in internal_ids and target in internal_ids:
                tnode = node_by_id.get(target)
                name = _input_name_by_slot(tnode, link.get("target_slot", 0))
                if name:
                    prompt[key(scope, target)]["inputs"][name] = [key(scope, origin), link.get("origin_slot", 0)]

        in_map = {}
        for sg_input in sg.get("inputs", []):
            targets = []
            for lid in sg_input.get("linkIds", []):
                link = link_by_id.get(lid)
                if link and link.get("target_id") in internal_ids:
                    targets.append((link["target_id"], link.get("target_slot", 0)))
            in_map[sg_input["name"]] = targets
        boundary_in[scope] = in_map

        out_map = {}
        for sg_output in sg.get("outputs", []):
            for lid in sg_output.get("linkIds", []):
                link = link_by_id.get(lid)
                if link and link.get("origin_id") in internal_ids:
                    out_map[sg_output["name"]] = (link["origin_id"], link.get("origin_slot", 0))
                    break
        boundary_out[scope] = out_map

    instance_by_id = {str(node["id"]): (node, sg, scope) for node, sg, scope in instances}

    def resolve_source(origin_id, origin_slot):
        """Return [node_key, slot] for a link origin, crossing subgraph output boundaries."""
        sid = str(origin_id)
        if sid in instance_by_id:
            node, sg, scope = instance_by_id[sid]
            out_name = _input_name_by_slot({"inputs": node.get("outputs", [])}, origin_slot)
            internal = boundary_out.get(scope, {}).get(out_name)
            if internal:
                return [key(scope, internal[0]), internal[1]]
            return None
        return [sid, origin_slot]

    # Wire top-level links, crossing into subgraph instances where needed.
    for link in workflow.get("links", []):
        if not isinstance(link, list) or len(link) < 6:
            continue
        _lid, oid, oslot, tid, tslot, _type = link[:6]
        source = resolve_source(oid, oslot)
        if source is None:
            continue
        tkey = str(tid)
        if tkey in instance_by_id:
            node, sg, scope = instance_by_id[tkey]
            inst_input = node.get("inputs", [])
            in_name = inst_input[tslot].get("name") if 0 <= tslot < len(inst_input) else None
            for (tnode, tnslot) in boundary_in.get(scope, {}).get(in_name, []):
                name = _input_name_by_slot({"inputs": sg_node_inputs(sg, tnode)}, tnslot)
                if name:
                    prompt[key(scope, tnode)]["inputs"][name] = source
        elif tkey in prompt:
            tnode = next((n for n in workflow.get("nodes", []) if str(n.get("id")) == tkey), None)
            name = _input_name_by_slot(tnode, tslot) if tnode else None
            if name:
                prompt[tkey]["inputs"][name] = source

    # Inject builder data; overriding CLIPTextEncode.text prunes the prompt-builder branch.
    for entry in prompt.values():
        if entry["class_type"] == "CLIPTextEncode":
            entry["inputs"]["text"] = compact_caption
        elif entry["class_type"] == "RandomNoise":
            entry["inputs"]["noise_seed"] = seed
    return prompt


def sg_node_inputs(sg, node_id):
    for node in sg.get("nodes", []):
        if node.get("id") == node_id:
            return node.get("inputs", [])
    return []


def find_save_image_node(prompt):
    for node_id, entry in prompt.items():
        if entry.get("class_type") in ("SaveImage", "PreviewImage"):
            return node_id
    return None


def comfy_generate(settings, workflow, compact_caption, seed, should_cancel=None):
    """Submit the workflow to ComfyUI and return raw PNG bytes of the first output image."""
    try:
        object_info = comfy_object_info(settings)
    except ComfyError:
        object_info = None
    prompt = workflow_to_api_prompt(workflow, compact_caption, seed, object_info)
    try:
        result = comfy_post(settings, "/prompt", {"prompt": prompt})
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = error.read().decode("utf-8", "replace")
        except OSError:
            pass
        raise ComfyError(f"HTTP {error.code}: {detail[:400]}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise ComfyError(str(error))
    prompt_id = result.get("prompt_id")
    if not prompt_id:
        raise ComfyError(json.dumps(result)[:300])

    for _ in range(600):  # up to ~5 minutes
        if should_cancel and should_cancel():
            raise ComfyError("cancelled")
        try:
            history = comfy_get(settings, f"/history/{prompt_id}", timeout=10)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise ComfyError(str(error))
        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node_output in outputs.values():
                for image in node_output.get("images", []):
                    query = urllib.parse.urlencode(
                        {"filename": image["filename"], "subfolder": image.get("subfolder", ""),
                         "type": image.get("type", "output")}
                    )
                    url = f"{comfy_base_url(settings)}/view?{query}"
                    request = urllib.request.Request(url, headers={"User-Agent": "IdeogramPromptBuilder"})
                    with urllib.request.urlopen(request, timeout=30) as response:
                        return response.read()
            raise ComfyError("No image in workflow output.")
        time.sleep(0.5)
    raise ComfyError("Timed out waiting for generation.")


class GenerationThread(QThread):
    finished_ok = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, settings, workflow, caption, seed, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.workflow = workflow
        self.caption = caption
        self.seed = seed
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            data = comfy_generate(
                self.settings, self.workflow, self.caption, self.seed, lambda: self._cancel,
            )
            self.finished_ok.emit(data)
        except ComfyError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - surface anything to the UI
            self.failed.emit(str(error))


def load_library():
    """Read the prompt library from disk, returning a list of entries."""
    if LIBRARY_FILE.exists():
        try:
            with open(LIBRARY_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            return []
    return []


def save_library(entries):
    """Persist the prompt library to disk."""
    with open(LIBRARY_FILE, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)


def preview_file(entry):
    """Resolve an entry's preview image to an existing path, or None."""
    name = entry.get("preview")
    if not name:
        return None
    path = PREVIEW_DIR / name
    return path if path.exists() else None


def remove_preview_file(entry):
    """Delete the preview image associated with an entry, if any."""
    path = preview_file(entry)
    if path:
        try:
            path.unlink()
        except OSError:
            pass
    entry["preview"] = None


def attach_preview(entry, parent):
    """Pick an image file and copy it into PREVIEW_DIR as this entry's preview."""
    path, _filter = QFileDialog.getOpenFileName(
        parent,
        tr("prev.pick_title"),
        "",
        tr("prev.filter"),
    )
    if not path:
        return False
    try:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        remove_preview_file(entry)
        target_name = f"{entry['id']}{Path(path).suffix.lower() or '.png'}"
        shutil.copyfile(path, PREVIEW_DIR / target_name)
    except OSError as error:
        QMessageBox.warning(parent, tr("prev.title"), tr("prev.save_fail").format(err=error))
        return False
    entry["preview"] = target_name
    entry["updated"] = datetime.now().isoformat(timespec="seconds")
    return True


class PaletteEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, limit, parent=None):
        super().__init__(parent)
        self.limit = limit
        self._colors = []
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(tr("pal.placeholder"))
        self.add_button = QPushButton(tr("pal.add"))
        self.add_button.clicked.connect(self.add_color)
        self.line_edit.textChanged.connect(self._line_changed)
        top.addWidget(self.line_edit, 1)
        top.addWidget(self.add_button)
        layout.addLayout(top)

        bottom = QHBoxLayout()
        self.swatch_row = QHBoxLayout()
        self.swatch_row.setSpacing(6)
        self.swatch_row.addStretch()
        bottom.addLayout(self.swatch_row, 1)
        self.counter_label = QLabel("")
        self.counter_label.setStyleSheet("color:#7A847C;background:transparent;")
        bottom.addWidget(self.counter_label)
        layout.addLayout(bottom)
        self._update_counter()

    def text(self):
        return palette_text(self._colors)

    def colors(self):
        return list(self._colors)

    def set_text(self, text):
        self.set_colors(parse_palette(text, self.limit))

    def set_colors(self, colors):
        self._colors = [normalize_hex(color) for color in colors if normalize_hex(color)][: self.limit]
        self._sync_line()
        self._render_swatches()
        self.changed.emit()

    def add_color(self):
        initial = QColor(self._colors[-1] if self._colors else "#FFFFFF")
        color = QColorDialog.getColor(initial, self, tr("pal.configure"))
        if not color.isValid():
            return
        value = color.name().upper()
        if value not in self._colors and len(self._colors) < self.limit:
            self._colors.append(value)
            self._sync_line()
            self._render_swatches()
            self.changed.emit()

    def edit_color(self, index):
        color = QColorDialog.getColor(QColor(self._colors[index]), self, tr("pal.configure"))
        if not color.isValid():
            return
        self._colors[index] = color.name().upper()
        self._sync_line()
        self._render_swatches()
        self.changed.emit()

    def remove_color(self, index):
        del self._colors[index]
        self._sync_line()
        self._render_swatches()
        self.changed.emit()

    def _line_changed(self):
        if self._syncing:
            return
        self._colors = parse_palette(self.line_edit.text(), self.limit)
        self._render_swatches()
        self.changed.emit()

    def _sync_line(self):
        self._syncing = True
        self.line_edit.setText(palette_text(self._colors))
        self._syncing = False

    def _update_counter(self):
        count = len(self._colors)
        self.counter_label.setText(tr("counter.colors").format(count=count, limit=self.limit))
        # Highlight when any color is not a valid uppercase #RRGGBB or the limit is exceeded (item 10).
        invalid = count > self.limit or any(not HEX_RE.match(c) for c in self._colors)
        self.line_edit.setProperty("invalid", "true" if invalid else "false")
        self.line_edit.style().unpolish(self.line_edit)
        self.line_edit.style().polish(self.line_edit)

    def _render_swatches(self):
        self._update_counter()
        while self.swatch_row.count() > 1:
            item = self.swatch_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for index, color in enumerate(self._colors):
            holder = QWidget()
            holder.setObjectName("SwatchHolder")
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)

            swatch = QToolButton()
            swatch.setToolTip(tr("pal.swatch_tip").format(color=color))
            swatch.setFixedSize(34, 28)
            swatch.setStyleSheet(
                f"QToolButton {{ background: {color}; border: 1px solid #AEB8B1; border-radius: 6px; }}"
            )
            swatch.clicked.connect(lambda _checked=False, i=index: self.edit_color(i))
            remove = QToolButton()
            remove.setText("×")
            remove.setToolTip(tr("pal.remove"))
            remove.setFixedSize(22, 28)
            remove.clicked.connect(lambda _checked=False, i=index: self.remove_color(i))
            row.addWidget(swatch)
            row.addWidget(remove)
            self.swatch_row.insertWidget(index, holder)


class BBoxCanvas(QFrame):
    selected = pyqtSignal(int)
    bbox_changed = pyqtSignal(int, list)

    BASE_SIZE = 340

    def __init__(self):
        super().__init__()
        self.elements = []
        self.selected_index = None
        self.drag_mode = None
        self.drag_index = None
        self.drag_start = QPointF()
        self.start_bbox = None
        self.zoom = 1.0
        self.ref_pixmap = None
        self.theme = THEMES["light"]
        self.setMinimumHeight(360)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_data(self, elements, selected_index):
        self.elements = elements
        self.selected_index = selected_index
        self.update()

    def set_theme(self, theme):
        self.theme = THEMES.get(theme, THEMES["light"])
        self.update()

    def set_reference(self, pixmap):
        """Set (or clear with None) the background reference image; scales with the grid."""
        self.ref_pixmap = pixmap if pixmap and not pixmap.isNull() else None
        self.update()

    def set_zoom(self, percent):
        self.zoom = max(0.5, min(3.0, percent / 100.0))
        size = int(self.BASE_SIZE * self.zoom)
        margin = 16
        # Grow minimums so the surrounding scroll area exposes scrollbars when zoomed in.
        self.setMinimumHeight(max(360, size + margin * 2))
        self.setMinimumWidth(size + margin * 2 if self.zoom > 1.0 else 0)
        self.update()

    def canvas_rect(self):
        margin = 16
        size = self.BASE_SIZE * self.zoom
        left = max(margin, (self.width() - size) / 2)
        top = margin
        return QRectF(left, top, size, size)

    def bbox_to_rect(self, bbox):
        canvas = self.canvas_rect()
        y1, x1, y2, x2 = bbox
        return QRectF(
            canvas.left() + canvas.width() * x1 / 1000,
            canvas.top() + canvas.height() * y1 / 1000,
            canvas.width() * (x2 - x1) / 1000,
            canvas.height() * (y2 - y1) / 1000,
        )

    def point_to_bbox_delta(self, delta):
        canvas = self.canvas_rect()
        return delta.y() * 1000 / canvas.height(), delta.x() * 1000 / canvas.width()

    def hit_handle(self, point, rect):
        handles = {
            "nw": rect.topLeft(),
            "n": QPointF(rect.center().x(), rect.top()),
            "ne": rect.topRight(),
            "e": QPointF(rect.right(), rect.center().y()),
            "se": rect.bottomRight(),
            "s": QPointF(rect.center().x(), rect.bottom()),
            "sw": rect.bottomLeft(),
            "w": QPointF(rect.left(), rect.center().y()),
        }
        for name, handle in handles.items():
            if QRectF(handle.x() - 7, handle.y() - 7, 14, 14).contains(point):
                return name
        return None

    def hit_test(self, point):
        for index in range(len(self.elements) - 1, -1, -1):
            element = self.elements[index]
            if not element.get("use_bbox"):
                continue
            rect = self.bbox_to_rect(element["bbox"])
            handle = self.hit_handle(point, rect)
            if handle:
                return index, handle
            if rect.contains(point):
                return index, "move"
        return None, None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index, mode = self.hit_test(event.position())
        if index is None:
            return
        self.drag_index = index
        self.drag_mode = mode
        self.drag_start = event.position()
        self.start_bbox = list(self.elements[index]["bbox"])
        self.selected.emit(index)

    def mouseMoveEvent(self, event):
        if self.drag_index is None:
            index, mode = self.hit_test(event.position())
            self.setCursor(self.cursor_for_mode(mode))
            return

        dy, dx = self.point_to_bbox_delta(event.position() - self.drag_start)
        y1, x1, y2, x2 = self.start_bbox

        if self.drag_mode == "move":
            height = y2 - y1
            width = x2 - x1
            y1 = clamp(y1 + dy, 0, 1000 - height)
            x1 = clamp(x1 + dx, 0, 1000 - width)
            y2 = y1 + height
            x2 = x1 + width
        else:
            if "n" in self.drag_mode:
                y1 = clamp(y1 + dy, 0, y2 - MIN_BBOX_SIZE)
            if "s" in self.drag_mode:
                y2 = clamp(y2 + dy, y1 + MIN_BBOX_SIZE, 1000)
            if "w" in self.drag_mode:
                x1 = clamp(x1 + dx, 0, x2 - MIN_BBOX_SIZE)
            if "e" in self.drag_mode:
                x2 = clamp(x2 + dx, x1 + MIN_BBOX_SIZE, 1000)

        self.bbox_changed.emit(self.drag_index, [y1, x1, y2, x2])

    def mouseReleaseEvent(self, event):
        self.drag_index = None
        self.drag_mode = None
        self.start_bbox = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cursor_for_mode(self, mode):
        mapping = {
            "move": Qt.CursorShape.SizeAllCursor,
            "n": Qt.CursorShape.SizeVerCursor,
            "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor,
            "w": Qt.CursorShape.SizeHorCursor,
            "nw": Qt.CursorShape.SizeFDiagCursor,
            "se": Qt.CursorShape.SizeFDiagCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor,
            "sw": Qt.CursorShape.SizeBDiagCursor,
        }
        return mapping.get(mode, Qt.CursorShape.CrossCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas = self.canvas_rect()

        painter.setPen(QPen(QColor(self.theme["canvas_grid"]), 1))
        painter.setBrush(QColor(self.theme["canvas_bg"]))
        painter.drawRoundedRect(canvas, 10, 10)

        # Reference image fills the grid square and therefore scales with the zoom.
        if self.ref_pixmap is not None:
            scaled = self.ref_pixmap.scaled(
                int(canvas.width()), int(canvas.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            img_x = canvas.left() + (canvas.width() - scaled.width()) / 2
            img_y = canvas.top() + (canvas.height() - scaled.height()) / 2
            painter.setOpacity(0.85)
            painter.drawPixmap(int(img_x), int(img_y), scaled)
            painter.setOpacity(1.0)

        painter.setPen(QPen(QColor(self.theme["canvas_grid"]), 1))
        for step in range(1, 10):
            x = canvas.left() + canvas.width() * step / 10
            y = canvas.top() + canvas.height() * step / 10
            painter.drawLine(int(x), int(canvas.top()), int(x), int(canvas.bottom()))
            painter.drawLine(int(canvas.left()), int(y), int(canvas.right()), int(y))

        painter.setPen(QPen(QColor(self.theme["canvas_label"]), 1))
        painter.drawText(int(canvas.left()) + 10, int(canvas.top()) + 22, tr("canvas.label"))

        for index, element in enumerate(self.elements):
            if not element.get("use_bbox"):
                continue
            rect = self.bbox_to_rect(element["bbox"])
            base = QColor("#C470A8") if element["type"] == "text" else QColor(self.theme["accent"])
            fill = QColor(base)
            fill.setAlpha(32)
            painter.setBrush(fill)
            painter.setPen(QPen(base, 3 if index == self.selected_index else 2))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(base)
            painter.drawText(rect.adjusted(7, 5, -7, -5), Qt.AlignmentFlag.AlignLeft, element.get("label") or str(index + 1))

            if index == self.selected_index:
                painter.setBrush(QColor(self.theme["panel"]))
                painter.setPen(QPen(base, 2))
                for point in [
                    rect.topLeft(),
                    QPointF(rect.center().x(), rect.top()),
                    rect.topRight(),
                    QPointF(rect.right(), rect.center().y()),
                    rect.bottomRight(),
                    QPointF(rect.center().x(), rect.bottom()),
                    rect.bottomLeft(),
                    QPointF(rect.left(), rect.center().y()),
                ]:
                    painter.drawEllipse(point, 5, 5)


class ComfySettingsDialog(QDialog):
    """Edit ComfyUI connection settings, persisted to comfy_settings.json."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = dict(settings)
        self.setWindowTitle(tr("set.title"))
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.host_edit = QLineEdit(str(self.settings.get("comfy_host", "127.0.0.1")))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(int(self.settings.get("comfy_port", 8188)))
        self.https_check = QCheckBox(tr("set.https"))
        self.https_check.setChecked(bool(self.settings.get("comfy_https", False)))
        form.addRow(tr("set.host"), self.host_edit)
        form.addRow(tr("set.port"), self.port_spin)
        form.addRow("", self.https_check)
        layout.addLayout(form)

        test_row = QHBoxLayout()
        self.test_button = QPushButton(tr("set.test"))
        self.test_button.clicked.connect(self.test_connection)
        test_row.addWidget(self.test_button)
        test_row.addStretch()
        layout.addLayout(test_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {
            "comfy_host": self.host_edit.text().strip() or "127.0.0.1",
            "comfy_port": self.port_spin.value(),
            "comfy_https": self.https_check.isChecked(),
        }

    def test_connection(self):
        probe = dict(self.settings)
        probe.update(self.values())
        try:
            comfy_test_connection(probe)
        except ComfyError as error:
            QMessageBox.warning(self, tr("set.title"), tr("set.test_fail").format(err=error))
            return
        QMessageBox.information(self, tr("set.title"), tr("set.test_ok"))


class LibraryDialog(QDialog):
    """Browse the prompt library: load, rename, attach a preview, or delete entries."""

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.selected_caption = None
        self.selected_id = None
        self._filtered = []  # list of original indices currently shown
        self.setWindowTitle(tr("libd.title"))
        self.resize(900, 600)

        layout = QHBoxLayout(self)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.addWidget(QLabel(tr("libd.saved_prompts")))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("libd.search"))
        self.search_edit.textChanged.connect(lambda _t: self._refresh_list(0))
        left.addWidget(self.search_edit)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(300)
        self.list_widget.currentRowChanged.connect(self._show_details)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.use_selected())
        left.addWidget(self.list_widget, 1)
        io_row = QHBoxLayout()
        export_button = QPushButton(tr("libd.export"))
        export_button.clicked.connect(self.export_library)
        import_button = QPushButton(tr("libd.import"))
        import_button.clicked.connect(self.import_library)
        io_row.addWidget(export_button)
        io_row.addWidget(import_button)
        left.addLayout(io_row)
        layout.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(10)
        self.preview_label = QLabel(tr("libd.no_preview"))
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(360, 260)
        self.preview_label.setStyleSheet(
            "background:palette(base);border:1px solid palette(mid);border-radius:8px;"
        )
        right.addWidget(self.preview_label, 1)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        right.addWidget(self.meta_label)

        right.addWidget(QLabel(tr("libd.tags")))
        self.tags_edit = QLineEdit()
        self.tags_edit.editingFinished.connect(self._save_tags)
        right.addWidget(self.tags_edit)

        button_row = QHBoxLayout()
        self.use_button = QPushButton(tr("libd.use"))
        self.use_button.setObjectName("PrimaryButton")
        self.use_button.clicked.connect(self.use_selected)
        self.rename_button = QPushButton(tr("libd.rename"))
        self.rename_button.clicked.connect(self.rename_selected)
        button_row.addWidget(self.use_button)
        button_row.addWidget(self.rename_button)
        right.addLayout(button_row)

        button_row2 = QHBoxLayout()
        self.preview_button = QPushButton(tr("libd.set_preview"))
        self.preview_button.clicked.connect(self.set_preview)
        self.paste_preview_button = QPushButton(tr("libd.paste_preview"))
        self.paste_preview_button.clicked.connect(self.paste_preview)
        self.clear_preview_button = QPushButton(tr("libd.clear_preview"))
        self.clear_preview_button.clicked.connect(self.clear_preview)
        button_row2.addWidget(self.preview_button)
        button_row2.addWidget(self.paste_preview_button)
        button_row2.addWidget(self.clear_preview_button)
        right.addLayout(button_row2)

        button_row3 = QHBoxLayout()
        self.delete_button = QPushButton(tr("libd.delete"))
        self.delete_button.clicked.connect(self.delete_selected)
        close_button = QPushButton(tr("libd.close"))
        close_button.clicked.connect(self.reject)
        button_row3.addWidget(self.delete_button)
        button_row3.addStretch()
        button_row3.addWidget(close_button)
        right.addLayout(button_row3)
        layout.addLayout(right, 1)

        self._refresh_list(0 if self.entries else -1)

    def _matches(self, entry, query):
        if not query:
            return True
        haystack = " ".join([
            entry.get("name", ""),
            " ".join(entry.get("tags", []) or []),
            entry.get("caption", {}).get("high_level_description", ""),
        ]).lower()
        return query in haystack

    def _refresh_list(self, select_row):
        query = self.search_edit.text().strip().lower()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._filtered = []
        for index, entry in enumerate(self.entries):
            if not self._matches(entry, query):
                continue
            self._filtered.append(index)
            mark = "🖼 " if preview_file(entry) else ""
            tags = entry.get("tags", []) or []
            suffix = f"  [{', '.join(tags)}]" if tags else ""
            self.list_widget.addItem(QListWidgetItem(f"{mark}{entry.get('name') or tr('lib.untitled')}{suffix}"))
        self.list_widget.blockSignals(False)
        if 0 <= select_row < len(self._filtered):
            self.list_widget.setCurrentRow(select_row)
        else:
            self._show_details(self.list_widget.currentRow())

    def _current_entry(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._filtered):
            original = self._filtered[row]
            return original, self.entries[original]
        return None, None

    def _show_details(self, row):
        has = 0 <= row < len(self._filtered)
        for button in (self.use_button, self.rename_button, self.preview_button,
                       self.paste_preview_button, self.clear_preview_button, self.delete_button):
            button.setEnabled(has)
        self.tags_edit.setEnabled(has)
        if not has:
            self.preview_label.setText(tr("libd.no_preview"))
            self.preview_label.setPixmap(QPixmap())
            self.meta_label.setText("")
            self.tags_edit.blockSignals(True)
            self.tags_edit.clear()
            self.tags_edit.blockSignals(False)
            return
        entry = self.entries[self._filtered[row]]
        self.tags_edit.blockSignals(True)
        self.tags_edit.setText(", ".join(entry.get("tags", []) or []))
        self.tags_edit.blockSignals(False)
        path = preview_file(entry)
        if path:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.preview_label.setPixmap(
                    pixmap.scaled(
                        self.preview_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self.preview_label.setText(tr("libd.preview_unavailable"))
        else:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(tr("libd.no_preview"))
        caption = entry.get("caption", {})
        high = caption.get("high_level_description", "") or tr("libd.no_high")
        count = len(caption.get("compositional_deconstruction", {}).get("elements", []))
        updated = entry.get("updated", entry.get("created", ""))
        self.meta_label.setText(tr("libd.meta").format(updated=updated, count=count, high=high))

    def use_selected(self):
        _row, entry = self._current_entry()
        if entry is None:
            return
        self.selected_caption = entry.get("caption", {})
        self.selected_id = entry.get("id")
        self.accept()

    def rename_selected(self):
        _row, entry = self._current_entry()
        if entry is None:
            return
        name, ok = QInputDialog.getText(self, tr("libd.rename_title"), tr("libd.rename_label"), text=entry.get("name", ""))
        if ok and name.strip():
            entry["name"] = name.strip()
            entry["updated"] = datetime.now().isoformat(timespec="seconds")
            save_library(self.entries)
            self._refresh_list(self.list_widget.currentRow())

    def _save_tags(self):
        _row, entry = self._current_entry()
        if entry is None:
            return
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        if tags != (entry.get("tags") or []):
            entry["tags"] = tags
            entry["updated"] = datetime.now().isoformat(timespec="seconds")
            save_library(self.entries)
            self._refresh_list(self.list_widget.currentRow())

    def set_preview(self):
        _row, entry = self._current_entry()
        if entry is None:
            return
        if attach_preview(entry, self):
            save_library(self.entries)
            self._refresh_list(self.list_widget.currentRow())

    def paste_preview(self):
        _row, entry = self._current_entry()
        if entry is None:
            return
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            QMessageBox.information(self, tr("libd.paste_preview"), tr("libd.no_clipboard_image"))
            return
        try:
            PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
            remove_preview_file(entry)
            target_name = f"{entry['id']}.png"
            image.save(str(PREVIEW_DIR / target_name), "PNG")
        except OSError as error:
            QMessageBox.warning(self, tr("prev.title"), tr("prev.save_fail").format(err=error))
            return
        entry["preview"] = target_name
        entry["updated"] = datetime.now().isoformat(timespec="seconds")
        save_library(self.entries)
        self._refresh_list(self.list_widget.currentRow())

    def clear_preview(self):
        _row, entry = self._current_entry()
        if entry is None or not entry.get("preview"):
            return
        remove_preview_file(entry)
        entry["updated"] = datetime.now().isoformat(timespec="seconds")
        save_library(self.entries)
        self._refresh_list(self.list_widget.currentRow())

    def delete_selected(self):
        original, entry = self._current_entry()
        if entry is None:
            return
        confirm = QMessageBox.question(
            self,
            tr("libd.delete_title"),
            tr("libd.delete_q").format(name=entry.get("name", "")),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        row = self.list_widget.currentRow()
        remove_preview_file(entry)
        del self.entries[original]
        save_library(self.entries)
        self._refresh_list(min(row, len(self._filtered) - 1))

    def export_library(self):
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("libd.export"), "prompt_library.zip", tr("libd.export_filter")
        )
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("prompt_library.json",
                                 json.dumps(self.entries, ensure_ascii=False, indent=2))
                for entry in self.entries:
                    preview = preview_file(entry)
                    if preview:
                        archive.write(preview, f"prompt_previews/{preview.name}")
        except OSError as error:
            QMessageBox.warning(self, tr("libd.export"), tr("libd.export_fail").format(err=error))
            return
        QMessageBox.information(self, tr("libd.export"), tr("libd.export_done").format(path=path))

    def import_library(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, tr("libd.import"), "", tr("libd.export_filter")
        )
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "r") as archive:
                imported = json.loads(archive.read("prompt_library.json").decode("utf-8"))
                PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
                existing_ids = {e.get("id") for e in self.entries}
                added = 0
                for entry in imported:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("id") in existing_ids:
                        entry["id"] = uuid.uuid4().hex
                    preview = entry.get("preview")
                    if preview:
                        member = f"prompt_previews/{preview}"
                        if member in archive.namelist():
                            with archive.open(member) as source:
                                (PREVIEW_DIR / preview).write_bytes(source.read())
                    self.entries.append(entry)
                    existing_ids.add(entry.get("id"))
                    added += 1
            save_library(self.entries)
        except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            QMessageBox.warning(self, tr("libd.import"), tr("libd.import_fail").format(err=error))
            return
        self._refresh_list(0)
        QMessageBox.information(self, tr("libd.import"), tr("libd.import_done").format(count=added))


class PromptBuilder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.elements = []
        self.selected_index = None
        self._loading = False
        self._toolbar = None
        self.settings = load_settings()
        self.theme = self.settings.get("theme", "light")
        self._undo_stack = []
        self._redo_stack = []
        self._suspend_history = False
        self._library_entry_id = None  # id of the entry loaded from the library (item 7)
        self._gen_thread = None
        self.setWindowTitle(tr("app.title"))
        self.resize(1460, 900)
        self._build_ui()
        if not self._restore_draft():
            self.load_caption(EXAMPLE_CAPTION)
        self._push_history(initial=True)

    def set_language(self, language):
        global CURRENT_LANG
        if language == CURRENT_LANG or language not in TRANSLATIONS:
            return
        caption = self.current_caption()
        ref = self.canvas.ref_pixmap if hasattr(self, "canvas") else None
        CURRENT_LANG = language
        self.settings["language"] = language
        save_settings(self.settings)
        self.setWindowTitle(tr("app.title"))
        if self._toolbar is not None:
            self.removeToolBar(self._toolbar)
            self._toolbar.deleteLater()
            self._toolbar = None
        self._suspend_history = True
        self._build_ui()
        self.load_caption(caption)
        if ref is not None:
            self.canvas.set_reference(ref)
        self._suspend_history = False

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings["theme"] = self.theme
        save_settings(self.settings)
        self.setStyleSheet(build_stylesheet(self.theme))
        self.canvas.set_theme(self.theme)

    # --- Undo / redo (item 1) -------------------------------------------
    def _snapshot(self):
        return copy.deepcopy(self.current_caption())

    def _push_history(self, initial=False):
        if self._suspend_history:
            return
        snap = self._snapshot()
        if self._undo_stack and self._undo_stack[-1] == snap:
            return
        self._undo_stack.append(snap)
        if len(self._undo_stack) > MAX_UNDO:
            self._undo_stack.pop(0)
        if not initial:
            self._redo_stack.clear()

    def undo(self):
        if len(self._undo_stack) < 2:
            return
        self._redo_stack.append(self._undo_stack.pop())
        target = copy.deepcopy(self._undo_stack[-1])
        self._suspend_history = True
        self.load_caption(target)
        self._suspend_history = False

    def redo(self):
        if not self._redo_stack:
            return
        target = self._redo_stack.pop()
        self._undo_stack.append(copy.deepcopy(target))
        self._suspend_history = True
        self.load_caption(copy.deepcopy(target))
        self._suspend_history = False

    def install_translate_menu(self, widget):
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(lambda point, target=widget: self.show_translate_menu(target, point))

    def show_translate_menu(self, widget, point):
        menu = widget.createStandardContextMenu()
        selected = self.selected_text(widget)
        if selected:
            menu.addSeparator()
            ru_action = menu.addAction(tr("trn.to_ru"))
            en_action = menu.addAction(tr("trn.to_en"))
            ru_action.triggered.connect(lambda: self.translate_selection(widget, "ru"))
            en_action.triggered.connect(lambda: self.translate_selection(widget, "en"))
        menu.exec(widget.mapToGlobal(point))

    def selected_text(self, widget):
        if isinstance(widget, QLineEdit):
            return widget.selectedText()
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            return widget.textCursor().selectedText().replace("\u2029", "\n")
        return ""

    def replace_selection(self, widget, replacement):
        if isinstance(widget, QLineEdit):
            widget.insert(replacement)
            return
        cursor = widget.textCursor()
        cursor.insertText(replacement)
        widget.setTextCursor(cursor)

    def translate_selection(self, widget, target_language):
        selected = self.selected_text(widget)
        if not selected.strip():
            return
        try:
            translated = google_translate_text(selected, target_language)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, IndexError, KeyError, TypeError) as error:
            QMessageBox.warning(self, tr("trn.error_title"), tr("trn.error_msg").format(err=error))
            return
        if translated:
            self.replace_selection(widget, translated)

    def _make_action(self, title, callback, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _build_menubar(self):
        bar = self.menuBar()
        bar.clear()
        file_menu = bar.addMenu(tr("menu.file"))
        file_menu.addAction(self._make_action(tr("tb.example"),
                            lambda: self.load_caption(EXAMPLE_CAPTION, mark_history=True)))
        file_menu.addAction(self._make_action(tr("tb.import"), self.import_json))
        file_menu.addAction(self._make_action(tr("tb.save_json"), self.save_json, "Ctrl+S"))
        file_menu.addAction(self._make_action(tr("tb.copy"), self.copy_current_json))

        edit_menu = bar.addMenu(tr("menu.edit"))
        edit_menu.addAction(self._make_action(tr("tb.undo"), self.undo, "Ctrl+Z"))
        edit_menu.addAction(self._make_action(tr("tb.redo"), self.redo, "Ctrl+Y"))

        lib_menu = bar.addMenu(tr("menu.library"))
        lib_menu.addAction(self._make_action(tr("tb.save_library"), self.save_to_library))
        lib_menu.addAction(self._make_action(tr("tb.overwrite"), self.overwrite_in_library))
        lib_menu.addAction(self._make_action(tr("tb.library"), self.open_library))

        comfy_menu = bar.addMenu(tr("menu.comfy"))
        comfy_menu.addAction(self._make_action(tr("tb.comfy_settings"), self.open_comfy_settings))
        comfy_menu.addAction(self._make_action(tr("tb.check_comfy"), self.check_comfy))
        comfy_menu.addAction(self._make_action(tr("tb.generate"), self.generate_in_comfy))

        view_menu = bar.addMenu(tr("menu.view"))
        view_menu.addAction(self._make_action(tr("tb.theme"), self.toggle_theme))

    def _build_ui(self):
        self.setStyleSheet(build_stylesheet(self.theme))
        self._build_menubar()
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        self._toolbar = toolbar
        # Slim toolbar: the most frequent actions only; everything lives in the menus too.
        generate_action = self._make_action(tr("tb.generate"), self.generate_in_comfy)
        toolbar.addAction(generate_action)
        toolbar.addSeparator()
        toolbar.addAction(self._make_action(tr("tb.undo"), self.undo))
        toolbar.addAction(self._make_action(tr("tb.redo"), self.redo))
        toolbar.addSeparator()
        toolbar.addAction(self._make_action(tr("tb.save_library"), self.save_to_library))
        toolbar.addAction(self._make_action(tr("tb.library"), self.open_library))
        toolbar.addSeparator()
        toolbar.addAction(self._make_action(tr("tb.copy"), self.copy_current_json))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addWidget(QLabel(tr("tb.language") + " "))
        self.language_combo = QComboBox()
        for code in available_languages():
            self.language_combo.addItem(LANGUAGE_NAMES.get(code, code), code)
        current_index = self.language_combo.findData(CURRENT_LANG)
        if current_index >= 0:
            self.language_combo.setCurrentIndex(current_index)
        self.language_combo.currentIndexChanged.connect(
            lambda _i: self.set_language(self.language_combo.currentData())
        )
        toolbar.addWidget(self.language_combo)
        theme_action = QAction(tr("tb.theme"), self)
        theme_action.triggered.connect(self.toggle_theme)
        toolbar.addAction(theme_action)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_widget = QWidget()
        self.editor_layout = QVBoxLayout(editor_widget)
        self.editor_layout.setContentsMargins(16, 16, 16, 16)
        self.editor_layout.setSpacing(12)
        editor_scroll.setWidget(editor_widget)
        splitter.addWidget(editor_scroll)

        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(16, 16, 16, 16)
        output_layout.setSpacing(10)
        splitter.addWidget(output_widget)
        splitter.setSizes([900, 560])

        self._build_summary()
        self._build_presets()
        self._build_style()
        self._build_composition()
        self.editor_layout.addStretch()
        self._build_output(output_layout)

    def _build_summary(self):
        box = QGroupBox(tr("grp.high"))
        layout = QVBoxLayout(box)
        self.high_text = QTextEdit()
        self.high_text.setMinimumHeight(110)
        self.high_text.setPlaceholderText(tr("high.placeholder"))
        self.high_text.textChanged.connect(self.update_output)
        self.install_translate_menu(self.high_text)
        layout.addWidget(self.high_text)
        self.editor_layout.addWidget(box)

    def _build_presets(self):
        box = QGroupBox(tr("grp.presets"))
        layout = QGridLayout(box)
        layout.setSpacing(8)
        for index, name in enumerate(PROMPT_PRESETS):
            button = QPushButton(name)
            button.clicked.connect(lambda _checked=False, value=name: self.apply_preset(value))
            layout.addWidget(button, index // 2, index % 2)
        no_safety = QPushButton(tr("preset.no_safety"))
        no_safety.clicked.connect(self.append_no_safety_filter)
        layout.addWidget(no_safety, 2, 0, 1, 2)
        self.editor_layout.addWidget(box)

    def _build_style(self):
        box = QGroupBox(tr("grp.style"))
        layout = QVBoxLayout(box)
        mode_row = QHBoxLayout()
        self.photo_radio = QRadioButton(tr("style.photo"))
        self.art_radio = QRadioButton(tr("style.art"))
        self.photo_radio.setChecked(True)
        self.photo_radio.toggled.connect(self._style_mode_changed)
        mode_row.addWidget(self.photo_radio)
        mode_row.addWidget(self.art_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        form = QFormLayout()
        self.aesthetics_edit = QLineEdit()
        self.lighting_edit = QLineEdit()
        self.photo_edit = QLineEdit()
        self.art_style_edit = QLineEdit()
        self.medium_combo = QComboBox()
        self.medium_combo.addItems(
            ["photograph", "illustration", "3d_render", "painting", "graphic_design", "mixed-media digital collage"]
        )
        self.palette_editor = PaletteEditor(limit=16)
        self.install_translate_menu(self.aesthetics_edit)
        self.install_translate_menu(self.lighting_edit)
        self.install_translate_menu(self.photo_edit)
        self.install_translate_menu(self.art_style_edit)
        self.install_translate_menu(self.palette_editor.line_edit)

        form.addRow(tr("style.aesthetics"), self.aesthetics_edit)
        form.addRow(tr("style.lighting"), self.lighting_edit)
        self.photo_row_label = QLabel(tr("style.photo_field"))
        self.art_row_label = QLabel(tr("style.art_style"))
        form.addRow(self.photo_row_label, self.photo_edit)
        form.addRow(self.art_row_label, self.art_style_edit)
        form.addRow(tr("style.medium"), self.medium_combo)
        form.addRow(tr("style.palette"), self.palette_editor)
        layout.addLayout(form)

        for widget in [self.aesthetics_edit, self.lighting_edit, self.photo_edit, self.art_style_edit]:
            widget.textChanged.connect(self.update_output)
        self.medium_combo.currentTextChanged.connect(self.update_output)
        self.palette_editor.changed.connect(self.update_output)
        self.editor_layout.addWidget(box)

    def _build_composition(self):
        box = QGroupBox(tr("grp.composition"))
        layout = QVBoxLayout(box)
        self.background_text = QTextEdit()
        self.background_text.setMinimumHeight(95)
        self.background_text.setPlaceholderText(tr("comp.background_placeholder"))
        self.background_text.textChanged.connect(self.update_output)
        self.install_translate_menu(self.background_text)
        layout.addWidget(QLabel(tr("comp.background")))
        layout.addWidget(self.background_text)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.element_list = QListWidget()
        self.element_list.currentRowChanged.connect(self.select_element)
        self.element_list.setMinimumWidth(280)
        left = QVBoxLayout()
        add_row = QHBoxLayout()
        add_button = QPushButton(tr("comp.add_element"))
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(lambda: self.add_element())
        template_button = QPushButton(tr("tb.template"))
        template_button.clicked.connect(self.add_from_template)
        add_row.addWidget(add_button, 1)
        add_row.addWidget(template_button)
        left.addLayout(add_row)
        left.addWidget(self.element_list, 1)
        ops_row = QHBoxLayout()
        for label, callback in [
            (tr("tb.duplicate"), self.duplicate_element),
            (tr("tb.move_up"), lambda: self.move_element(-1)),
            (tr("tb.move_down"), lambda: self.move_element(1)),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            ops_row.addWidget(button)
        left.addLayout(ops_row)
        remove_button = QPushButton(tr("comp.remove_element"))
        remove_button.clicked.connect(self.delete_element)
        left.addWidget(remove_button)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        self._build_element_form(right)

        ref_row = QHBoxLayout()
        for label, callback in [
            (tr("canvas.load_ref"), self.load_reference_image),
            (tr("canvas.paste_ref"), self.paste_reference_image),
            (tr("canvas.clear_ref"), self.clear_reference_image),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            ref_row.addWidget(button)
        right.addLayout(ref_row)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel(tr("canvas.zoom")))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setValue(100)
        self.zoom_label = QLabel("100%")
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_label)
        right.addLayout(zoom_row)

        self.canvas = BBoxCanvas()
        self.canvas.set_theme(self.theme)
        self.canvas.selected.connect(self.select_element)
        self.canvas.bbox_changed.connect(self.update_bbox_from_canvas)
        canvas_scroll = QScrollArea()
        canvas_scroll.setWidgetResizable(True)
        canvas_scroll.setWidget(self.canvas)
        canvas_scroll.setMinimumHeight(380)
        right.addWidget(canvas_scroll)
        hint = QLabel(tr("comp.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{THEMES[self.theme]['muted']};background:transparent;")
        right.addWidget(hint)
        body.addLayout(right, 2)
        layout.addLayout(body)
        self.editor_layout.addWidget(box)

    def _build_element_form(self, parent_layout):
        form_box = QFrame()
        form_layout = QFormLayout(form_box)
        self.element_type = QComboBox()
        self.element_type.addItems(["obj", "text"])
        self.element_label = QLineEdit()
        self.element_text = QLineEdit()
        self.element_desc = QTextEdit()
        self.element_desc.setMinimumHeight(90)
        self.element_palette = PaletteEditor(limit=5)
        self.install_translate_menu(self.element_label)
        self.install_translate_menu(self.element_text)
        self.install_translate_menu(self.element_desc)
        self.install_translate_menu(self.element_palette.line_edit)
        self.use_bbox = QCheckBox(tr("el.use_bbox"))
        self.use_bbox.setChecked(True)
        self.bbox_spins = []
        bbox_layout = QHBoxLayout()
        for name in ["Y min", "X min", "Y max", "X max"]:
            spin = QSpinBox()
            spin.setRange(0, 1000)
            spin.setValue(200 if "min" in name else 800)
            spin.setPrefix(f"{name}: ")
            self.bbox_spins.append(spin)
            bbox_layout.addWidget(spin)

        form_layout.addRow(tr("el.type"), self.element_type)
        form_layout.addRow(tr("el.label"), self.element_label)
        form_layout.addRow(tr("el.text"), self.element_text)
        form_layout.addRow(tr("el.description"), self.element_desc)
        form_layout.addRow(tr("el.palette"), self.element_palette)
        form_layout.addRow("", self.use_bbox)
        form_layout.addRow(tr("el.bbox"), bbox_layout)
        parent_layout.addWidget(form_box)

        for widget in [self.element_type, self.element_label, self.element_text, self.use_bbox, *self.bbox_spins]:
            signal = (
                widget.currentTextChanged
                if isinstance(widget, QComboBox)
                else widget.textChanged
                if isinstance(widget, QLineEdit)
                else widget.stateChanged
                if isinstance(widget, QCheckBox)
                else widget.valueChanged
            )
            signal.connect(self.save_element_form)
        self.element_desc.textChanged.connect(self.save_element_form)
        self.element_palette.changed.connect(self.save_element_form)

    def _build_output(self, layout):
        self.output_tabs = QTabWidget()
        layout.addWidget(self.output_tabs, 1)

        # --- JSON tab ---
        json_tab = QWidget()
        json_layout = QVBoxLayout(json_tab)
        json_layout.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        title = QLabel(tr("out.title"))
        title.setStyleSheet("font-size:16px;font-weight:700;background:transparent;")
        self.pretty_radio = QRadioButton(tr("out.pretty"))
        self.compact_radio = QRadioButton(tr("out.compact"))
        self.pretty_radio.setChecked(True)
        self.pretty_radio.toggled.connect(self.update_output)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.pretty_radio)
        top.addWidget(self.compact_radio)
        json_layout.addLayout(top)

        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        json_layout.addWidget(self.output_text, 1)

        actions = QHBoxLayout()
        copy_compact = QPushButton(tr("out.copy_compact"))
        copy_compact.clicked.connect(self.copy_compact_json)
        save = QPushButton(tr("out.save_json_btn"))
        save.clicked.connect(self.save_json)
        actions.addWidget(copy_compact)
        actions.addWidget(save)
        actions.addStretch()
        json_layout.addLayout(actions)

        self.validation_list = QListWidget()
        self.validation_list.setMaximumHeight(160)
        self.validation_list.itemClicked.connect(self._on_validation_clicked)
        json_layout.addWidget(self.validation_list)
        self.output_tabs.addTab(json_tab, tr("tab.json"))

        # --- Result tab (generated image from ComfyUI, item 14) ---
        result_tab = QWidget()
        result_layout = QVBoxLayout(result_tab)
        result_layout.setContentsMargins(0, 8, 0, 0)
        self.result_label = QLabel(tr("result.empty"))
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setStyleSheet(
            "background:palette(base);border:1px solid palette(mid);border-radius:8px;"
        )
        self.result_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.result_label.setMinimumSize(0, 0)
        result_layout.addWidget(self.result_label, 1)
        result_actions = QHBoxLayout()
        self.result_save_lib = QPushButton(tr("result.save_lib"))
        self.result_save_lib.clicked.connect(lambda: self._save_generated_to_library(self._last_generated))
        self.result_save_file = QPushButton(tr("result.save_file"))
        self.result_save_file.clicked.connect(self._save_generated_to_file)
        self.result_save_lib.setEnabled(False)
        self.result_save_file.setEnabled(False)
        result_actions.addWidget(self.result_save_lib)
        result_actions.addWidget(self.result_save_file)
        result_actions.addStretch()
        result_layout.addLayout(result_actions)
        self.output_tabs.addTab(result_tab, tr("tab.result"))
        self._last_generated = None

    def _style_mode_changed(self):
        photo_mode = self.photo_radio.isChecked()
        self.photo_edit.setVisible(photo_mode)
        self.photo_row_label.setVisible(photo_mode)
        self.art_style_edit.setVisible(not photo_mode)
        self.art_row_label.setVisible(not photo_mode)
        if self._loading:
            return
        if photo_mode:
            self.medium_combo.setCurrentText("photograph")
        elif self.medium_combo.currentText() == "photograph":
            self.medium_combo.setCurrentText("illustration")
        self.update_output()

    def style_mode(self):
        return "photo" if self.photo_radio.isChecked() else "art"

    def current_caption(self):
        caption = {}
        high = self.high_text.toPlainText().strip()
        if high:
            caption["high_level_description"] = high

        style = {}
        if self.aesthetics_edit.text().strip():
            style["aesthetics"] = self.aesthetics_edit.text().strip()
        if self.lighting_edit.text().strip():
            style["lighting"] = self.lighting_edit.text().strip()
        if self.style_mode() == "photo":
            if self.photo_edit.text().strip():
                style["photo"] = self.photo_edit.text().strip()
            if self.medium_combo.currentText().strip():
                style["medium"] = self.medium_combo.currentText().strip()
        else:
            if self.medium_combo.currentText().strip():
                style["medium"] = self.medium_combo.currentText().strip()
            if self.art_style_edit.text().strip():
                style["art_style"] = self.art_style_edit.text().strip()
        if self.palette_editor.colors():
            style["color_palette"] = self.palette_editor.colors()
        if style:
            caption["style_description"] = style

        caption["compositional_deconstruction"] = {
            "background": self.background_text.toPlainText().strip(),
            "elements": [self.ordered_element(element) for element in self.elements],
        }
        return caption

    def ordered_element(self, element):
        item = {"type": element["type"]}
        if element.get("use_bbox"):
            item["bbox"] = [int(value) for value in element["bbox"]]
        if element["type"] == "text":
            item["text"] = element.get("text", "").strip()
        item["desc"] = element.get("desc", "").strip()
        colors = parse_palette(element.get("palette", ""), 5)
        if colors:
            item["color_palette"] = colors
        return item

    def update_output(self):
        if self._loading:
            return
        caption = self.current_caption()
        if self.compact_radio.isChecked():
            text = json.dumps(caption, ensure_ascii=False, separators=(",", ":"))
        else:
            text = json.dumps(caption, ensure_ascii=False, indent=2)
        self.output_text.setPlainText(text)
        self._populate_validation(self.validate_caption(caption))
        self.canvas.set_data(self.elements, self.selected_index)
        self._push_history()
        self._save_draft(caption)

    def _populate_validation(self, messages):
        colors = {"ok": "#2E8B57", "warn": "#B8860B", "bad": THEMES[self.theme]["error"]}
        self.validation_list.clear()
        for kind, message, element_index in messages:
            item = QListWidgetItem(f"[{kind.upper()}] {message}")
            item.setForeground(QColor(colors.get(kind, THEMES[self.theme]["text"])))
            item.setData(Qt.ItemDataRole.UserRole, element_index)
            self.validation_list.addItem(item)

    def _on_validation_clicked(self, item):
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None and 0 <= index < len(self.elements):
            self.select_element(index)

    def validate_caption(self, caption):
        """Return a list of (kind, message, element_index_or_None) tuples."""
        messages = []
        style = caption.get("style_description", {})
        comp = caption["compositional_deconstruction"]
        if not caption.get("high_level_description"):
            messages.append(("warn", tr("val.no_high"), None))
        if not comp.get("background"):
            messages.append(("bad", tr("val.bg_required"), None))
        if not comp.get("elements"):
            messages.append(("bad", tr("val.add_element"), None))
        if style:
            missing = [key for key in ["aesthetics", "lighting", "medium"] if not style.get(key)]
            if missing:
                messages.append(("bad", tr("val.style_missing").format(fields=", ".join(missing)), None))
            if bool(style.get("photo")) == bool(style.get("art_style")):
                messages.append(("bad", tr("val.photo_or_art"), None))
            for color in style.get("color_palette", []):
                if not HEX_RE.match(color):
                    messages.append(("bad", tr("val.hex_upper").format(color=color), None))
        for index, element in enumerate(comp.get("elements", []), start=1):
            ei = index - 1
            title = element.get("text") or tr("val.element_word").format(index=index)
            if element["type"] == "text" and not element.get("text"):
                messages.append(("bad", tr("val.text_literal").format(title=title), ei))
            if not element.get("desc"):
                messages.append(("bad", tr("val.desc_required").format(title=title), ei))
            if "bbox" in element:
                y1, x1, y2, x2 = element["bbox"]
                if y2 <= y1 or x2 <= x1:
                    messages.append(("bad", tr("val.bbox_order").format(title=title), ei))
            for color in element.get("color_palette", []):
                if not HEX_RE.match(color):
                    messages.append(("bad", tr("val.el_hex").format(title=title, color=color), ei))
        if not any(kind == "bad" for kind, _message, _idx in messages):
            messages.insert(0, ("ok", tr("val.ok"), None))
        return messages

    def add_element(self, element=None):
        element = element or {}
        normalized = {
            "type": element.get("type", "obj"),
            "label": element.get("label") or element.get("text") or f"{tr('el.element')} {len(self.elements) + 1}",
            "text": element.get("text", ""),
            "desc": element.get("desc", ""),
            "palette": palette_text(element.get("color_palette", []))
            if isinstance(element.get("color_palette"), list)
            else element.get("palette", ""),
            "use_bbox": "bbox" in element or element.get("use_bbox", True),
            "bbox": element.get("bbox", [200, 200, 800, 800]),
        }
        self.elements.append(normalized)
        self.refresh_elements(len(self.elements) - 1)

    def delete_element(self):
        if self.selected_index is None:
            return
        del self.elements[self.selected_index]
        next_index = min(self.selected_index, len(self.elements) - 1) if self.elements else None
        self.refresh_elements(next_index)

    def refresh_elements(self, selected_index=None):
        self.element_list.blockSignals(True)
        self.element_list.clear()
        for index, element in enumerate(self.elements, start=1):
            title = element.get("text") or element.get("label") or element.get("desc", "")[:32] or f"{tr('el.element')} {index}"
            self.element_list.addItem(QListWidgetItem(f"{index}. {element['type']} - {title}"))
        self.element_list.blockSignals(False)
        self.selected_index = selected_index
        if selected_index is not None and selected_index >= 0:
            self.element_list.setCurrentRow(selected_index)
        self.load_element_form()
        self.update_output()

    def select_element(self, row):
        if row < 0:
            self.selected_index = None
        else:
            self.selected_index = row
            if self.element_list.currentRow() != row:
                self.element_list.setCurrentRow(row)
        self.load_element_form()
        self.update_output()

    def load_element_form(self):
        self._loading = True
        enabled = self.selected_index is not None and bool(self.elements)
        for widget in [
            self.element_type,
            self.element_label,
            self.element_text,
            self.element_desc,
            self.element_palette,
            self.use_bbox,
            *self.bbox_spins,
        ]:
            widget.setEnabled(enabled)
        if enabled:
            element = self.elements[self.selected_index]
            self.element_type.setCurrentText(element["type"])
            self.element_label.setText(element.get("label", ""))
            self.element_text.setText(element.get("text", ""))
            self.element_desc.setPlainText(element.get("desc", ""))
            self.element_palette.set_text(element.get("palette", ""))
            self.use_bbox.setChecked(element.get("use_bbox", True))
            for spin, value in zip(self.bbox_spins, element.get("bbox", [200, 200, 800, 800])):
                spin.setValue(int(value))
        self._loading = False

    def save_element_form(self):
        if self._loading or self.selected_index is None:
            return
        self.elements[self.selected_index] = {
            "type": self.element_type.currentText(),
            "label": self.element_label.text().strip(),
            "text": self.element_text.text().strip(),
            "desc": self.element_desc.toPlainText().strip(),
            "palette": self.element_palette.text(),
            "use_bbox": self.use_bbox.isChecked(),
            "bbox": [spin.value() for spin in self.bbox_spins],
        }
        current = self.selected_index
        self.element_list.blockSignals(True)
        item = self.element_list.item(current)
        if item:
            element = self.elements[current]
            title = element.get("text") or element.get("label") or element.get("desc", "")[:32] or f"{tr('el.element')} {current + 1}"
            item.setText(f"{current + 1}. {element['type']} - {title}")
        self.element_list.blockSignals(False)
        self.update_output()

    def update_bbox_from_canvas(self, index, bbox):
        if index < 0 or index >= len(self.elements):
            return
        self.elements[index]["use_bbox"] = True
        self.elements[index]["bbox"] = bbox
        if self.selected_index != index:
            self.select_element(index)
        self._loading = True
        for spin, value in zip(self.bbox_spins, bbox):
            spin.setValue(int(value))
        self.use_bbox.setChecked(True)
        self._loading = False
        self.update_output()

    # --- Element operations (items 3, 4, 12) ----------------------------
    def duplicate_element(self):
        if self.selected_index is None:
            return
        clone = copy.deepcopy(self.elements[self.selected_index])
        clone["label"] = f"{clone.get('label', '')} copy".strip()
        self.elements.insert(self.selected_index + 1, clone)
        self.refresh_elements(self.selected_index + 1)

    def move_element(self, delta):
        if self.selected_index is None:
            return
        new_index = self.selected_index + delta
        if new_index < 0 or new_index >= len(self.elements):
            return
        items = self.elements
        items[self.selected_index], items[new_index] = items[new_index], items[self.selected_index]
        self.refresh_elements(new_index)

    def add_from_template(self):
        names = list(ELEMENT_TEMPLATES.keys())
        name, ok = QInputDialog.getItem(
            self, tr("tpl.choose_title"), tr("tpl.choose_label"), names, 0, False
        )
        if not ok or not name:
            return
        template = copy.deepcopy(ELEMENT_TEMPLATES[name])
        template.setdefault("use_bbox", True)
        self.add_element(template)

    # --- Reference image + zoom (item 5) --------------------------------
    def load_reference_image(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, tr("canvas.load_ref"), "", tr("prev.filter")
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, tr("canvas.load_ref"), tr("canvas.ref_load_fail"))
            return
        self.canvas.set_reference(pixmap)

    def paste_reference_image(self):
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            QMessageBox.information(self, tr("canvas.paste_ref"), tr("libd.no_clipboard_image"))
            return
        self.canvas.set_reference(QPixmap.fromImage(image))

    def clear_reference_image(self):
        self.canvas.set_reference(None)

    def _on_zoom_changed(self, value):
        self.zoom_label.setText(f"{value}%")
        self.canvas.set_zoom(value)

    # --- Draft autosave (item 2) ----------------------------------------
    def _save_draft(self, caption=None):
        if self._loading:
            return
        try:
            with open(DRAFT_FILE, "w", encoding="utf-8") as handle:
                json.dump(caption if caption is not None else self.current_caption(),
                          handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _restore_draft(self):
        if not DRAFT_FILE.exists():
            return False
        try:
            with open(DRAFT_FILE, "r", encoding="utf-8") as handle:
                caption = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(caption, dict) or not caption.get("compositional_deconstruction"):
            return False
        if QMessageBox.question(
            self, tr("draft.restore_title"), tr("draft.restore_q")
        ) == QMessageBox.StandardButton.Yes:
            self.load_caption(caption)
            return True
        return False

    def closeEvent(self, event):
        self._save_draft()
        if self._gen_thread is not None and self._gen_thread.isRunning():
            self._gen_thread.cancel()
            self._gen_thread.wait(2000)
        super().closeEvent(event)

    # --- ComfyUI (item 14) ----------------------------------------------
    def open_comfy_settings(self):
        dialog = ComfySettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.update(dialog.values())
            save_settings(self.settings)
            QMessageBox.information(self, tr("set.title"), tr("set.saved"))

    def _missing_deps_report(self, missing):
        sections = [
            ("nodes", "comfy.missing_nodes"), ("unet", "comfy.missing_unet"),
            ("vae", "comfy.missing_vae"), ("clip", "comfy.missing_clip"),
            ("clip_gguf", "comfy.missing_clip_gguf"), ("samplers", "comfy.missing_samplers"),
        ]
        lines = []
        for key, tkey in sections:
            if missing.get(key):
                lines.append(tr(tkey).format(items=", ".join(missing[key])))
        return lines

    def check_comfy(self):
        progress = QProgressDialog(tr("comfy.checking"), tr("common.cancel"), 0, 0, self)
        progress.setWindowTitle(tr("comfy.check_title"))
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()
        try:
            missing = check_comfy_dependencies(self.settings)
        except ComfyError as error:
            progress.close()
            QMessageBox.warning(
                self, tr("comfy.check_title"),
                tr("comfy.unreachable").format(url=comfy_base_url(self.settings), err=error),
            )
            return None
        progress.close()
        lines = self._missing_deps_report(missing)
        if not lines:
            QMessageBox.information(self, tr("comfy.check_title"), tr("comfy.all_ok"))
        else:
            QMessageBox.warning(
                self, tr("comfy.check_title"),
                tr("comfy.missing_header") + "\n\n" + "\n".join(lines),
            )
        return missing

    def generate_in_comfy(self):
        if not WORKFLOW_FILE.exists():
            QMessageBox.critical(self, tr("comfy.gen_title"),
                                 tr("comfy.workflow_missing").format(path=WORKFLOW_FILE))
            return
        missing = self.check_comfy()
        if missing is None:
            return  # server unreachable, already reported
        if any(missing.values()):
            if QMessageBox.question(
                self, tr("comfy.gen_title"), tr("comfy.deps_missing_continue")
            ) != QMessageBox.StandardButton.Yes:
                return
        try:
            with open(WORKFLOW_FILE, "r", encoding="utf-8") as handle:
                workflow = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            QMessageBox.critical(self, tr("comfy.gen_title"), tr("comfy.gen_fail").format(err=error))
            return

        caption = json.dumps(self.current_caption(), ensure_ascii=False, separators=(",", ":"))
        seed = uuid.uuid4().int % (2 ** 31)
        self._gen_progress = QProgressDialog(tr("comfy.generating"), tr("common.cancel"), 0, 0, self)
        self._gen_progress.setWindowTitle(tr("comfy.gen_title"))
        self._gen_progress.setMinimumDuration(0)
        self._gen_progress.setValue(0)

        self._gen_thread = GenerationThread(self.settings, workflow, caption, seed, self)
        self._gen_thread.finished_ok.connect(self._on_generation_done)
        self._gen_thread.failed.connect(self._on_generation_failed)
        self._gen_progress.canceled.connect(self._gen_thread.cancel)
        self._gen_thread.start()

    def _on_generation_failed(self, message):
        if getattr(self, "_gen_progress", None):
            self._gen_progress.close()
        if message != "cancelled":
            QMessageBox.warning(self, tr("comfy.gen_title"), tr("comfy.gen_fail").format(err=message))

    def _on_generation_done(self, data):
        if getattr(self, "_gen_progress", None):
            self._gen_progress.close()
        self._last_generated = data
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if not pixmap.isNull():
            self._result_pixmap = pixmap
            self._render_result()
            self.canvas.set_reference(pixmap)
        self.result_save_lib.setEnabled(True)
        self.result_save_file.setEnabled(True)
        # Bring the generated image to the foreground (item: get image into the app).
        self.output_tabs.setCurrentIndex(1)

    def _render_result(self):
        pixmap = getattr(self, "_result_pixmap", None)
        if pixmap is None or pixmap.isNull():
            return
        target = self.result_label.size()
        self.result_label.setPixmap(
            pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_result()

    def _save_generated_to_file(self):
        if not self._last_generated:
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("result.save_file"), "ideogram-result.png", tr("result.png_filter")
        )
        if not path:
            return
        try:
            with open(path, "wb") as handle:
                handle.write(self._last_generated)
        except OSError as error:
            QMessageBox.warning(self, tr("comfy.gen_title"), tr("comfy.gen_fail").format(err=error))
            return
        QMessageBox.information(self, tr("comfy.gen_title"), tr("result.saved_file").format(path=path))

    def _save_generated_to_library(self, image_data):
        caption = self.current_caption()
        default = caption.get("high_level_description", "")[:48].strip() or tr("lib.untitled")
        name, ok = QInputDialog.getText(self, tr("tb.save_library"), tr("lib.name_prompt"), text=default)
        if not ok or not name.strip():
            return
        entries = load_library()
        now = datetime.now().isoformat(timespec="seconds")
        entry = {
            "id": uuid.uuid4().hex, "name": name.strip(), "created": now, "updated": now,
            "preview": None, "tags": [], "caption": caption,
        }
        try:
            PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
            target_name = f"{entry['id']}.png"
            with open(PREVIEW_DIR / target_name, "wb") as handle:
                handle.write(image_data)
            entry["preview"] = target_name
        except OSError:
            pass
        entries.append(entry)
        try:
            save_library(entries)
        except OSError as error:
            QMessageBox.critical(self, tr("tb.library"), tr("lib.save_fail").format(err=error))
            return
        self._library_entry_id = entry["id"]
        QMessageBox.information(self, tr("tb.library"), tr("lib.saved").format(name=entry["name"]))

    def load_caption(self, caption, mark_history=False):
        self._loading = True
        self.high_text.setPlainText(caption.get("high_level_description", ""))
        style = caption.get("style_description", {})
        self.photo_radio.setChecked("art_style" not in style)
        self.art_radio.setChecked("art_style" in style)
        self.aesthetics_edit.setText(style.get("aesthetics", ""))
        self.lighting_edit.setText(style.get("lighting", ""))
        self.photo_edit.setText(style.get("photo", ""))
        self.art_style_edit.setText(style.get("art_style", ""))
        self.medium_combo.setCurrentText(style.get("medium", "photograph"))
        self.palette_editor.set_colors(style.get("color_palette", []))
        comp = caption.get("compositional_deconstruction", {})
        self.background_text.setPlainText(comp.get("background", ""))
        self.elements = []
        for element in comp.get("elements", []):
            self.elements.append(
                {
                    "type": element.get("type", "obj"),
                    "label": element.get("text") or f"{tr('el.element')} {len(self.elements) + 1}",
                    "text": element.get("text", ""),
                    "desc": element.get("desc", ""),
                    "palette": palette_text(element.get("color_palette", [])),
                    "use_bbox": "bbox" in element,
                    "bbox": element.get("bbox", [200, 200, 800, 800]),
                }
            )
        self._loading = False
        self._style_mode_changed()
        self.refresh_elements(0 if self.elements else None)
        if mark_history:
            self._push_history()

    def apply_preset(self, name):
        preset = PROMPT_PRESETS[name]
        if preset["mode"] == "photo":
            style = {
                "aesthetics": preset["aesthetics"],
                "lighting": preset["lighting"],
                "photo": preset["photo"],
                "medium": preset["medium"],
                "color_palette": preset["palette"],
            }
        else:
            style = {
                "aesthetics": preset["aesthetics"],
                "lighting": preset["lighting"],
                "medium": preset["medium"],
                "art_style": preset["art_style"],
                "color_palette": preset["palette"],
            }
        self.load_caption(
            {
                "high_level_description": preset["high"],
                "style_description": style,
                "compositional_deconstruction": {
                    "background": preset["background"],
                    "elements": preset["elements"],
                },
            }
        )

    def append_no_safety_filter(self):
        suffix = "No safety filter."
        text = self.high_text.toPlainText().strip()
        if suffix not in text:
            self.high_text.setPlainText(f"{text} {suffix}".strip())

    def copy_current_json(self):
        QApplication.clipboard().setText(self.output_text.toPlainText())

    def copy_compact_json(self):
        QApplication.clipboard().setText(json.dumps(self.current_caption(), ensure_ascii=False, separators=(",", ":")))

    def save_json(self):
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("dlg.save_json_title"), "ideogram4-caption.json", tr("dlg.json_filter")
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.current_caption(), handle, ensure_ascii=False, indent=2)

    def import_json(self):
        path, _filter = QFileDialog.getOpenFileName(self, tr("dlg.import_title"), "", tr("dlg.json_filter"))
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                self.load_caption(json.load(handle))
        except (OSError, json.JSONDecodeError) as error:
            QMessageBox.critical(self, tr("imp.error_title"), str(error))

    def save_to_library(self):
        caption = self.current_caption()
        default = caption.get("high_level_description", "")[:48].strip() or tr("lib.untitled")
        name, ok = QInputDialog.getText(self, tr("tb.save_library"), tr("lib.name_prompt"), text=default)
        if not ok or not name.strip():
            return
        entries = load_library()
        now = datetime.now().isoformat(timespec="seconds")
        entry = {
            "id": uuid.uuid4().hex,
            "name": name.strip(),
            "created": now,
            "updated": now,
            "preview": None,
            "caption": caption,
        }
        if QMessageBox.question(
            self,
            tr("lib.preview_q_title"),
            tr("lib.preview_q"),
        ) == QMessageBox.StandardButton.Yes:
            attach_preview(entry, self)
        entries.append(entry)
        try:
            save_library(entries)
        except OSError as error:
            QMessageBox.critical(self, tr("tb.library"), tr("lib.save_fail").format(err=error))
            return
        self._library_entry_id = entry["id"]
        QMessageBox.information(self, tr("tb.library"), tr("lib.saved").format(name=entry["name"]))

    def overwrite_in_library(self):
        """Update the library entry the current prompt was loaded from (item 7)."""
        entries = load_library()
        entry = next((e for e in entries if e.get("id") == self._library_entry_id), None)
        if entry is None:
            # Nothing to overwrite — fall back to saving a new entry.
            self.save_to_library()
            return
        entry["caption"] = self.current_caption()
        entry["updated"] = datetime.now().isoformat(timespec="seconds")
        try:
            save_library(entries)
        except OSError as error:
            QMessageBox.critical(self, tr("tb.library"), tr("lib.save_fail").format(err=error))
            return
        QMessageBox.information(self, tr("tb.library"), tr("lib.saved").format(name=entry.get("name", "")))

    def open_library(self):
        entries = load_library()
        dialog = LibraryDialog(entries, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_caption is not None:
            self.load_caption(dialog.selected_caption)
            self._library_entry_id = dialog.selected_id


def main():
    app = QApplication(sys.argv)
    window = PromptBuilder()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

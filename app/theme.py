"""主题配色与样式表。"""

from __future__ import annotations

from .config import Settings

LIGHT = {
    "panel": "#ffffff",
    "body": "#f6f7f9",
    "card": "#ffffff",
    "card_border": "#e4e7ec",
    "card_border_hover": "#c9d2e0",
    "text": "#1f2328",
    "muted": "#8b949e",
    "accent": "#2f6feb",
    "accent_text": "#ffffff",
    "pin": "#f0a020",
    "hover": "#eef1f6",
    "danger": "#d64545",
    "divider": "#eceff3",
    "scroll_handle": "#c7ccd4",
}

DARK = {
    "panel": "#232529",
    "body": "#1b1c1f",
    "card": "#2b2d33",
    "card_border": "#3a3d45",
    "card_border_hover": "#54596380",
    "text": "#e6e8eb",
    "muted": "#9aa0a6",
    "accent": "#6ea8fe",
    "accent_text": "#101418",
    "pin": "#f0b23c",
    "hover": "#33363d",
    "danger": "#f0736f",
    "divider": "#31343b",
    "scroll_handle": "#4a4e56",
}


def palette(settings: Settings) -> dict:
    return DARK if settings.theme == "dark" else LIGHT


def build_stylesheet(settings: Settings) -> str:
    p = palette(settings)
    fs = settings.font_size
    small = max(9, fs - 3)
    return f"""
QWidget#panel {{
    background: {p['panel']};
    border-radius: 14px;
}}
QWidget#panelBody {{
    background: {p['body']};
}}
QWidget#header {{
    background: {p['panel']};
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
}}
QWidget#footer {{
    background: {p['panel']};
    border-bottom-left-radius: 14px;
    border-bottom-right-radius: 14px;
}}
QLabel#title {{
    color: {p['text']};
    font-size: {fs + 1}px;
    font-weight: 600;
}}
QLabel#count {{
    color: {p['muted']};
    font-size: {small}px;
}}
QLabel#muted {{
    color: {p['muted']};
    font-size: {small}px;
}}
QLabel#empty {{
    color: {p['muted']};
    font-size: {fs}px;
}}
QToolButton#iconbtn {{
    background: transparent;
    color: {p['muted']};
    border: none;
    border-radius: 6px;
    padding: 3px 6px;
    font-size: {fs}px;
}}
QToolButton#iconbtn:hover {{
    background: {p['hover']};
    color: {p['text']};
}}
QToolButton#closebtn:hover {{
    background: {p['danger']};
    color: #ffffff;
}}
QToolButton#cardbtn {{
    background: transparent;
    color: {p['muted']};
    border: none;
    border-radius: 5px;
    padding: 1px 5px;
    font-size: {small + 1}px;
}}
QToolButton#cardbtn:hover {{
    background: {p['hover']};
    color: {p['text']};
}}
QToolButton#pinbtn[active="true"] {{
    color: {p['pin']};
}}
QToolButton#delbtn:hover {{
    background: {p['danger']};
    color: #ffffff;
}}
QFrame#card {{
    background: {p['card']};
    border: 1px solid {p['card_border']};
    border-radius: 10px;
}}
QFrame#card:hover {{
    border: 1px solid {p['card_border_hover']};
}}
QFrame#card[pinned="true"] {{
    border: 1px solid {p['pin']};
}}
QPlainTextEdit#notetext {{
    background: transparent;
    color: {p['text']};
    border: none;
    font-size: {fs}px;
    selection-background-color: {p['accent']};
    selection-color: {p['accent_text']};
}}
QLineEdit#tags {{
    background: transparent;
    color: {p['muted']};
    border: none;
    border-top: 1px solid {p['divider']};
    padding: 3px 1px 1px 1px;
    font-size: {small}px;
}}
QLineEdit#tags:focus {{
    color: {p['text']};
    border-top: 1px solid {p['accent']};
}}
QLineEdit#search {{
    background: {p['body']};
    color: {p['text']};
    border: 1px solid {p['card_border']};
    border-radius: 8px;
    padding: 4px 22px 4px 8px;
    font-size: {small + 2}px;
}}
QLineEdit#search:focus {{
    border: 1px solid {p['accent']};
}}
QToolButton#pagebtn {{
    background: transparent;
    color: {p['text']};
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: {small + 1}px;
}}
QToolButton#pagebtn:hover {{
    background: {p['hover']};
}}
QToolButton#pagebtn[current="true"] {{
    background: {p['accent']};
    color: {p['accent_text']};
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px 1px 2px 0px;
}}
QScrollBar::handle:vertical {{
    background: {p['scroll_handle']};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip {{
    color: {p['text']};
    background: {p['card']};
    border: 1px solid {p['card_border']};
    padding: 3px 6px;
}}
QMenu {{
    background: {p['card']};
    border: 1px solid {p['card_border']};
    color: {p['text']};
}}
QMenu::item:selected {{ background: {p['accent']}; color: {p['accent_text']}; }}
"""


def dialog_stylesheet(settings: Settings) -> str:
    p = palette(settings)
    fs = settings.font_size
    return f"""
QDialog {{ background: {p['panel']}; }}
QLabel {{ color: {p['text']}; font-size: {fs - 1}px; }}
QLabel#hint {{ color: {p['muted']}; font-size: {max(9, fs - 3)}px; }}
QGroupBox {{
    color: {p['text']};
    font-size: {fs - 1}px;
    border: 1px solid {p['card_border']};
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 10px 6px 10px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QLineEdit, QSpinBox, QComboBox {{
    background: {p['body']};
    color: {p['text']};
    border: 1px solid {p['card_border']};
    border-radius: 6px;
    padding: 4px 6px;
    font-size: {fs - 1}px;
}}
QCheckBox {{ color: {p['text']}; font-size: {fs - 1}px; spacing: 6px; }}
QPushButton {{
    background: {p['body']};
    color: {p['text']};
    border: 1px solid {p['card_border']};
    border-radius: 6px;
    padding: 5px 14px;
    font-size: {fs - 1}px;
}}
QPushButton:hover {{ background: {p['hover']}; }}
QPushButton#primary {{
    background: {p['accent']};
    color: {p['accent_text']};
    border: none;
}}
QSlider::groove:horizontal {{ background: {p['card_border']}; height: 4px; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {p['accent']}; width: 14px; margin: -5px 0; border-radius: 7px;
}}
"""

from __future__ import annotations
from typing import Iterable
import gradio as gr
from gradio.themes.base import Base
from gradio.themes.utils import colors, fonts, sizes

class ContosoCareTheme(Base):
    def __init__(
        self,
        *,
        primary_hue: colors.Color | str = colors.blue,
        secondary_hue: colors.Color | str = colors.gray,
        neutral_hue: colors.Color | str = colors.gray,
        spacing_size: sizes.Size | str = sizes.spacing_md,
        radius_size: sizes.Size | str = sizes.radius_md,
        text_size: sizes.Size | str = sizes.text_md,
        font: fonts.Font
        | str
        | Iterable[fonts.Font | str] = (
            "Segoe UI",
            "Segoe UI Web (West European)",
            "system-ui",
            "-apple-system",
            "Roboto",
            "Helvetica Neue",
            "sans-serif",
        ),
        font_mono: fonts.Font
        | str
        | Iterable[fonts.Font | str] = (
            "Consolas",
            "Monaco", 
            "Courier New",
            "ui-monospace",
            "monospace",
        ),
    ):
        super().__init__(
            primary_hue=primary_hue,
            secondary_hue=secondary_hue,
            neutral_hue=neutral_hue,
            spacing_size=spacing_size,
            radius_size=radius_size,
            text_size=text_size,
            font=font,
            font_mono=font_mono,
        )
        super().set(
            # Main background colors
            body_background_fill="#121212",
            body_background_fill_dark="#121212",
            
            # Container backgrounds
            background_fill_primary="#1c1c1c",
            background_fill_primary_dark="#1c1c1c",
            background_fill_secondary="#141414", 
            background_fill_secondary_dark="#141414",
            
            # Panel and block backgrounds
            block_background_fill="#1c1c1c",
            block_background_fill_dark="#1c1c1c",
            panel_background_fill="#1c1c1c",
            panel_background_fill_dark="#1c1c1c",
            
            # Input field backgrounds
            input_background_fill="#141414",
            input_background_fill_dark="#141414",
            input_background_fill_focus="#141414",
            input_background_fill_focus_dark="#141414",
            
            # Button backgrounds
            button_primary_background_fill="#479ef5",
            button_primary_background_fill_dark="#479ef5",
            button_primary_background_fill_hover="#3a8ce8",
            button_primary_background_fill_hover_dark="#3a8ce8",
            button_secondary_background_fill="#2c2d2c",
            button_secondary_background_fill_dark="#2c2d2c",
            button_secondary_background_fill_hover="#479ef5",
            button_secondary_background_fill_hover_dark="#479ef5",
            
            # Border colors
            border_color_primary="#2c2d2c",
            border_color_primary_dark="#2c2d2c",
            border_color_accent="#479ef5",
            border_color_accent_dark="#479ef5",
            input_border_color="#2c2d2c",
            input_border_color_dark="#2c2d2c",
            input_border_color_focus="#479ef5",
            input_border_color_focus_dark="#479ef5",
            
            # Text colors
            body_text_color="#9d9eaf",
            body_text_color_dark="#d6d6d6",
            block_title_text_color="#ffffff",
            block_title_text_color_dark="#ffffff",
            block_label_text_color="#d6d6d6",
            block_label_text_color_dark="#d6d6d6",
            block_info_text_color="#9d9eaf",
            block_info_text_color_dark="#9d9eaf",
            button_primary_text_color="#ffffff",
            button_primary_text_color_dark="#ffffff",
            button_secondary_text_color="#479ef5",
            button_secondary_text_color_dark="#ffffff",
            
            # Link colors
            link_text_color="#479ef5",
            link_text_color_dark="#479ef5",
            link_text_color_hover="#3a8ce8",
            link_text_color_hover_dark="#3a8ce8",
            
            # Tab styling
            button_cancel_background_fill="transparent",
            button_cancel_background_fill_dark="transparent",
            button_cancel_border_color="transparent",
            button_cancel_border_color_dark="transparent",
            button_cancel_text_color="#9d9eaf",
            button_cancel_text_color_dark="#9d9eaf",
            
            # Shadow and effects
            block_shadow="0 2px 8px rgba(0, 0, 0, 0.3)",
            block_shadow_dark="0 2px 8px rgba(0, 0, 0, 0.3)",
            
            # Progress bar
            loader_color="#479ef5",
            loader_color_dark="#479ef5",
            
            # Form elements
            checkbox_background_color="#141414",
            checkbox_background_color_dark="#141414", 
            checkbox_background_color_selected="#479ef5",
            checkbox_background_color_selected_dark="#479ef5",
            checkbox_border_color="#2c2d2c",
            checkbox_border_color_dark="#2c2d2c",
            checkbox_border_color_focus="#479ef5",
            checkbox_border_color_focus_dark="#479ef5",
            
            # Table styling
            table_even_background_fill="#141414",
            table_even_background_fill_dark="#141414",
            table_odd_background_fill="#1c1c1c", 
            table_odd_background_fill_dark="#1c1c1c",
            table_border_color="#2c2d2c",
            table_border_color_dark="#2c2d2c",
            
            # Code block styling
            code_background_fill="#141414",
            code_background_fill_dark="#141414",
            
            # Slider styling
            slider_color="#479ef5",
            slider_color_dark="#479ef5",
            
            # Border radius adjustments
            block_radius="8px",
            input_radius="4px",
            
            # Font weights (only valid ones)
            block_title_text_weight="600",
        )
 
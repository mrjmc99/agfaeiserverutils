# agfa-ei-utils\fun.py
import logging
from PIL import Image, ImageDraw, ImageFont
import textwrap


# Function to generate meme
def generate_meme(image_path, top_text, bottom_text, output_path, font_name='impact.ttf'):
    logging.info("Generating meme...")
    try:
        # Open the image
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)

        # Load the TrueType font
        max_width = img.width * 0.9  # Allow a 5% margin on either side
        max_font_size = img.height // 10  # Set a maximum font size based on image height

        font_size = max_font_size
        font = ImageFont.truetype(font_name, font_size)

        # Reduce font size until text fits within max_width
        def fit_text_to_width(text, font):
            while draw.textbbox((0, 0), text, font=font)[2] > max_width and font_size > 10:
                font = ImageFont.truetype(font_name, font.size - 2)
            return font

        # Adjust top text font
        font = fit_text_to_width(top_text, font)
        wrapped_top_text = textwrap.fill(top_text, width=40)

        # Draw top text
        top_y_position = 10
        draw.multiline_text(
            ((img.width - draw.textbbox((0, 0), wrapped_top_text, font=font)[2]) / 2, top_y_position),
            wrapped_top_text, fill="white", font=font, align="center"
        )

        # Adjust bottom text font
        font = fit_text_to_width(bottom_text, font)
        wrapped_bottom_text = textwrap.fill(bottom_text, width=40)

        # Draw bottom text at the bottom with a bit of padding
        bottom_y_position = img.height - draw.textbbox((0, 0), wrapped_bottom_text, font=font)[3] - 20
        draw.multiline_text(
            ((img.width - draw.textbbox((0, 0), wrapped_bottom_text, font=font)[2]) / 2, bottom_y_position),
            wrapped_bottom_text, fill="white", font=font, align="center"
        )

        # Save the meme
        img.save(output_path)
        logging.info(f"Meme saved at {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Failed to generate meme: {e}")
        raise
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from preset_messages import WELCOME_MESSAGE
from bot import process_message
from db import init_db
from dotenv import load_dotenv


load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(WELCOME_MESSAGE)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    user_id = update.effective_user.id
    text = update.message.text if update.message.text else None
    image_path = None
    
    # Handle photo if present
    if update.message.photo:
        # Get the largest photo (last in the array)
        photo = update.message.photo[-1]
        # Download the photo
        file = await context.bot.get_file(photo.file_id)
        image_path = f"data/photos/{user_id}_{photo.file_id}.jpg"
        await file.download_to_drive(image_path)
    
    # Process the message
    response = process_message(user_id, text, image_path)
    await update.message.reply_text(response)

def main() -> None:
    """Start the bot."""
    # Initialize database
    init_db()
    
    # Create the Application
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main() 
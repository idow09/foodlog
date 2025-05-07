import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from preset_messages import WELCOME_MESSAGE
from bot import process_message
from db import init_db
from dotenv import load_dotenv


load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("data/bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")
    await update.message.reply_text(WELCOME_MESSAGE)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    user = update.effective_user
    user_id = user.id
    text = update.message.text if update.message.text else None
    image_path = None

    logger.info(f"Received message from user {user_id} ({user.username})")
    if text:
        logger.info(f"Message text: {text}")

    # Handle photo if present
    if update.message.photo:
        logger.info(f"Processing photo from user {user_id}")
        # Get the largest photo (last in the array)
        photo = update.message.photo[-1]
        # Download the photo
        file = await context.bot.get_file(photo.file_id)
        image_path = f"data/photos/{user_id}_{photo.file_id}.jpg"
        await file.download_to_drive(image_path)
        logger.info(f"Photo saved to {image_path}")

    try:
        # Process the message
        response = await process_message(user_id, text, image_path)
        await update.message.reply_text(response)
        logger.info(f"Response sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error processing message for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "מצטער, אירעה שגיאה בעיבוד ההודעה. אנא נסה שוב."
        )


def main() -> None:
    """Start the bot."""
    logger.info("Starting bot")

    # Initialize database
    init_db()

    # Create the Application
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    application = Application.builder().token(token).build()
    logger.info("Application created")

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_message)
    )
    logger.info("Handlers added")

    # Start the Bot
    logger.info("Starting polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

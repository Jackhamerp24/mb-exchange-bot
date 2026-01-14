import asyncio
import json
import logging
import os
import re
from datetime import datetime, time
from pathlib import Path
from typing import Final
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import aiohttp
from bs4 import BeautifulSoup
import pytz

# Configuration
TOKEN: Final = os.getenv("TELEGRAM_BOT_TOKEN", "7686247051:AAGPNEXLaWlKj0auBgVfpvpZXACYLwbgz0Y")
BOT_USERNAME: Final = "@MBbankExchangeRate_bot"
EXCHANGE_URL: Final = "https://webgia.com/ty-gia/mbbank/"
SUBSCRIBERS_FILE: Final = "subscribers.json"

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store user IDs who want daily notifications
subscribed_users = set()


def load_subscribers():
    """Load subscribed users from file"""
    global subscribed_users
    try:
        if Path(SUBSCRIBERS_FILE).exists():
            with open(SUBSCRIBERS_FILE, 'r') as f:
                subscribed_users = set(json.load(f))
            logger.info(f"Loaded {len(subscribed_users)} subscribers from file")
    except Exception as e:
        logger.error(f"Error loading subscribers: {e}")
        subscribed_users = set()


def save_subscribers():
    """Save subscribed users to file"""
    try:
        with open(SUBSCRIBERS_FILE, 'w') as f:
            json.dump(list(subscribed_users), f)
        logger.info(f"Saved {len(subscribed_users)} subscribers to file")
    except Exception as e:
        logger.error(f"Error saving subscribers: {e}")


async def scrape_aud_rate() -> dict:
    """
    Scrapes webgia.com for MB Bank AUD to VND exchange rate.
    Returns a dict with rate and status.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            }
            
            async with session.get(EXCHANGE_URL, headers=headers, timeout=30) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find the table with exchange rates
                    table = soup.find('table')
                    
                    if not table:
                        return {
                            'success': False,
                            'error': 'Exchange rate table not found on page'
                        }
                    
                    # Find all rows
                    rows = table.find_all('tr')
                    
                    for row in rows:
                        cells = row.find_all('td')
                        
                        # We need at least 6 columns: Currency, Name, Buy Cash, Buy Transfer, Sell Cash, Sell Transfer
                        if len(cells) >= 6:
                            # Check if this is the AUD row
                            currency_code = cells[0].get_text(strip=True)
                            
                            if 'AUD' in currency_code.upper():
                                # Column 5 is "Bán chuyển khoản" (Sell Transfer)
                                selling_rate = cells[5].get_text(strip=True)
                                
                                # Clean up the rate - remove any non-numeric characters except comma and dot
                                selling_rate = re.sub(r'[^\d,.]', '', selling_rate)
                                
                                # Check if we got a valid rate
                                if selling_rate and selling_rate != 'webgia.com':
                                    return {
                                        'success': True,
                                        'rate': selling_rate,
                                        'currency': 'AUD'
                                    }
                    
                    return {
                        'success': False,
                        'error': 'AUD rate not found in the table. The website might have changed its structure.'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Failed to fetch page. HTTP Status: {response.status}'
                    }
    except asyncio.TimeoutError:
        logger.error("Timeout while fetching exchange rate")
        return {
            'success': False,
            'error': 'Request timeout. Please try again later.'
        }
    except Exception as e:
        logger.error(f"Error scraping exchange rate: {e}")
        return {
            'success': False,
            'error': f'Error: {str(e)}'
        }


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    await update.message.reply_text(
        "👋 <b>Welcome to MB Bank Exchange Rate Bot!</b>\n\n"
        "This bot helps you monitor the AUD to VND exchange rate from MB Bank.\n\n"
        "<b>Available commands:</b>\n"
        "💱 /rate - Get current AUD to VND rate\n"
        "🔔 /subscribe - Get daily rate updates at 9:00 AM (VN time)\n"
        "🔕 /unsubscribe - Stop daily updates\n"
        "❓ /help - Show detailed help\n\n"
        "Start by typing /rate to see the current exchange rate!",
        parse_mode='HTML'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command"""
    await update.message.reply_text(
        "🤖 <b>MB Bank Exchange Rate Bot - Help</b>\n\n"
        "<b>Commands:</b>\n\n"
        "💱 <b>/rate</b>\n"
        "Get the current AUD to VND exchange rate (Bán ra - Chuyển khoản)\n\n"
        "🔔 <b>/subscribe</b>\n"
        "Subscribe to daily rate notifications at 9:00 AM Vietnam time\n\n"
        "🔕 <b>/unsubscribe</b>\n"
        "Unsubscribe from daily notifications\n\n"
        "❓ <b>/help</b>\n"
        "Show this help message\n\n"
        "<b>About the Rate:</b>\n"
        "The bot fetches the 'Bán ra (Chuyển khoản)' rate, which is the selling/transfer rate "
        "from MB Bank. This is the rate at which the bank sells AUD for VND in transfers.\n\n"
        "<b>Note:</b> Exchange rates are updated regularly and may change throughout the day.",
        parse_mode='HTML'
    )


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /rate command - fetch and display current rate"""
    await update.message.reply_text("⏳ Fetching current AUD to VND rate from MB Bank...")
    
    result = await scrape_aud_rate()
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')
    
    if result['success']:
        message = (
            f"💱 <b>MB Bank Exchange Rate</b>\n\n"
            f"🇦🇺 Currency: <b>AUD → VND</b> 🇻🇳\n"
            f"📊 Rate (Bán ra - Chuyển khoản):\n"
            f"<b>{result['rate']} VND</b>\n\n"
            f"🕐 Updated: {current_time}\n"
            f"📍 Source: MB Bank via WebGia.com"
        )
    else:
        message = (
            f"❌ <b>Error Fetching Rate</b>\n\n"
            f"{result['error']}\n\n"
            f"Please try again later."
        )
    
    await update.message.reply_text(message, parse_mode='HTML')


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /subscribe command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "User"
    
    if user_id in subscribed_users:
        await update.message.reply_text(
            f"✅ Hi {user_name}! You are already subscribed to daily rate updates.\n\n"
            "You will receive notifications every day at 9:00 AM (Vietnam time)."
        )
    else:
        subscribed_users.add(user_id)
        save_subscribers()
        await update.message.reply_text(
            f"✅ <b>Successfully subscribed!</b>\n\n"
            f"Hi {user_name}, you will now receive daily AUD to VND exchange rate updates "
            f"at 9:00 AM (Vietnam time).\n\n"
            f"Use /unsubscribe anytime to stop receiving updates.",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} ({user_name}) subscribed to daily updates")


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /unsubscribe command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "User"
    
    if user_id in subscribed_users:
        subscribed_users.remove(user_id)
        save_subscribers()
        await update.message.reply_text(
            f"✅ <b>Successfully unsubscribed</b>\n\n"
            f"Hi {user_name}, you will no longer receive daily rate updates.\n\n"
            f"Use /subscribe anytime to start receiving updates again.",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} ({user_name}) unsubscribed from daily updates")
    else:
        await update.message.reply_text(
            f"ℹ️ Hi {user_name}, you are not currently subscribed to daily updates.\n\n"
            f"Use /subscribe to start receiving daily rate updates."
        )


async def send_daily_rate(context: ContextTypes.DEFAULT_TYPE):
    """Send daily exchange rate to all subscribed users"""
    if not subscribed_users:
        logger.info("No subscribed users for daily rate update")
        return
    
    logger.info(f"Sending daily rate to {len(subscribed_users)} subscribers")
    
    result = await scrape_aud_rate()
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')
    
    if result['success']:
        message = (
            f"🌅 <b>Daily Exchange Rate Update</b>\n\n"
            f"💱 MB Bank - AUD → VND\n"
            f"📊 Rate (Bán ra - Chuyển khoản):\n"
            f"<b>{result['rate']} VND</b>\n\n"
            f"🕐 {current_time} (Vietnam Time)\n"
            f"📍 Source: MB Bank\n\n"
            f"💡 Use /rate to check anytime!"
        )
    else:
        message = (
            f"⚠️ <b>Daily Rate Update - Error</b>\n\n"
            f"Unable to fetch today's rate:\n{result['error']}\n\n"
            f"Use /rate to try again manually."
        )
    
    success_count = 0
    failed_count = 0
    
    for user_id in subscribed_users.copy():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
            success_count += 1
            await asyncio.sleep(0.1)  # Small delay to avoid rate limiting
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            failed_count += 1
    
    logger.info(f"Daily rate sent: {success_count} successful, {failed_count} failed")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Main function to run the bot"""
    # Load existing subscribers
    load_subscribers()
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Schedule daily job at 9:00 AM Vietnam time
    job_queue = application.job_queue
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    scheduled_time = time(hour=9, minute=0, tzinfo=vietnam_tz)
    
    job_queue.run_daily(
        send_daily_rate,
        time=scheduled_time,
        name="daily_exchange_rate"
    )
    
    logger.info("=" * 60)
    logger.info("MB Bank Exchange Rate Bot started successfully!")
    logger.info(f"Bot username: {BOT_USERNAME}")
    logger.info(f"Loaded {len(subscribed_users)} subscribers")
    logger.info(f"Daily notifications scheduled for 9:00 AM Vietnam time")
    logger.info(f"Using alternative source: {EXCHANGE_URL}")
    logger.info("=" * 60)
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

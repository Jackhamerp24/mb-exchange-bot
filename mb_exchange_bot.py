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
import requests
from bs4 import BeautifulSoup
import pytz

# Configuration
TOKEN: Final = os.getenv("TELEGRAM_BOT_TOKEN", "7686247051:AAGPNEXLaWlKj0auBgVfpvpZXACYLwbgz0Y")
BOT_USERNAME: Final = "@MBbankExchangeRate_bot"
CHOGIA_URL: Final = "https://chogia.vn/ngoai-te/aud/"
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


def scrape_mbbank_rate_chogia() -> dict:
    """
    Scrapes chogia.vn for MB Bank AUD rate
    This site aggregates rates from all Vietnamese banks!
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(CHOGIA_URL, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the table with bank rates
            table = soup.find('table')
            
            if table:
                rows = table.find_all('tr')
                
                for row in rows:
                    cells = row.find_all('td')
                    
                    if len(cells) >= 4:
                        # First column is bank name
                        bank_cell = cells[0]
                        
                        # Check if this is MB Bank row
                        if bank_cell:
                            bank_link = bank_cell.find('a')
                            if bank_link and 'mbbank' in bank_link.get('href', ''):
                                # Found MB Bank row!
                                # Columns: Bank Name | Mua vào | Bán ra | Chuyển khoản
                                
                                buy_cash = cells[1].get_text(strip=True)  # Mua vào (tiền mặt)
                                sell_cash = cells[2].get_text(strip=True)  # Bán ra (tiền mặt)
                                sell_transfer = cells[3].get_text(strip=True)  # Chuyển khoản
                                
                                # Clean up the rates
                                buy_cash = re.sub(r'[^\d,.]', '', buy_cash)
                                sell_cash = re.sub(r'[^\d,.]', '', sell_cash)
                                sell_transfer = re.sub(r'[^\d,.]', '', sell_transfer)
                                
                                if sell_transfer and len(sell_transfer) > 3:
                                    return {
                                        'success': True,
                                        'rate_transfer': sell_transfer,
                                        'rate_cash': sell_cash,
                                        'buy_rate': buy_cash,
                                        'source': 'MB Bank (via ChoGia.vn)'
                                    }
            
            return {
                'success': False,
                'error': 'Could not find MB Bank rate in table'
            }
        else:
            return {
                'success': False,
                'error': f'Failed to fetch page. HTTP Status: {response.status_code}'
            }
            
    except Exception as e:
        logger.error(f"Error scraping chogia.vn: {e}")
        return {
            'success': False,
            'error': f'Error: {str(e)}'
        }


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    await update.message.reply_text(
        "👋 <b>Welcome to MB Bank Exchange Rate Bot!</b>\n\n"
        "This bot monitors the AUD to VND exchange rate from MB Bank.\n\n"
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
        "Get the current AUD to VND exchange rate from MB Bank\n\n"
        "🔔 <b>/subscribe</b>\n"
        "Subscribe to daily rate notifications at 9:00 AM Vietnam time\n\n"
        "🔕 <b>/unsubscribe</b>\n"
        "Unsubscribe from daily notifications\n\n"
        "❓ <b>/help</b>\n"
        "Show this help message\n\n"
        "<b>Rate Information:</b>\n"
        "• <b>Bán ra (Chuyển khoản)</b> - Transfer selling rate (main rate)\n"
        "• <b>Bán ra (Tiền mặt)</b> - Cash selling rate\n"
        "• <b>Mua vào</b> - Buying rate\n\n"
        "<b>Source:</b> Data from ChoGia.vn, updated from MB Bank",
        parse_mode='HTML'
    )


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /rate command - fetch and display current rate"""
    await update.message.reply_text("⏳ Fetching current AUD to VND rate from MB Bank...")
    
    # Run synchronous scraping in executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scrape_mbbank_rate_chogia)
    
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')
    
    if result['success']:
        message = (
            f"💱 <b>MB Bank Exchange Rate</b>\n\n"
            f"🇦🇺 Currency: <b>AUD → VND</b> 🇻🇳\n\n"
            f"📊 <b>Bán ra (Chuyển khoản):</b>\n"
            f"<b>{result['rate_transfer']}</b> VND\n\n"
            f"💵 <b>Bán ra (Tiền mặt):</b>\n"
            f"{result['rate_cash']} VND\n\n"
            f"💰 <b>Mua vào:</b>\n"
            f"{result['buy_rate']} VND\n\n"
            f"🕐 Updated: {current_time}\n"
            f"📍 Source: {result['source']}"
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
    
    # Run synchronous scraping in executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scrape_mbbank_rate_chogia)
    
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')
    
    if result['success']:
        message = (
            f"🌅 <b>Daily Exchange Rate Update</b>\n\n"
            f"💱 MB Bank - AUD → VND\n\n"
            f"📊 <b>Bán ra (Chuyển khoản):</b>\n"
            f"<b>{result['rate_transfer']}</b> VND\n\n"
            f"🕐 {current_time} (Vietnam Time)\n"
            f"📍 Source: {result['source']}\n\n"
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
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            failed_count += 1
    
    logger.info(f"Daily rate sent: {success_count} successful, {failed_count} failed")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Main function to run the bot"""
    load_subscribers()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    
    application.add_error_handler(error_handler)
    
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
    logger.info(f"Using ChoGia.vn as source: {CHOGIA_URL}")
    logger.info("=" * 60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

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
                                        'source': 'MB Bank (qua ChoGia.vn)'
                                    }
            
            return {
                'success': False,
                'error': 'Không tìm thấy tỷ giá MB Bank trong bảng'
            }
        else:
            return {
                'success': False,
                'error': f'Không thể tải trang. HTTP Status: {response.status_code}'
            }
            
    except Exception as e:
        logger.error(f"Error scraping chogia.vn: {e}")
        return {
            'success': False,
            'error': f'Lỗi: {str(e)}'
        }


def format_number(number: float) -> str:
    """Format number with thousand separators"""
    return "{:,.0f}".format(number).replace(',', '.')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    await update.message.reply_text(
        "👋 <b>Chào mừng đến với Bot Tỷ Giá MB Bank!</b>\n\n"
        "Bot này giúp bạn theo dõi tỷ giá AUD sang VND của MB Bank.\n\n"
        "<b>Các lệnh có sẵn:</b>\n"
        "💱 /tygia - Xem tỷ giá AUD hiện tại\n"
        "🔄 /chuyendoi [số tiền] - Chuyển đổi AUD sang VND\n"
        "   Ví dụ: /chuyendoi 2000\n"
        "🔔 /dangky - Nhận thông báo tỷ giá hàng ngày lúc 9:00 sáng\n"
        "🔕 /huy - Ngừng nhận thông báo hàng ngày\n"
        "❓ /trogiup - Hiển thị trợ giúp chi tiết\n\n"
        "Bắt đầu bằng cách gõ /tygia để xem tỷ giá hiện tại!",
        parse_mode='HTML'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command"""
    await update.message.reply_text(
        "🤖 <b>Bot Tỷ Giá MB Bank - Trợ Giúp</b>\n\n"
        "<b>Các lệnh:</b>\n\n"
        "💱 <b>/tygia</b>\n"
        "Xem tỷ giá AUD sang VND hiện tại của MB Bank\n\n"
        "🔄 <b>/chuyendoi [số tiền]</b>\n"
        "Tính toán số tiền VND cần trả khi mua AUD từ MB Bank\n"
        "Ví dụ: /chuyendoi 2000 (mua 2,000 AUD)\n\n"
        "🔔 <b>/dangky</b>\n"
        "Đăng ký nhận thông báo tỷ giá hàng ngày lúc 9:00 sáng\n\n"
        "🔕 <b>/huy</b>\n"
        "Hủy đăng ký nhận thông báo hàng ngày\n\n"
        "❓ <b>/trogiup</b>\n"
        "Hiển thị trợ giúp này\n\n"
        "<b>Thông tin về tỷ giá:</b>\n"
        "• <b>Bán ra (Chuyển khoản)</b> - Giá MB Bank bán AUD (chuyển khoản)\n"
        "• <b>Bán ra (Tiền mặt)</b> - Giá MB Bank bán AUD (tiền mặt)\n"
        "• <b>Mua vào</b> - Giá MB Bank mua AUD từ bạn\n\n"
        "<b>Nguồn dữ liệu:</b> ChoGia.vn, cập nhật từ MB Bank",
        parse_mode='HTML'
    )


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /tygia command - fetch and display current rate"""
    await update.message.reply_text("⏳ Đang lấy tỷ giá AUD sang VND từ MB Bank...")
    
    # Run synchronous scraping in executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scrape_mbbank_rate_chogia)
    
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M:%S')
    
    if result['success']:
        message = (
            f"💱 <b>Tỷ Giá MB Bank</b>\n\n"
            f"🇦🇺 Ngoại tệ: <b>AUD → VND</b> 🇻🇳\n\n"
            f"📊 <b>Bán ra (Chuyển khoản):</b>\n"
            f"<b>{result['rate_transfer']}</b> VND\n\n"
            f"💵 <b>Bán ra (Tiền mặt):</b>\n"
            f"{result['rate_cash']} VND\n\n"
            f"💰 <b>Mua vào:</b>\n"
            f"{result['buy_rate']} VND\n\n"
            f"🕐 Cập nhật: {current_time}\n"
            f"📍 Nguồn: {result['source']}\n\n"
            f"💡 Dùng /chuyendoi [số tiền] để tính toán\n"
            f"Ví dụ: /chuyendoi 2000"
        )
    else:
        message = (
            f"❌ <b>Lỗi khi lấy tỷ giá</b>\n\n"
            f"{result['error']}\n\n"
            f"Vui lòng thử lại sau."
        )
    
    await update.message.reply_text(message, parse_mode='HTML')


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /chuyendoi command - convert AUD to VND"""
    
    # Check if amount is provided
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "⚠️ <b>Vui lòng nhập số tiền AUD cần chuyển đổi</b>\n\n"
            "Cách dùng: /chuyendoi [số tiền]\n\n"
            "Ví dụ:\n"
            "• /chuyendoi 2000\n"
            "• /chuyendoi 5000\n"
            "• /chuyendoi 10000",
            parse_mode='HTML'
        )
        return
    
    # Parse the amount
    try:
        amount_str = context.args[0].replace(',', '').replace('.', '')
        amount = float(amount_str)
        
        if amount <= 0:
            await update.message.reply_text(
                "⚠️ Số tiền phải lớn hơn 0!\n\n"
                "Vui lòng nhập số tiền hợp lệ."
            )
            return
            
    except ValueError:
        await update.message.reply_text(
            "⚠️ <b>Số tiền không hợp lệ!</b>\n\n"
            "Vui lòng nhập số tiền là một con số.\n\n"
            "Ví dụ: /chuyendoi 2000",
            parse_mode='HTML'
        )
        return
    
    # Fetch current rate
    await update.message.reply_text("⏳ Đang lấy tỷ giá hiện tại...")
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scrape_mbbank_rate_chogia)
    
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M:%S')
    
    if result['success']:
        # Parse the rate
        rate_str = result['rate_transfer'].replace(',', '').replace('.', '')
        rate = float(rate_str)
        
        # Calculate VND amount needed
        vnd_amount = amount * rate
        
        message = (
            f"💱 <b>Chuyển Đổi AUD sang VND</b>\n\n"
            f"🇦🇺 Số tiền AUD muốn mua: <b>{format_number(amount)} AUD</b>\n\n"
            f"📊 Tỷ giá MB Bank (Chuyển khoản):\n"
            f"<b>{result['rate_transfer']}</b> VND/AUD\n\n"
            f"💰 <b>Số tiền VND cần trả:</b>\n"
            f"<code>{format_number(vnd_amount)} VND</code>\n\n"
            f"📝 <b>Chi tiết tính toán:</b>\n"
            f"{format_number(amount)} AUD × {result['rate_transfer']} = {format_number(vnd_amount)} VND\n\n"
            f"🕐 Tỷ giá lúc: {current_time}\n"
            f"📍 Nguồn: {result['source']}\n\n"
            f"⚠️ <i>Lưu ý: Đây là tỷ giá tham khảo. Tỷ giá thực tế có thể thay đổi khi giao dịch.</i>"
        )
    else:
        message = (
            f"❌ <b>Không thể lấy tỷ giá</b>\n\n"
            f"{result['error']}\n\n"
            f"Vui lòng thử lại sau."
        )
    
    await update.message.reply_text(message, parse_mode='HTML')


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /dangky command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Bạn"
    
    if user_id in subscribed_users:
        await update.message.reply_text(
            f"✅ Xin chào {user_name}! Bạn đã đăng ký nhận thông báo tỷ giá hàng ngày.\n\n"
            "Bạn sẽ nhận thông báo mỗi ngày lúc 9:00 sáng (giờ Việt Nam)."
        )
    else:
        subscribed_users.add(user_id)
        save_subscribers()
        await update.message.reply_text(
            f"✅ <b>Đăng ký thành công!</b>\n\n"
            f"Xin chào {user_name}, từ giờ bạn sẽ nhận thông báo tỷ giá AUD sang VND "
            f"mỗi ngày lúc 9:00 sáng (giờ Việt Nam).\n\n"
            f"Dùng /huy để ngừng nhận thông báo.",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} ({user_name}) subscribed to daily updates")


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /huy command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Bạn"
    
    if user_id in subscribed_users:
        subscribed_users.remove(user_id)
        save_subscribers()
        await update.message.reply_text(
            f"✅ <b>Hủy đăng ký thành công</b>\n\n"
            f"Xin chào {user_name}, bạn sẽ không còn nhận thông báo tỷ giá hàng ngày.\n\n"
            f"Dùng /dangky để đăng ký lại.",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} ({user_name}) unsubscribed from daily updates")
    else:
        await update.message.reply_text(
            f"ℹ️ Xin chào {user_name}, bạn chưa đăng ký nhận thông báo hàng ngày.\n\n"
            f"Dùng /dangky để bắt đầu nhận thông báo."
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
    
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M:%S')
    
    if result['success']:
        message = (
            f"🌅 <b>Thông Báo Tỷ Giá Hàng Ngày</b>\n\n"
            f"💱 MB Bank - AUD → VND\n\n"
            f"💵 <b>Bán ra (Tiền mặt):</b>\n"
            f"{result['rate_cash']} VND\n\n"
            f"🕐 {current_time} (Giờ Việt Nam)\n"
            f"📍 Nguồn: {result['source']}\n\n"
            f"💡 Dùng /tygia để kiểm tra bất cứ lúc nào!\n"
            f"💡 Dùng /chuyendoi [số tiền] để tính toán!"
        )
    else:
        message = (
            f"⚠️ <b>Thông Báo Tỷ Giá - Có Lỗi</b>\n\n"
            f"Không thể lấy tỷ giá hôm nay:\n{result['error']}\n\n"
            f"Dùng /tygia để thử lại thủ công."
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
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("trogiup", help_command))
    application.add_handler(CommandHandler("help", help_command))  # English alias
    application.add_handler(CommandHandler("tygia", rate_command))
    application.add_handler(CommandHandler("rate", rate_command))  # English alias
    application.add_handler(CommandHandler("chuyendoi", convert_command))
    application.add_handler(CommandHandler("convert", convert_command))  # English alias
    application.add_handler(CommandHandler("dangky", subscribe_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))  # English alias
    application.add_handler(CommandHandler("huy", unsubscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))  # English alias
    
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
    logger.info("Bot Tỷ Giá MB Bank khởi động thành công!")
    logger.info(f"Tên bot: {BOT_USERNAME}")
    logger.info(f"Đã tải {len(subscribed_users)} người đăng ký")
    logger.info(f"Thông báo hàng ngày vào lúc 9:00 sáng giờ Việt Nam")
    logger.info(f"Sử dụng nguồn: {CHOGIA_URL}")
    logger.info("=" * 60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

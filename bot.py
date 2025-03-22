import os
import json
import logging
import asyncio
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Setup
load_dotenv()
logging.basicConfig(
    filename='logs/error.log',
    level=logging.ERROR,
    format='%(asctime)s - %(message)s'
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USERS = [int(id) for id in os.getenv("ALLOWED_USER_IDS").split(",")]
CONFIG = {
    'target_url': os.getenv("TARGET_URL"),
    'voucher': os.getenv("VOUCHER_CODE"),
    'order_time': os.getenv("ORDER_TIME")
}

# Scheduler
scheduler = AsyncIOScheduler()

class BlibliAuto:
    def __init__(self, account_file):
        self.account = account_file
        self.driver = self.setup_driver()
        self.retry_count = 0

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.binary_location = "/data/data/com.termux/files/usr/bin/chromium"
        return webdriver.Chrome(options=options)

    async def send_telegram(self, message: str, chat_id: int):
        try:
            await Bot(token=TELEGRAM_TOKEN).send_message(
                chat_id=chat_id,
                text=f"🤖 [BLIBLI BOT]\n{message}"
            )
        except Exception as e:
            logging.error(f"Telegram Error: {str(e)}")

    async def process_order(self, chat_id: int):
        try:
            # Load Cookies
            with open(f"cookies/{self.account}", 'r') as f:
                cookies = json.load(f)
            
            self.driver.get("https://www.blibli.com")
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            
            # Step 1: Buka Produk
            self.driver.get(CONFIG['target_url'])
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Beli Sekarang')]"))
            ).click()
            
            # Step 2: Klaim Voucher
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "voucherCode"))
            ).send_keys(CONFIG['voucher'])
            self.driver.find_element(By.XPATH, "//button[contains(., 'Pakai')]").click()
            
            # Step 3: Pembayaran
            payment_method = json.load(open('config.json'))['payment_method']
            self.driver.find_element(By.XPATH, f"//div[contains(., '{payment_method}')]").click()
            self.driver.find_element(By.ID, "confirmPayment").click()
            
            await self.send_telegram(f"✅ {self.account} SUCCESS!", chat_id)
            
        except Exception as e:
            self.retry_count += 1
            if self.retry_count < 3:
                await self.process_order(chat_id)
            else:
                await self.send_telegram(f"❌ {self.account} FAILED: {str(e)}", chat_id)
                logging.error(f"Order Error ({self.account}): {str(e)}")
        finally:
            self.driver.quit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    await update.message.reply_text("""
🔧 **BLIBLI AUTO-ORDER BOT**
/add - Tambah akun (kirim file .json)
/delete <nama_file> - Hapus akun
/set_time <YYYY-MM-DD HH:MM:SS> - Atur waktu
/set_voucher <KODE> - Set voucher
/set_link <URL> - Set produk
/list - Lihat akun
/run - Jalankan sekarang
/schedule <nama_file> <YYYY-MM-DD HH:MM:SS> - Jadwalkan pemesanan
""")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    
    file = await update.message.document.get_file()
    filename = update.message.document.file_name
    await file.download_to_drive(f"cookies/{filename}")
    
    config = json.load(open('config.json'))
    config['accounts'].append(filename)
    json.dump(config, open('config.json', 'w'))
    
    await update.message.reply_text(f"✅ {filename} ditambahkan!")

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Harap masukkan nama file akun yang ingin dihapus.")
        return
    
    filename = context.args[0]
    config = json.load(open('config.json'))
    
    if filename in config['accounts']:
        config['accounts'].remove(filename)
        json.dump(config, open('config.json', 'w'))
        await update.message.reply_text(f"✅ {filename} berhasil dihapus!")
    else:
        await update.message.reply_text(f"❌ {filename} tidak ditemukan.")

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CONFIG['order_time'] = ' '.join(context.args)
    os.environ["ORDER_TIME"] = CONFIG['order_time']
    await update.message.reply_text(f"⏰ Waktu diatur: {CONFIG['order_time']}")

async def set_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CONFIG['voucher'] = context.args[0]
    os.environ["VOUCHER_CODE"] = CONFIG['voucher']
    await update.message.reply_text(f"🎫 Voucher diatur: {CONFIG['voucher']}")

async def set_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CONFIG['target_url'] = context.args[0]
    os.environ["TARGET_URL"] = CONFIG['target_url']
    await update.message.reply_text(f"🔗 Link diatur: {CONFIG['target_url']}")

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = "\n".join(json.load(open('config.json'))['accounts']) or "Tidak ada akun"
    await update.message.reply_text(f"📁 Daftar Akun:\n{accounts}")

async def run_account_order(filename: str, chat_id: int):
    blibli = BlibliAuto(filename)
    await blibli.process_order(chat_id)

async def run_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not all(CONFIG.values()):
        await update.message.reply_text("❌ Konfigurasi belum lengkap!")
        return
    
    accounts = json.load(open('config.json'))['accounts']
    if not accounts:
        await update.message.reply_text("❌ Tidak ada akun yang terdaftar.")
        return
    
    await update.message.reply_text("🚀 Memulai pemesanan untuk semua akun...")
    
    tasks = []
    for account in accounts:
        tasks.append(run_account_order(account, update.effective_chat.id))
    
    await asyncio.gather(*tasks)

async def schedule_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: /schedule <nama_file_akun> <YYYY-MM-DD HH:MM:SS>")
        return
    
    filename = context.args[0]
    order_time = ' '.join(context.args[1:])
    
    try:
        order_time = datetime.strptime(order_time, "%Y-%m-%d %H:%M:%S")
        scheduler.add_job(
            run_account_order,
            'date',
            run_date=order_time,
            args=[filename, update.effective_chat.id]
        )
        await update.message.reply_text(f"⏰ Pemesanan untuk {filename} dijadwalkan pada {order_time}.")
    except ValueError:
        await update.message.reply_text("❌ Format waktu tidak valid. Gunakan format: YYYY-MM-DD HH:MM:SS")

async def on_startup(app: Application):
    for user_id in ALLOWED_USERS:
        await Bot(token=TELEGRAM_TOKEN).send_message(
            chat_id=user_id,
            text="🤖 Bot telah terhubung dan siap digunakan!"
        )

if __name__ == "__main__":
    # Setup folder
    os.makedirs("cookies", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Init bot
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", handle_document))
    app.add_handler(CommandHandler("delete", delete_account))
    app.add_handler(CommandHandler("set_time", set_time))
    app.add_handler(CommandHandler("set_voucher", set_voucher))
    app.add_handler(CommandHandler("set_link", set_link))
    app.add_handler(CommandHandler("list", list_accounts))
    app.add_handler(CommandHandler("run", run_now))
    app.add_handler(CommandHandler("schedule", schedule_order))
    
    # Start scheduler
    scheduler.start()
    
    # Notifikasi saat bot terhubung
    app.run_polling(on_startup=on_startup)

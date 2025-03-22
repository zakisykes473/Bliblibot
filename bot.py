import os
import json
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

# Load Config
CONFIG = {
    "target_url": "",
    "voucher": "",
    "order_time": ""
}
ACCOUNTS = []

# Setup
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
ALLOWED_USERS = [int(id) for id in os.getenv("ALLOWED_USER_IDS").split(",")]

class BlibliAuto:
    def __init__(self, account_file):
        self.driver = webdriver.Chrome(
            options=self.get_chrome_options(),
        )
        self.account_file = account_file

    def get_chrome_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-dev-shm-usage")
        options.binary_location = "/data/data/com.termux/files/usr/bin/chromium"
        return options

    async def process_order(self, chat_id):
        try:
            # Load cookies
            with open(f"cookies/{self.account_file}") as f:
                cookies = json.load(f)
            
            self.driver.get("https://www.blibli.com")
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            
            # Proses order
            self.driver.get(CONFIG['target_url'])
            
            # Klik beli sekarang
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Beli Sekarang')]"))
            ).click()
            
            # Apply voucher
            self.driver.find_element(By.ID, "voucherCode").send_keys(CONFIG['voucher'])
            self.driver.find_element(By.XPATH, "//button[contains(., 'Pakai')]").click()
            
            # Pembayaran
            self.driver.find_element(By.XPATH, "//div[contains(., 'Gopay')]").click()
            self.driver.find_element(By.ID, "confirmPayment").click()
            
            await bot.send_message(
                chat_id=chat_id,
                text=f"✅ [{self.account_file}] Order sukses!"
            )
        except Exception as e:
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ [{self.account_file}] Gagal: {str(e)}"
            )
        finally:
            self.driver.quit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    await update.message.reply_text("""
🤖 **Blibli Auto-Order Bot**
/add_account - Tambah akun (kirim file .json)
/set_time [YYYY-MM-DD HH:MM:SS] - Atur waktu
/set_voucher [KODE] - Set voucher
/set_link [URL] - Set link produk
/list_accounts - Daftar akun
/run - Jalankan sekarang
""")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    
    file = await update.message.document.get_file()
    await file.download_to_drive(f"cookies/{update.message.document.file_name}")
    ACCOUNTS.append(update.message.document.file_name)
    
    await update.message.reply_text("✅ Akun ditambahkan!")

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CONFIG['order_time'] = ' '.join(context.args)
    await update.message.reply_text(f"⏰ Waktu diatur: {CONFIG['order_time']}")

async def set_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CONFIG['voucher'] = context.args[0]
    await update.message.reply_text(f"🎫 Voucher diatur: {CONFIG['voucher']}")

async def set_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CONFIG['target_url'] = context.args[0]
    await update.message.reply_text(f"🔗 Link diatur: {CONFIG['target_url']}")

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = "\n".join(ACCOUNTS) if ACCOUNTS else "Belum ada akun"
    await update.message.reply_text(f"📂 Daftar Akun:\n{accounts}")

async def run_job(context: ContextTypes.DEFAULT_TYPE):
    for account in ACCOUNTS:
        blibli = BlibliAuto(account)
        await blibli.process_order(context.job.chat_id)

async def run_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not all([CONFIG['target_url'], CONFIG['voucher'], ACCOUNTS]):
        await update.message.reply_text("❌ Konfigurasi belum lengkap!")
        return
    
    for account in ACCOUNTS:
        blibli = BlibliAuto(account)
        await blibli.process_order(update.effective_chat.id)

if __name__ == "__main__":
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_time", set_time))
    app.add_handler(CommandHandler("set_voucher", set_voucher))
    app.add_handler(CommandHandler("set_link", set_link))
    app.add_handler(CommandHandler("list_accounts", list_accounts))
    app.add_handler(CommandHandler("run", run_now))
    
    # Document Handler (Untuk upload cookies)
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, handle_document))
    
    app.run_polling()

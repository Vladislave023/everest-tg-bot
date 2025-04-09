import os
from dotenv import load_dotenv

load_dotenv()  

TOKEN = os.getenv("BOT_TOKEN")  
ADMIN_ID = os.getenv("ADMIN_ID")
WEBSITE_URL = "https://everest-tk.ru/obnovlenie-kataloga"
CHANNEL_URL = "https://t.me/everesttkk"
WORKING_HOURS_TEXT = "Ожидайте, в рабочее время с 9 до 18 по Хабаровску с вами свяжется специалист"
ALBUM_THRESHOLD_SECONDS = 1.5  
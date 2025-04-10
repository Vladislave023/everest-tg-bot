import os

if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv()

TOKEN = os.getenv("BOT_TOKEN") or os.environ.get("BOT_TOKEN")  # Берёт из .env или GitHub Secrets
ADMIN_ID = int(os.getenv("ADMIN_ID") or os.environ.get("ADMIN_ID"))  # Преобразует в число

WEBSITE_URL = "https://everest-tk.ru/obnovlenie-kataloga"
CHANNEL_URL = "https://t.me/everesttkk"
WORKING_HOURS_TEXT = "Ожидайте, в рабочее время с 9 до 18 по Хабаровску с вами свяжется специалист"
ALBUM_THRESHOLD_SECONDS = 1.5

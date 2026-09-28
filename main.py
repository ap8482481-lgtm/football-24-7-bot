import os
import sys
import asyncio
import urllib.parse
import urllib.request
import feedparser
import io
import re

# ================= АВТОУСТАНОВКА ЗАВИСИМОСТЕЙ =================
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Автоматическая установка библиотеки Pillow...")
    os.system(f"{sys.executable} -m pip install Pillow")
    from PIL import Image, ImageDraw, ImageFont

from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# ================= НАСТРОЙКИ =================
# ВНИМАНИЕ: При загрузке на GitHub (публичный репозиторий) 
# не оставляйте здесь свои реальные ключи!
BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
CHANNEL_ID = "@ВАШ_ЮЗЕРНЕЙМ_КАНАЛА"  # Например: @football24_7_news
GIGACHAT_AUTH_DATA = "ВАШ_КЛЮЧ_АВТОРИЗАЦИИ_GIGACHAT"

RSS_URLS = [
    "https://www.championat.com/xml/rss_football.xml",
    "https://www.sports.ru/stat/export/rss/football.xml",
    "https://www.sport-express.ru/services/materials/news/football/se/",
    "https://matchtv.ru/news.rss"
]
# =============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
posted_news = set()

# Промпт для написания текста
SYSTEM_PROMPT_TEXT = """
Ты — главный редактор Telegram-канала "ФУТБОЛ 24/7". 
Твоя задача — сделать короткую выжимку из новости. 
Правила:
1. Строго по факту, никакой воды и слухов.
2. Текст должен читаться за 15-30 секунд.
3. Обязательно добавь в начале поста одну из подходящих рубрик с эмодзи:
⚡️ #Срочно | 🔄 #Трансферы | 🏆 #Матчи | 📊 #Статистика | 🗣 #Мнения
"""

# Промпт для фотореалистичной картинки
SYSTEM_PROMPT_IMAGE = """
Ты — профессиональный prompt-инженер. 
Твоя задача: прочитать новость о футболе и написать короткое описание (промпт) на английском языке для генерации фотореалистичной картинки.
Правила:
1. ТОЛЬКО английский язык.
2. Не более 10-15 слов.
3. Без вводных слов, только сама суть картинки.
4. Обязательно добавь в конце стилистику: sports action photography, DSLR, ultra-realistic, sharp focus, 8k resolution, photorealistic.
"""

def rewrite_news_with_ai(news_text: str) -> str:
    """Генерация текста поста через GigaChat-3-Ultra"""
    try:
        client = GigaChat(credentials=GIGACHAT_AUTH_DATA, scope="GIGACHAT_API_PERS", verify_ssl_certs=False)
        chat = Chat(
            model="GigaChat-3-Ultra",
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT_TEXT),
                Messages(role=MessagesRole.USER, content=f"Сделай пост из этой новости:\n{news_text}")
            ],
        )
        return client.chat(chat).choices[0].message.content
    except Exception as e:
        print(f"Ошибка GigaChat (Текст): {e}")
        return None

def generate_image_prompt_with_ai(news_text: str) -> str:
    """Генерация английского промпта для картинки"""
    try:
        client = GigaChat(credentials=GIGACHAT_AUTH_DATA, scope="GIGACHAT_API_PERS", verify_ssl_certs=False)
        chat = Chat(
            model="GigaChat-3-Ultra",
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT_IMAGE),
                Messages(role=MessagesRole.USER, content=f"Сделай промпт для обложки этой новости:\n{news_text}")
            ],
        )
        return client.chat(chat).choices[0].message.content.strip()
    except Exception as e:
        return "epic football moment, sports action photography, DSLR, ultra-realistic, sharp focus, 8k resolution, photorealistic"

def download_generated_image(prompt: str):
    """Скачивание картинки с использованием фотореалистичной модели Flux"""
    try:
        print("ОТЛАДКА: Нейросеть рисует картинку в высоком качестве (модель Flux)...")
        safe_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&nologo=true&model=flux"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    except Exception as e:
        print(f"Ошибка скачивания ИИ-картинки: {e}")
        return None

def apply_watermark(image_bytes: bytes) -> bytes:
    """Обрезает чужой логотип и накладывает плашку канала"""
    try:
        # 1. Открываем сгенерированную картинку
        base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        
        # 2. Срезаем нижние 40 пикселей, чтобы навсегда удалить логотип @pollinations.ai
        base_img = base_img.crop((0, 0, base_img.width, base_img.height - 40))
        
        # 3. Создаем прозрачный слой
        txt_layer = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)
        
        # 4. Загружаем шрифт (если блокировка — системный)
        font_path = "Roboto-Bold.ttf"
        try:
            if not os.path.exists(font_path):
                urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf", font_path)
            font = ImageFont.truetype(font_path, 45)
        except Exception:
            font = ImageFont.load_default()
        
        text = "ФУТБОЛ 24/7"
        
        # 5. Вычисляем размер текста (поддержка новых и старых версий Pillow)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_width, text_height = draw.textsize(text, font=font)
            
        # 6. Координаты для правого нижнего угла
        margin_x, margin_y = 30, 30
        padding_x, padding_y = 20, 10
        
        x = base_img.width - text_width - margin_x - (padding_x * 2)
        y = base_img.height - text_height - margin_y - (padding_y * 2)
        
        # 7. Рисуем полупрозрачную черную плашку
        try:
            draw.rounded_rectangle(
                [x, y, x + text_width + (padding_x * 2), y + text_height + (padding_y * 2)],
                radius=12,
                fill=(0, 0, 0, 190)
            )
        except AttributeError:
            draw.rectangle(
                [x, y, x + text_width + (padding_x * 2), y + text_height + (padding_y * 2)],
                fill=(0, 0, 0, 190)
            )
            
        # 8. Наносим текст и сохраняем
        draw.text((x + padding_x, y + padding_y), text, font=font, fill=(255, 255, 255, 255))
        
        final_img = Image.alpha_composite(base_img, txt_layer).convert("RGB")
        output = io.BytesIO()
        final_img.save(output, format="JPEG", quality=95)
        return output.getvalue()
        
    except Exception as e:
        print(f"Ошибка при создании водяного знака: {e}")
        return image_bytes

def get_latest_news_from_all_sources():
    """Парсинг последних футбольных новостей"""
    all_entries = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                all_entries.append(feed.entries[0])
        except Exception:
             pass
    if not all_entries:
        return None
    return all_entries[0] 

async def fetch_and_publish():
    """Основной цикл публикации"""
    print("Проверка новых новостей по всем источникам...")
    latest_entry = get_latest_news_from_all_sources()
    
    if latest_entry:
        news_link = latest_entry.link
        if news_link not in posted_news:
            raw_text = f"{latest_entry.title}\n{latest_entry.get('summary', '')}"
            
            # 1. Текст от нейросети
            final_post = rewrite_news_with_ai(raw_text)
            
            if final_post:
                # 2. Картинка от нейросети
                image_prompt = generate_image_prompt_with_ai(raw_text)
                image_bytes = download_generated_image(image_prompt)
                
                try:
                    if image_bytes:
                        # 3. Наложение водяного знака
                        branded_image_bytes = apply_watermark(image_bytes)
                        photo = BufferedInputFile(branded_image_bytes, filename="ai_cover_branded.jpg")
                        
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=final_post)
                        print("Новость с ФИРМЕННОЙ картинкой опубликована!")
                    else:
                        await bot.send_message(chat_id=CHANNEL_ID, text=final_post)
                        print("Новость без картинки опубликована!")
                        
                    posted_news.add(news_link)
                except Exception as e:
                    print(f"Ошибка публикации: {e}")
        else:
            print("Самая свежая новость уже была опубликована ранее.")

async def main():
    print("ШАГ 1: Удаляем конфликты Telegram (Webhook)...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("ШАГ 2: Запускаем планировщик задач (интервал 20 минут)...")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(fetch_and_publish, "interval", minutes=20) 
    scheduler.start()
    
    print("ШАГ 3: Тестовый запуск публикации...")
    await fetch_and_publish()
    
    print("ШАГ 4: Переход в режим ожидания (Polling)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

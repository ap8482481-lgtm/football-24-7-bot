import asyncio
import urllib.parse
import urllib.request
import feedparser
from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8691613866:AAF9OyxSbbECPSouLLJYeDKADYFqjQszN60"
CHANNEL_ID = "@football24_7_news" 
GIGACHAT_AUTH_DATA = "MDFhMDhjODctNzJlOS03ZTM1LTkyZDUtMzQ2NWEzNzg4MzAxOmY3YmQyODM4LWJlOTItNGYzOC1hOGZjLTM1YTU2ZjE2YTgzMg=="

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

# Промпт для текста
SYSTEM_PROMPT_TEXT = """
Ты — главный редактор Telegram-канала "ФУТБОЛ 24/7". 
Твоя задача — сделать короткую выжимку из новости. 
Правила:
1. Строго по факту, никакой воды и слухов.
2. Текст должен читаться за 15-30 секунд.
3. Обязательно добавь в начале поста одну из подходящих рубрик с эмодзи:
⚡️ #Срочно | 🔄 #Трансферы | 🏆 #Матчи | 📊 #Статистика | 🗣 #Мнения
"""

# Промпт для генерации картинки
SYSTEM_PROMPT_IMAGE = """
Ты — профессиональный prompt-инженер. 
Твоя задача: прочитать новость о футболе и написать короткое описание (промпт) на английском языке для генерации картинки нейросетью.
Правила:
1. ТОЛЬКО английский язык.
2. Не более 10-15 слов.
3. Без вводных слов, только сама суть картинки.
4. Обязательно добавь в конце стилистику: cinematic lighting, realistic, highly detailed, 8k.
Пример: Two football players fighting for the ball on a green field, cinematic lighting, realistic, highly detailed, 8k
"""

def rewrite_news_with_ai(news_text: str) -> str:
    """Генерация текста поста через GigaChat"""
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
    """Генерация промпта для картинки через GigaChat"""
    try:
        client = GigaChat(credentials=GIGACHAT_AUTH_DATA, scope="GIGACHAT_API_PERS", verify_ssl_certs=False)
        chat = Chat(
            model="GigaChat-3-Ultra",
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT_IMAGE),
                Messages(role=MessagesRole.USER, content=f"Сделай промпт для обложки этой новости:\n{news_text}")
            ],
        )
        prompt = client.chat(chat).choices[0].message.content.strip()
        print(f"ОТЛАДКА: Сгенерирован промпт для фото -> {prompt}")
        return prompt
    except Exception as e:
        print(f"Ошибка GigaChat (Промпт картинки): {e}")
        return "epic football moment, cinematic lighting, realistic, highly detailed, 8k" # Резервный промпт

def download_generated_image(prompt: str):
    """Отправляет промпт в ИИ-генератор и скачивает готовую картинку"""
    try:
        print("ОТЛАДКА: Нейросеть рисует картинку, подождите 5-10 секунд...")
        safe_prompt = urllib.parse.quote(prompt)
        # Обращаемся к бесплатному генератору без логотипов, размер 1024x1024
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&nologo=true"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read()
    except Exception as e:
        print(f"ОТЛАДКА: Ошибка при рисовании картинки: {e}")
        return None

def get_latest_news_from_all_sources():
    all_entries = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                all_entries.append(feed.entries[0])
        except Exception as e:
             print(f"Ошибка парсинга {url}: {e}")
             
    if not all_entries:
        return None
    return all_entries[0] 

async def fetch_and_publish():
    print("Проверка новых новостей по всем источникам...")
    
    latest_entry = get_latest_news_from_all_sources()
    
    if latest_entry:
        news_link = latest_entry.link
        
        if news_link not in posted_news:
            news_title = latest_entry.title
            news_summary = latest_entry.get('summary', '') 
            raw_text = f"{news_title}\n{news_summary}"
            print(f"Найдена новая новость: {news_title}")
            
            # 1. Пишем текст
            final_post = rewrite_news_with_ai(raw_text)
            
            if final_post:
                # 2. Придумываем промпт для картинки
                image_prompt = generate_image_prompt_with_ai(raw_text)
                
                # 3. Рисуем и скачиваем картинку
                image_bytes = download_generated_image(image_prompt)
                
                try:
                    if image_bytes:
                        photo = BufferedInputFile(image_bytes, filename="ai_cover.jpg")
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=final_post)
                        print("Новость с УНИКАЛЬНОЙ ИИ-КАРТИНКОЙ успешно опубликована!")
                    else:
                        await bot.send_message(chat_id=CHANNEL_ID, text=final_post)
                        print("Новость БЕЗ картинки успешно опубликована!")
                        
                    posted_news.add(news_link)
                except Exception as e:
                    print(f"Ошибка публикации в Telegram: {e}")
            else:
                print("Не удалось получить текст от GigaChat.")
        else:
            print("Самая свежая новость уже была опубликована ранее.")
    else:
        print("Не удалось получить новости из RSS-источников.")

async def main():
    print("ШАГ 1: Удаляем вебхук Telegram...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("ШАГ 2: Запускаем планировщик...")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(fetch_and_publish, "interval", minutes=20) 
    scheduler.start()
    
    print("ШАГ 3: Делаем тестовую проверку прямо сейчас...")
    await fetch_and_publish()
    
    print("ШАГ 4: Запускаем ожидание (Polling)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

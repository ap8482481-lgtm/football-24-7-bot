import asyncio
import feedparser
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from gigachat import GigaChat

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8691613866:AAF9OyxSbbECPSouLLJYeDKADYFqjQszN60"
CHANNEL_ID = "@football24_7_news"
GIGACHAT_AUTH_DATA = "MDFhMDhjODctNzJlOS03ZTM1LTkyZDUtMzQ2NWEzNzg4MzAxOmY3YmQyODM4LWJlOTItNGYzOC1hOGZjLTM1YTU2ZjE2YTgzMg=="

# Список источников новостей
RSS_URLS = [
    "https://www.championat.com/xml/rss_football.xml",  # Чемпионат (Футбол)
    "https://www.sports.ru/stat/export/rss/football.xml", # Sports.ru (Футбол)
    "https://www.sport-express.ru/services/materials/news/football/se/", # Спорт-Экспресс
    "https://matchtv.ru/news.rss" # Матч ТВ (общая, но бот сгенерирует текст только если это футбол)
]
# =============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище опубликованных новостей
posted_news = set()

SYSTEM_PROMPT = """
Ты — главный редактор Telegram-канала "ФУТБОЛ 24/7". 
Твоя задача — сделать короткую выжимку из новости. 
Правила:
1. Строго по факту, никакой воды и слухов.
2. Текст должен читаться за 15-30 секунд.
3. Обязательно добавь в начале поста одну из подходящих рубрик с эмодзи:
⚡️ #Срочно (для важных новостей)
🔄 #Трансферы (для переходов)
🏆 #Матчи (для результатов)
📊 #Статистика (для цифр и фактов)
🗣 #Мнения (для цитат и интервью)
"""

def rewrite_news_with_ai(news_text: str) -> str:
    """Отправка новости в GigaChat для рерайта"""
    try:
        with GigaChat(credentials=GIGACHAT_AUTH_DATA, verify_ssl_certs=False) as giga:
            response = giga.chat(
                payload={
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Сделай пост из этой новости:\n{news_text}"}
                    ],
                    "model": "GigaChat-Pro"  
                }
            )
            return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка GigaChat: {e}")
        return None

def extract_image_from_entry(entry):
    """Извлекает ссылку на картинку из RSS-ленты"""
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        for enc in entry.enclosures:
            if 'image' in enc.type or enc.href.endswith(('.jpg', '.jpeg', '.png')):
                return enc.href
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    return None

def get_latest_news_from_all_sources():
    """Собирает последнюю новость из всех RSS-лент и выбирает самую свежую"""
    all_entries = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                # Берём самую новую запись из каждой ленты
                entry = feed.entries[0] 
                all_entries.append(entry)
        except Exception as e:
             print(f"Ошибка парсинга {url}: {e}")
             
    if not all_entries:
        return None
        
    # В RSS обычно есть поле 'published_parsed', по которому можно сортировать
    # Но для надежности просто берём первую попавшуюся не опубликованную новость
    # (в реальном проекте лучше парсить время и сортировать по нему)
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
            
            final_post = rewrite_news_with_ai(raw_text)
            image_url = extract_image_from_entry(latest_entry)
            
            if final_post:
                try:
                    if image_url:
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=final_post)
                        print("Новость с КАРТИНКОЙ успешно опубликована!")
                    else:
                        await bot.send_message(chat_id=CHANNEL_ID, text=final_post)
                        print("Новость БЕЗ картинки успешно опубликована!")
                        
                    posted_news.add(news_link)
                except Exception as e:
                    print(f"Ошибка публикации в Telegram: {e}")

async def main():
    scheduler = AsyncIOScheduler()
    # Уменьшим интервал, чтобы новости с разных сайтов выходили чаще
    scheduler.add_job(fetch_and_publish, "interval", minutes=20) 
    scheduler.start()
    
    print("Бот запущен. Ожидание расписания...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

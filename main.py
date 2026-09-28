import asyncio
import re
import urllib.request
import feedparser
from aiogram import Bot, Dispatcher
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
    """Отправка новости в GigaChat-3-Ultra"""
    try:
        client = GigaChat(
            credentials=GIGACHAT_AUTH_DATA,
            scope="GIGACHAT_API_PERS",
            verify_ssl_certs=False,
        )
        
        chat = Chat(
            model="GigaChat-3-Ultra",
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                Messages(role=MessagesRole.USER, content=f"Сделай пост из этой новости:\n{news_text}")
            ],
        )
        
        resp = client.chat(chat)
        return resp.choices[0].message.content
    except Exception as e:
        print(f"Ошибка GigaChat: {e}")
        return None

def extract_image_from_entry(entry):
    """Продвинутый парсер og:image с имитацией браузера и отладкой"""
    if not hasattr(entry, 'link') or not entry.link:
        print("ОТЛАДКА: У записи в RSS нет ссылки (link)")
        return None
        
    try:
        print(f"ОТЛАДКА: Скачиваем страницу статьи для поиска картинки -> {entry.link}")
        req = urllib.request.Request(
            entry.link, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
            # Универсальный поиск (поддерживает property и name в любом порядке)
            patterns = [
                r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    img_url = match.group(1)
                    print(f"ОТЛАДКА: Найдена картинка og:image -> {img_url}")
                    return img_url
                    
            print("ОТЛАДКА: Тег og:image на странице статьи не найден.")
    except Exception as e:
        print(f"ОТЛАДКА: Ошибка при загрузке страницы для картинки: {e}")
        
    return None

def get_latest_news_from_all_sources():
    """Собирает последнюю новость из всех RSS-лент"""
    all_entries = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                entry = feed.entries[0] 
                all_entries.append(entry)
        except Exception as e:
             print(f"Ошибка парсинга {url}: {e}")
             
    if not all_entries:
        return None
        
    return all_entries[0] 

async def fetch_and_publish():
    """Сбор новостей и публикация в канал"""
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
            else:
                print("Не удалось получить текст от GigaChat.")
        else:
            print("Самая свежая новость уже была опубликована ранее.")
    else:
        print("Не удалось получить новости из RSS-источников.")

async def main():
    print("ШАГ 1: Удаляем вебхук Telegram...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("ШАГ 1: Вебхук успешно удален.")
    except Exception as e:
        print(f"Ошибка при удалении вебхука: {e}")
    
    print("ШАГ 2: Запускаем планировщик...")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(fetch_and_publish, "interval", minutes=20) 
    scheduler.start()
    print("ШАГ 2: Планировщик запущен.")
    
    print("ШАГ 3: Делаем тестовую проверку новостей прямо сейчас...")
    try:
        await fetch_and_publish()
        print("ШАГ 3: Тестовая проверка завершена.")
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА В ТЕСТЕ: {e}")
    
    print("ШАГ 4: Запускаем ожидание сообщений от Telegram (Polling)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

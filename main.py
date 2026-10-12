import os
import sys
import asyncio
import io
import re
import feedparser

# ================= АВТОУСТАНОВКА ЗАВИСИМОСТЕЙ =================
try:
    from PIL import Image, ImageDraw, ImageFont
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Установка необходимых библиотек...")
    os.system(f"{sys.executable} -m pip install Pillow requests beautifulsoup4")
    from PIL import Image, ImageDraw, ImageFont
    import requests
    from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
CHANNEL_ID = "@ВАШ_ЮЗЕРНЕЙМ_КАНАЛА"  
GIGACHAT_AUTH_DATA = "ВАШ_КЛЮЧ_АВТОРИЗАЦИИ_GIGACHAT"

RSS_URLS = [
    "https://www.championat.com/xml/rss_football.xml",
    "https://www.sports.ru/stat/export/rss/football.xml",
    "https://www.sport-express.ru/services/materials/news/football/se/",
    "https://matchtv.ru/news.rss"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}
# =============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
posted_news = set()

SYSTEM_PROMPT_TEXT = """
Ты — главный редактор Telegram-канала "ФУТБОЛ 24/7". 
Твоя задача — сделать короткую выжимку из новости. 
Правила:
1. Строго по факту, никакой воды и слухов.
2. Текст должен читаться за 15-30 секунд.
3. Обязательно добавь в начале поста одну из подходящих рубрик с эмодзи:
⚡️ #Срочно | 🔄 #Трансферы | 🏆 #Матчи | 📊 #Статистика | 🗣 #Мнения
"""

def rewrite_news_with_ai(news_text: str) -> str:
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
        print(f"Ошибка GigaChat: {e}")
        return None

def extract_original_image_url(entry):
    if hasattr(entry, 'media_content') and entry.media_content:
        return entry.media_content[0].get('url')
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if 'image' in enc.get('type', '') or any(ext in enc.get('href', '').lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                return enc.get('href')

    summary = getattr(entry, 'summary', '')
    if summary:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
        if match:
            return match.group(1)

    if hasattr(entry, 'link') and entry.link:
        try:
            resp = requests.get(entry.link, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                og_image = soup.find('meta', property='og:image')
                if og_image and og_image.get('content'):
                    return og_image['content']
        except Exception:
            pass
    return None

def download_image(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None

def download_generated_image(prompt: str):
    """Резервная генерация реалистичного фона, если сайт заблокировал фото"""
    import urllib.parse
    try:
        print("ОТЛАДКА: Сайт не отдал фото. Генерируем резервный ИИ-фон...")
        safe_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true&model=flux"
        req = requests.get(url, headers=HEADERS, timeout=30)
        if req.status_code == 200:
            return req.content
    except Exception as e:
        print(f"Ошибка резервной генерации: {e}")
    return None

def apply_premium_template(image_bytes: bytes, post_text: str) -> bytes:
    try:
        base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        
        target_w, target_h = 1280, 720
        aspect_base = base_img.width / base_img.height
        aspect_target = target_w / target_h
        
        if aspect_base > aspect_target:
            new_w = int(base_img.height * aspect_target)
            offset = (base_img.width - new_w) // 2
            base_img = base_img.crop((offset, 0, offset + new_w, base_img.height))
        else:
            new_h = int(base_img.width / aspect_target)
            offset = (base_img.height - new_h) // 2
            base_img = base_img.crop((0, offset, base_img.width, offset + new_h))
            
        base_img = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        overlay = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        font_path = "Roboto-Bold.ttf"
        if not os.path.exists(font_path):
            resp = requests.get("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf")
            with open(font_path, 'wb') as f:
                f.write(resp.content)
        
        font_large = ImageFont.truetype(font_path, 65)
        font_tag = ImageFont.truetype(font_path, 45)
        
        tag_match = re.search(r'#([А-Яа-яA-Za-z0-9_]+)', post_text)
        tag_text = f"#{tag_match.group(1)}" if tag_match else "#Футбол"
        
        try:
            bbox = draw.textbbox((0, 0), tag_text, font=font_tag)
            tag_w = bbox[2] - bbox[0] + 60
        except AttributeError:
            tag_w = draw.textsize(tag_text, font=font_tag)[0] + 60
            
        tag_poly = [(0, 40), (tag_w, 40), (tag_w - 25, 110), (0, 110)]
        tag_shadow = [(x+8, y+8) for x, y in tag_poly]
        draw.polygon(tag_shadow, fill=(0, 0, 0, 120))
        draw.polygon(tag_poly, fill=(226, 35, 50, 255))
        draw.text((30, 50), tag_text, font=font_tag, fill=(255, 255, 255, 255))
        
        text1 = "ФУТБОЛ"
        text2 = " 24/7 "
        
        try:
            bbox1 = draw.textbbox((0, 0), text1, font=font_large)
            w1 = bbox1[2] - bbox1[0] + 60
            bbox2 = draw.textbbox((0, 0), text2, font=font_large)
            w2 = bbox2[2] - bbox2[0] + 60
        except AttributeError:
            w1 = draw.textsize(text1, font=font_large)[0] + 60
            w2 = draw.textsize(text2, font=font_large)[0] + 60
        
        y1_top, y1_bot = 500, 590
        x1_right = target_w - 40
        x1_left = x1_right - w1
        poly1 = [(x1_left, y1_top), (x1_right, y1_top), (x1_right - 25, y1_bot), (x1_left - 25, y1_bot)]
        
        y2_top, y2_bot = 590, 680
        x2_right = target_w - 65
        x2_left = x2_right - w2
        poly2 = [(x2_left, y2_top), (x2_right, y2_top), (x2_right - 25, y2_bot), (x2_left - 25, y2_bot)]
        
        draw.polygon([(x+10, y+10) for x, y in poly1], fill=(0, 0, 0, 120))
        draw.polygon([(x+10, y+10) for x, y in poly2], fill=(0, 0, 0, 120))
        
        draw.polygon(poly1, fill=(226, 35, 50, 255))
        draw.polygon(poly2, fill=(255, 255, 255, 255))
        
        draw.text((x1_left + 25, y1_top + 10), text1, font=font_large, fill=(255, 255, 255, 255))
        draw.text((x2_left + 20, y2_top + 10), text2, font=font_large, fill=(20, 25, 40, 255))
        
        final_img = Image.alpha_composite(base_img, overlay).convert("RGB")
        output = io.BytesIO()
        final_img.save(output, format="JPEG", quality=95)
        return output.getvalue()
        
    except Exception as e:
        print(f"Ошибка при наложении премиум-шаблона: {e}")
        return image_bytes

def get_latest_news_from_all_sources():
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
    print("Проверка новых новостей по всем источникам...")
    latest_entry = get_latest_news_from_all_sources()
    
    if latest_entry:
        news_link = latest_entry.link
        if news_link not in posted_news:
            raw_text = f"{latest_entry.title}\n{latest_entry.get('summary', '')}"
            final_post = rewrite_news_with_ai(raw_text)
            
            if final_post:
                # 1. Пытаемся достать оригинальное фото
                original_img_url = extract_original_image_url(latest_entry)
                image_bytes = None
                
                if original_img_url:
                    print(f"ОТЛАДКА: Качаем фото -> {original_img_url}")
                    image_bytes = download_image(original_img_url)
                
                # 2. Если сайт заблокировал скачивание — генерируем ИИ-фон
                if not image_bytes:
                    fallback_prompt = "sports action photography, epic football moment, DSLR, ultra-realistic, sharp focus, stadium lights, photorealistic"
                    image_bytes = download_generated_image(fallback_prompt)
                
                try:
                    if image_bytes:
                        # 3. Накладываем шаблон
                        branded_image_bytes = apply_premium_template(image_bytes, final_post)
                        photo = BufferedInputFile(branded_image_bytes, filename="premium_cover.jpg")
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=final_post)
                        print("Новость с ПРЕМИУМ ДИЗАЙНОМ опубликована!")
                    else:
                        await bot.send_message(chat_id=CHANNEL_ID, text=final_post)
                        print("Новость без картинки опубликована (даже резерв не сработал).")
                        
                    posted_news.add(news_link)
                except Exception as e:
                    print(f"Ошибка публикации: {e}")
        else:
            print("Самая свежая новость уже была опубликована ранее.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(fetch_and_publish, "interval", minutes=20) 
    scheduler.start()
    await fetch_and_publish()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import jinja2
import markupsafe
from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging

from models import ExplainRequest, ExplainResponse, SearchResponse
from services import get_or_create_explanation, load_explanation_from_file, get_all_explanation_slugs, \
    search_explanations

logger = logging.getLogger(__name__)

# Определяем базовую директорию приложения
APP_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="ПростоПонятно.ai",
    description="Объяснение сложных тем простыми словами с помощью AI",
    version="1.0.0"
)

# Монтируем статические файлы (CSS, JS)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

# Настраиваем шаблонизатор Jinja2
templates = Jinja2Templates(directory=APP_DIR / "templates")


@jinja2.pass_context
def nl2br(_, value):
    br = "<br>\n"
    result = str(markupsafe.escape(value)).replace('\n', br)
    return markupsafe.Markup(result)


templates.env.filters['nl2br'] = nl2br


# --- Эндпоинты для HTML страниц ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Отображает главную страницу с формой ввода."""
    explanation_levels = {
        "simple": "Простое объяснение",
        "teenager": "Как подростку",
        "5-year-old": "Как 5-летнему",
        "tldr": "Кратко (TL;DR)",
        "pros_cons": "Плюсы и минусы",
        "metaphor": "Через метафору (AI придумает)",
        "custom_analogy": "С моей аналогией..."
    }
    return templates.TemplateResponse("index.html", {
        "request": request,
        "explanation_levels": explanation_levels
    })


@app.get("/explanation/{slug}", response_class=HTMLResponse)
async def read_explanation(request: Request, slug: str):
    """Отображает страницу с сохраненным объяснением по его slug."""
    logger.info(f"Request for explanation page with slug: {slug}")
    explanation_data = await load_explanation_from_file(slug)

    if not explanation_data:
        logger.warning(f"Explanation with slug '{slug}' not found.")
        # Можно редиректить на главную или показывать 404
        # return RedirectResponse(url="/", status_code=302)
        raise HTTPException(status_code=404, detail="Explanation not found")

    # Получаем название уровня для отображения
    level_map = {  # Карта для user-friendly названий уровней
        "simple": "Простое", "teenager": "Для подростка", "5-year-old": "Для 5-летнего",
        "tldr": "Кратко (TL;DR)", "pros_cons": "Плюсы и минусы", "metaphor": "Метафора",
        "custom_analogy": f"Аналогия: {explanation_data.analogy}" if explanation_data.analogy else "Аналогия"
    }
    display_level = level_map.get(explanation_data.level, explanation_data.level)

    context = {
        "request": request,
        "explanation": explanation_data,
        "display_level": display_level  # Передаем user-friendly название уровня
    }
    return templates.TemplateResponse("explanation_page.html", context)


# --- Эндпоинт API для генерации объяснений (используется JS с главной страницы) ---

@app.post("/api/explain", response_model=ExplainResponse)
async def api_explain_topic(explain_request: ExplainRequest):
    """
    Принимает запрос на объяснение, генерирует/получает его,
    возвращает текст и slug. Сохранение происходит в фоне.
    """
    try:
        explanation_text, slug = await get_or_create_explanation(explain_request)
        if slug:
            logger.info(f"Returning explanation for slug: {slug}")
            return ExplainResponse(explanation=explanation_text, slug=slug)
        else:
            logger.warning(f"Failed to get or create valid explanation for topic: {explain_request.topic}")
            # Если slug=None, значит это текст ошибки или невалидный ответ
            # Возвращаем его, но клиент должен понять, что это не успешное объяснение
            return ExplainResponse(explanation=explanation_text, slug=None)
    except ConnectionError as e:
        logger.error(f"ConnectionError in /api/explain: {e}")
        raise HTTPException(status_code=503, detail=str(e))  # Возвращаем текст ошибки
    except Exception as e:
        logger.error(f"Unexpected error in /api/explain: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при обработке запроса.")


# --- НОВЫЙ Эндпоинт для поиска ---
@app.get("/api/search", response_model=SearchResponse)
async def api_search(q: str = Query(None, min_length=3, max_length=50)):
    """
    Ищет сохраненные объяснения по запросу 'q'.
    """
    if q is None:
        return SearchResponse(results=[])  # Пустой запрос - пустой результат

    logger.info(f"Received search request with query: '{q}'")
    search_results = await search_explanations(q)
    return SearchResponse(results=search_results)


# ---------------------------------

# --- Эндпоинты для SEO ---

@app.get("/robots.txt", response_class=PlainTextResponse)
async def get_robots_txt(request: Request):
    """Возвращает содержимое файла robots.txt."""
    base_url = str(request.base_url)
    content = f"""User-agent: *
Allow: /
Disallow: /api/ # Запрещаем индексацию API

Sitemap: {base_url}sitemap.xml
"""
    return content


@app.get("/sitemap.xml")
async def get_sitemap(request: Request):
    """Генерирует XML Sitemap со всеми сохраненными страницами объяснений."""
    slugs = await get_all_explanation_slugs()
    base_url = str(request.base_url).rstrip('/')  # Убираем слэш в конце, если есть

    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # Главная страница
    xml_content += f'  <url><loc>{base_url}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'

    # Страницы объяснений
    for slug in slugs:
        xml_content += f'  <url><loc>{base_url}/explanation/{slug}</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>\n'
    xml_content += '</urlset>'

    return Response(content=xml_content, media_type="application/xml")


# --- Запуск сервера для локальной разработки ---
# (Этот блок выполняется, только если скрипт запущен напрямую: python -m app.main)
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Uvicorn server for local development...")
    # Запуск из корневой папки проекта: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    # Или можно запустить так, но без --reload:
    uvicorn.run(app, host="localhost", port=8000)

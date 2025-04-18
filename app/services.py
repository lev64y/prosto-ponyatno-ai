import asyncio
from typing import Optional, List

from google import genai
import logging
import json
import datetime
from pathlib import Path

from google.genai.types import Tool, GoogleSearch, GenerateContentConfig, FinishReason
from slugify import slugify
import aiofiles  # Для асинхронного чтения/записи

from app.core.config import GOOGLE_API_KEY, EXPLANATIONS_DIR
from models import ExplainRequest, StoredExplanation, SearchResultItem

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация клиента GenAI
try:
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY not found in environment variables.")
    # Используем актуальную и доступную модель
    client = genai.Client(api_key=GOOGLE_API_KEY)
    logger.info("Google GenAI client configured successfully.")
except Exception as _:
    logger.error(f"Error configuring Google GenAI client: {_}", exc_info=True)
    client = None

model_id = "gemini-2.0-flash"

google_search_tool = Tool(
    google_search=GoogleSearch()
)

generation_config = GenerateContentConfig(
    tools=[google_search_tool],
    response_modalities=["TEXT"],
)


# --- Функции для работы с файлами объяснений ---

def get_explanation_filepath(slug: str) -> Path:
    """Возвращает путь к файлу объяснения по slug."""
    return EXPLANATIONS_DIR / f"{slug}.json"


async def load_explanation_from_file(slug: str) -> Optional[StoredExplanation]:
    """Асинхронно загружает объяснение из JSON файла."""
    filepath = get_explanation_filepath(slug)
    if not filepath.is_file():
        return None
    try:
        async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            # Преобразуем строку времени обратно в datetime
            data['created_at'] = datetime.datetime.fromisoformat(data['created_at'])
            return StoredExplanation(**data)
    except Exception as e:
        logger.error(f"Error loading explanation file {filepath}: {e}")
        return None


async def save_explanation_to_file(data: StoredExplanation):
    """Асинхронно сохраняет объяснение в JSON файл."""
    filepath = get_explanation_filepath(data.slug)
    try:
        # Преобразуем datetime в строку ISO для JSON
        data_dict = data.model_dump()
        data_dict['created_at'] = data.created_at.isoformat()

        async with aiofiles.open(filepath, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(data_dict, ensure_ascii=False, indent=4))
        logger.info(f"Successfully saved explanation to {filepath}")
    except Exception as e:
        logger.error(f"Error saving explanation file {filepath}: {e}")


# --- Основная логика генерации и сохранения ---

def generate_ai_explanation(request: ExplainRequest) -> str:
    """Генерирует объяснение с помощью Google GenAI."""
    if not client:
        raise ConnectionError("Google GenAI client not configured or API key missing.")

    topic = request.topic.strip()  # Убираем лишние пробелы
    base_prompt = f"Тема или вопрос: '{topic}'."

    # Определяем аудиторию и стиль на основе уровня
    if request.level == "5-year-old":
        audience = "для ребенка примерно пяти лет"
        style_prompt = " Объясни это ОЧЕНЬ-ОЧЕНЬ просто. Используй самые базовые слова, короткие предложения (максимум 10 слов). Можно использовать детские сравнения (например, 'представь себе...'). Никаких сложных терминов. Главное - передать самую суть идеи на интуитивном уровне."
    elif request.level == "teenager":
        audience = "для подростка (12-16 лет)"
        style_prompt = " Объясни простыми словами, чтобы понял заинтересованный подросток. Избегай сложного жаргона, но можно использовать базовые аналогии, если они уместны. Сосредоточься на том, почему это интересно или важно. Будь краток и ясен."
    elif request.level == "simple":
        audience = "для взрослого человека без специальных знаний в этой области"
        style_prompt = " Дай максимально простое и понятное объяснение. Фокусируйся на ключевой идее и основной концепции. Избегай глубоких технических деталей и специфической терминологии. Цель - быстрое понимание сути."
    elif request.level == "custom_analogy" and request.analogy:
        audience = "для взрослого человека без специальных знаний в этой области"
        style_prompt = f" Объясни, используя аналогию с '{request.analogy.strip()}'. Сделай эту аналогию ЦЕНТРАЛЬНОЙ частью объяснения. Проведи четкие параллели между темой и аналогией на каждом шаге. Убедись, что аналогия помогает понять тему, а не запутывает."
    elif request.level == "tldr":
        audience = "для любого, кто хочет супер-краткий ответ"
        style_prompt = " Дай ОЧЕНЬ краткое резюме (TL;DR - Too Long; Didn't Read). Объясни самую суть темы в 1-2 предложениях, максимум 40-50 слов. Только ключевая информация."
    elif request.level == "pros_cons":
        audience = "для человека, оценивающего тему"
        style_prompt = " Объясни тему, четко выделив ее основные ПЛЮСЫ (преимущества, сильные стороны) и МИНУСЫ (недостатки, слабые стороны, риски). Структурируй ответ, например, используя подзаголовки 'Плюсы:' и 'Минусы:' или маркированные списки. Будь объективен."
    elif request.level == "metaphor":
        audience = "для взрослого человека без специальных знаний"
        style_prompt = " Придумай и используй подходящую МЕТАФОРУ или яркую аналогию, чтобы объяснить эту тему. Сначала кратко представь метафору, а затем используй ее для объяснения ключевых аспектов темы. Метафора должна быть оригинальной и помогать интуитивному пониманию."
    else:  # Fallback на простое объяснение
        audience = "для взрослого человека без специальных знаний в этой области"
        style_prompt = " Дай простое и понятное объяснение. Фокусируйся на ключевой идее. Избегай жаргона."

    # Общие инструкции для AI
    full_prompt = f"Твоя задача - объяснять сложные темы простыми словами. {base_prompt}\n" \
                  f"Целевая аудитория: {audience}.\n" \
                  f"Стиль и фокус объяснения: {style_prompt}\n" \
                  f"ВАЖНЫЕ ПРАВИЛА:\n" \
                  f"- Отвечай ТОЛЬКО текстом объяснения на языке на котором вопрос.\n" \
                  f"- НЕ используй приветствия ('Привет!', 'Конечно!'), вступления ('В этом объяснении...') или заключения ('Надеюсь, это помогло!').\n" \
                  f"- Форматируй ответ с помощью Markdown (заголовки ##, списки *, **, жирный текст **, курсив *, блоки кода ```), если это улучшает читаемость.\n" \
                  f"- Если тема предполагает код, используй блоки кода Markdown с указанием языка (например, ```python ... ```).\n" \
                  f"- Будь точным, но избегай излишней сложности, соответствуй выбранному уровню.\n" \
                  f"Ответ:"  # Начинаем ответ сразу с объяснения

    logger.info(
        f"Generating content for prompt (style: {request.level}): {full_prompt[:300]}...")  # Логируем больше информации

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=full_prompt,
            # config=generation_config,
        )

        if not response.candidates or response.prompt_feedback.block_reason or response.candidates[
            0].finish_reason != FinishReason.STOP:
            # Логирование причин уже внутри этого блока в предыдущей версии
            error_text = "Извините, не удалось сгенерировать ответ из-за ограничений или ошибки."
            if response.prompt_feedback.block_reason:
                error_text += f" (Причина: {response.prompt_feedback.block_reason})"
            elif not response.candidates:
                error_text += " (Нет кандидатов для ответа)"
            elif response.candidates and response.candidates[0].finish_reason != FinishReason.STOP:
                error_text += f" (Генерация прервана: {response.candidates[0].finish_reason})"
            logger.warning(error_text)
            return error_text  # Возвращаем текст ошибки пользователю

        logger.info(f"Successfully generated response for topic: {request.topic}")
        return response.text.strip()

    except Exception as e:
        logger.error(f"Error generating content via GenAI: {e}", exc_info=True)
        if "API key not valid" in str(e):
            raise ConnectionError("Invalid Google API Key.") from e
        return f"Произошла ошибка при обращении к AI сервису. Пожалуйста, проверьте конфигурацию или попробуйте позже."


async def get_or_create_explanation(request: ExplainRequest) -> tuple[str, Optional[str]]:
    """
    Получает объяснение из файла или генерирует новое.
    Сохраняет в файл ТОЛЬКО если генерация прошла успешно и результат валиден.
    Возвращает: (текст объяснения, slug или None если сохранение не произошло)
    """
    logger.info(f"Processing request for topic: {request.topic}")

    # 1. Сгенерировать slug
    # Учитываем уровень и аналогию в slug, чтобы различать разные объяснения одной темы
    slug_base = request.topic
    if request.level == "custom_analogy" and request.analogy:
        slug_base += f"-аналогия-{request.analogy}"
    elif request.level != "simple":
        slug_base += f"-уровень-{request.level}"

    topic_slug = slugify(f"{request.topic}-{request.level}-{request.analogy or ''}",
                         lowercase=True, separator='-', max_length=80,
                         replacements=[['+', 'plus'], ['#', 'sharp']])  # Добавим реплейсменты

    filepath = get_explanation_filepath(topic_slug)

    # Проверка кеша
    if filepath.is_file():
        logger.info(f"Cache hit: Found existing explanation file for slug: {topic_slug}")
        existing_data = await load_explanation_from_file(topic_slug)
        if existing_data:
            return existing_data.explanation_text, topic_slug

    # Генерация и Валидация
    logger.info(f"Cache miss: Generating explanation for topic: {request.topic}, level: {request.level}")
    explanation_text = None
    generation_error = None
    is_valid_for_saving = False

    try:
        explanation_text = generate_ai_explanation(request)  # Используем улучшенную функцию

        # --- Улучшенная валидация ---
        error_indicators = [
            "извините", "не удалось", "ошибка", "не могу", "ограничений безопасности",
            "невозможно обработать", "сервис недоступен", "api key not valid",
            "произошла ошибка"  # Добавляем общие фразы
        ]
        min_length_threshold = {  # Разная минимальная длина для разных типов
            "tldr": 15,
            "5-year-old": 30,
            "default": 50
        }
        min_len = min_length_threshold.get(request.level, min_length_threshold["default"])

        if not explanation_text:
            logger.warning(f"Validation failed: Empty response for topic: {request.topic}")
            generation_error = "AI вернул пустой ответ."
        elif len(explanation_text) < min_len:
            logger.warning(
                f"Validation failed: Response too short ({len(explanation_text)} < {min_len} chars) for level '{request.level}', topic: {request.topic}")
            # Не сохраняем, но можем вернуть пользователю короткий ответ
        elif any(indicator in explanation_text.lower() for indicator in error_indicators):
            logger.warning(
                f"Validation failed: Response contains error indicators for topic: {request.topic}. Text: {explanation_text[:100]}...")
            # Не сохраняем, возвращаем пользователю текст ошибки
        else:
            is_valid_for_saving = True
            logger.info(f"Validation passed for topic: {request.topic}. Explanation is valid for saving.")
            # --- Конец улучшенной валидации ---

    except ConnectionError as e:
        logger.error(f"ConnectionError during generation: {e}")
        generation_error = f"Ошибка подключения к сервису AI: {e}"
    except Exception as e:
        logger.error(f"Error during generation: {e}", exc_info=True)
        generation_error = "Произошла внутренняя ошибка при генерации объяснения."

    if is_valid_for_saving and explanation_text:
        # 5. Генерируем метаданные
        meta_title = f"Как понять '{request.topic[:40]}' простыми словами | ПростоПонятно.ai"
        sentences = explanation_text.split('.')
        meta_description = (sentences[0] + '.').strip()
        if len(sentences) > 1:
            meta_description += (' ' + sentences[1] + '.').strip()
        meta_description = meta_description[:160].rsplit(' ', 1)[0] + '...'

        # 6. Готовим данные для сохранения
        stored_data = StoredExplanation(
            topic_raw=request.topic,
            slug=topic_slug,
            level=request.level,
            analogy=request.analogy,
            explanation_text=explanation_text,
            meta_title=meta_title,
            meta_description=meta_description,
            created_at=datetime.datetime.now(datetime.timezone.utc)
        )

        # 7. Сохраняем в файл (асинхронно)
        await save_explanation_to_file(stored_data)  # Сохранение происходит ТОЛЬКО здесь

        # 8. Возвращаем успешный результат и slug
        return explanation_text, topic_slug
    else:
        # 9. Если НЕ валидно для сохранения ИЛИ была ошибка генерации
        logger.warning(
            f"Explanation for topic '{request.topic}' (level: {request.level}) will NOT be saved. Valid: {is_valid_for_saving}")
        final_text_to_return = generation_error if generation_error else (
                explanation_text or "Не удалось получить ответ.")
        return final_text_to_return, None


# --- Новая функция для поиска по файлам ---
async def search_explanations(query: str, limit: int = 10) -> List[SearchResultItem]:
    """
    Асинхронно ищет по JSON файлам объяснений.
    Ищет вхождение query (case-insensitive) в topic_raw или начале explanation_text.
    """
    query_lower = query.lower().strip()
    if not query_lower or len(query_lower) < 3:  # Не ищем слишком короткие запросы
        return []

    logger.info(f"Starting search for query: '{query}'")
    # Получаем список всех JSON файлов асинхронно
    try:
        all_files = [f for f in EXPLANATIONS_DIR.glob("*.json")]
    except Exception as e:
        logger.error(f"Error listing explanation files: {e}")
        return []

    # Создаем задачи для чтения и проверки каждого файла
    tasks = [load_and_check_file(filepath, query_lower) for filepath in all_files]

    # Запускаем задачи конкурентно
    checked_results = await asyncio.gather(*tasks)

    # Отфильтровываем None (файлы, которые не подошли или не прочитались)
    # Сортируем по релевантности (сначала те, где совпадение в заголовке)
    matched_items = sorted(
        [res for res in checked_results if res is not None],
        key=lambda item: 0 if query_lower in item.topic.lower() else 1  # Приоритет совпадению в теме
    )

    logger.info(f"Search finished. Found {len(matched_items)} potential matches for query: '{query}'.")
    return matched_items[:limit]  # Возвращаем только топ N результатов


async def load_and_check_file(filepath: Path, query_lower: str) -> Optional[SearchResultItem]:
    """Вспомогательная функция для чтения одного файла и проверки совпадения."""
    try:
        async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            data["created_at"] = datetime.datetime.fromisoformat(data['created_at']) if isinstance(data.get('created_at'), str) else data.get('created_at')
            explanation_data = StoredExplanation(
                **data,
            )

            # Проверка совпадения (в теме ИЛИ в начале текста)
            topic_match = query_lower in explanation_data.topic_raw.lower()
            text_match = query_lower in explanation_data.explanation_text[:500].lower()  # Ищем в первых 500 символах

            if topic_match or text_match:
                return SearchResultItem(
                    topic=explanation_data.topic_raw,
                    slug=explanation_data.slug
                )
            return None
    except Exception as e:
        logger.error(f"Error processing file {filepath} during search: {e}")
        return None


async def get_all_explanation_slugs() -> list[str]:
    """Получает список всех slug'ов из папки explanations."""
    slugs = []
    try:
        for filepath in EXPLANATIONS_DIR.glob("*.json"):
            slugs.append(filepath.stem)
    except Exception as e:
        logger.error(f"Error listing slugs for sitemap: {e}")
    return slugs

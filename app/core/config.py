import os
from dotenv import load_dotenv
from pathlib import Path

# Определяем базовую директорию проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем переменные окружения из .env файла в корне проекта
load_dotenv(dotenv_path=BASE_DIR / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
EXPLANATIONS_DIR = BASE_DIR / "explanations" # Путь к папке с объяснениями

# Убедимся, что директория существует
EXPLANATIONS_DIR.mkdir(parents=True, exist_ok=True)
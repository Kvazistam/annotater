import json
import re
import sqlite3
import os
from dotenv import load_dotenv

from CRUD import read_tale
from nvim_mistral import parse_stream_to_json

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
DB_NAME = os.getenv("DB_NAME")


def init_db():
    """Создает таблицу результатов, если её еще нет."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблица для сохранения результатов.
    # Добавьте сюда другие текстовые поля (например, source, nation), если они нужны
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS folk_tales_annotated (
            id INTEGER PRIMARY KEY,
            title TEXT,
            text TEXT,
            annotation_status TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def get_max_annotated_id():
    """Находит максимальный ID, который уже был успешно обработан."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(ROWID) FROM folk_tales_annotated")
    result = cursor.fetchone()[0]
    conn.close()
    return max(result, 100) if result is not None else 0


def get_unannotated_tales(last_id):
    """Выбирает все сказки из исходной таблицы, у которых ID больше максимального обработанного."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Предполагаем, что в folk_tales есть колонки id, title, text
    cursor.execute(
        "SELECT ROWID, source, nation, title, text FROM folk_tales WHERE ROWID > ? ORDER BY ROWID ASC",
        (last_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def clean_and_parse_json(raw_text):
    """Вырезает JSON из любого мусора нейросети с помощью регулярного выражения."""
    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return None
    return None



def save_result(tale_id, source, nation, title, text, stages_list, warns_content):
    """Сохраняет запись в таблицу folk_tales_annotated."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Переводим список этапов в строку для хранения в БД (например, "call_to_adventure, road_of_trials")
    stages_str = ", ".join(stages_list) if isinstance(stages_list, list) else str(stages_list)
    
    cursor.execute("""
        INSERT OR REPLACE INTO folk_tales_annotated (id, source, nation, title, text, stages, warns)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (tale_id, source, nation, title, text, stages_str, warns_content))
    conn.commit()
    conn.close()

def main(ask_ai):
    init_db()

    # Шаг 1: Узнаем, на каком ID остановились
    last_id = get_max_annotated_id()
    print(f"[*] Последний обработанный ID в folk_tales_annotated: {last_id}")

    # Шаг 2: Получаем новые сказки
    tales = get_unannotated_tales(last_id)
    if not tales:
        print("[✓] Все сказки уже обработаны! Новых записей нет.")
        return

    print(f"[*] Найдено {len(tales)} новых сказок для обработки.")

    # Шаг 3: Цикл обработки
    for tale_id, source, nation, title, text in tales:
        print(f"-> Обрабатывается сказка ID {tale_id}: '{title}' ({nation})...")

        # Интегрируем ваш экспертный промпт
        prompt = f"""Ты эксперт по мономифу Дж. Кэмпбелла. Твоя задача — разметить сказку, вставляя теги этапов прямо в текст.

## ЭТАПЫ (используй ТОЧНО эти теги)
### Departure
<stage_call_to_adventure> | <stage_refusal_of_call> | <stage_supernatural_aid> | <stage_crossing_threshold> | <stage_belly_of_whale>
### Initiation  
<stage_road_of_trials> | <stage_meeting_goddess> | <stage_woman_as_temptress> | <stage_atonement_father> | <stage_apotheosis> | <stage_ultimate_boon>
### Return
<stage_refusal_return> | <stage_magic_flight> | <stage_rescue_from_without> | <stage_crossing_return_threshold> | <stage_master_two_worlds> | <stage_freedom_to_live>

## ПРАВИЛА
✅ Вставляй теги в формате <stage_name>текст</stage_name> вокруг соответствующих фрагментов.
✅ Сохраняй оригинальный текст дословно — ничего не удаляй, не меняй, не сокращай.
✅ Если этап отсутствует — просто пропусти его, не выдумывай.
✅ Если сказка слишком короткая (<150 слов) или бессвязная — верни текст как есть и добавь в конец "# UNSTRUCTURED".
✅ Если один фрагмент подходит под несколько этапов — ставь теги подряд: <stage_a><stage_b>текст</stage_b></stage_a>

## ФОРМАТ ОТВЕТА (строго JSON)
{{
  "annotated_text": "размеченный текст с тегами",
  "stages_found": ["call_to_adventure", "crossing_threshold", ...],
  "warning": null или "# UNSTRUCTURED"
}}

## ПРИМЕР (few-shot)
Input: "Little Red Riding Hood was asked by her mother to take food to her grandmother..."
Output: {{
  "annotated_text": "<stage_call_to_adventure>Little Red Riding Hood was asked by her mother to take food to her grandmother who lived in the forest.</stage_call_to_adventure> She set out... <stage_crossing_threshold>She entered the forest.</stage_crossing_threshold>...",
  "stages_found": ["call_to_adventure", "crossing_threshold", "road_of_trials", "belly_of_whale", "rescue_from_without"],
  "warning": null
}}

Входные данные для разметки:
Источник: {source}
Народность: {nation}
Название: {title}
Текст: {text}
"""

        try:
            # Запрос к Gemini с защитой от падений
            raw_response = ask_ai(prompt)

            # Очистка и парсинг вашим JSON-шаблоном
            parsed_json = clean_and_parse_json(raw_response)

            if parsed_json and "annotated_text" in parsed_json:
                annotated_text = parsed_json["annotated_text"]
                stages_found = parsed_json.get("stages_found", [])
                warning = parsed_json.get("warning", None)
                
                # Сохраняем:
                # В поле text уходит РАЗМЕЧЕННЫЙ текст сказки (как вы просили в структуре таблицы)
                # В поле stages уходит список найденных этапов через запятую
                # В поле warns уходит значение предупреждения (null или # UNSTRUCTURED)
                save_result(tale_id, source, nation, title, annotated_text, stages_found, warning)
                print(f"   [✓] Успешно размечено и сохранено.")
            else:
                print(f"   [X] Ошибка: Не удалось извлечь JSON нужного формата для ID {tale_id}.")
                save_result(tale_id, source, nation, title, text, "error", f"Ошибка парсинга JSON. Сырой ответ: {raw_response}")
            
        
        except Exception as e:
            print(f"   [X] Скрипт остановлен из-за критической ошибки на ID {tale_id}: {e}")
            break

    print("[*] Обработка полностью завершена.")


def manual_insert(id, ai_responce):
    with open(ai_responce, 'r', encoding='utf-8') as fp:
        raw = fp.read()
        ai_text = parse_stream_to_json(raw)
        d = clean_and_parse_json(ai_text)
        tale = read_tale(id)
        save_result(id, tale['source'], tale['nation'], tale['title'], d['annotated_text'], d['stages_found'], d.get('warnings', ""))

# manual_insert(103, r'checkpoints\ai_response20-07-03')
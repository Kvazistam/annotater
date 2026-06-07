import sqlite3
from typing import Optional, Dict, List, Any

DB_PATH = "tales.db"

def get_db_connection() -> sqlite3.Connection:
    """Открывает соединение с оптимизациями для скриптов."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Доступ к полям по имени: row["title"]
    conn.execute("PRAGMA journal_mode=WAL;")  # Быстрая запись, защита от блокировок
    return conn

def read_tale(tale_id: int, table = 'folk_tales') -> Optional[Dict[str, Any]]:
    """Читает одну сказку по ID из исходной таблицы."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT ROWID as id, source, nation, title, text FROM {table} WHERE ROWID = ?",
            (tale_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

def save_annotated_tale(
    tale_id: int,
    source: str,
    nation: str,
    title: str,
    annotated_text: str,
    stages: List[str],
    warns: Optional[str] = None
) -> None:
    """Вставляет или обновляет размеченную сказку в таблице результатов."""
    stages_str = ", ".join(stages) if isinstance(stages, list) else str(stages)
    
    with get_db_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO folk_tales_annotated 
            (id, source, nation, title, text, stages, warns)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tale_id, source, nation, title, annotated_text, stages_str, warns))
        conn.commit()

def delete_tale(tale_id: int, table: str = 'folk_tales_annotated') -> bool:
    """
    Удаляет сказку по ID из указанной таблицы.
    
    :param tale_id: ID сказки (соответствует ROWID в исходной или id в аннотированной).
    :param table: Имя таблицы для удаления (по умолчанию 'folk_tales_annotated').
    :return: True, если запись была найдена и удалена, иначе False.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # В исходной таблице надежнее искать по ROWID, 
        # в таблице результатов - по явной колонке 'id'
        id_column = "ROWID" if table == "folk_tales" else "id"
        
        cursor.execute(
            f"DELETE FROM {table} WHERE {id_column} = ?",
            (tale_id,)
        )
        conn.commit()
        
        # cursor.rowcount содержит количество затронутых (удаленных) строк
        return cursor.rowcount > 0
import re
from typing import List, Tuple, Dict


class TagMerger:
    """Автоматически вставляет теги из ответа ИИ в исходный текст."""
    
    @staticmethod
    def extract_tagged_fragments(ai_response: str) -> List[Tuple[str, str]]:
        pattern = r'(?P<context_before>([^<>\n]{0,50}))(?P<stage><[/]?stage_\w+>)(?P<context_after>([^<>\n]{0,50}))'
        # Более надёжный вариант для вложенных/смежных тегов:
        fragments = []
        # Ищем все открытия тегов
        for match in re.finditer(pattern, ai_response):
            d = match.groupdict()
            g = (d['stage'], d['context_before'], d['context_after'])
            fragments.append(g)
        print(fragments)
        return fragments

    @staticmethod
    def find_text_positions(original: str, fragments: List[Tuple[str, str]]) -> List[Dict]:
        """Находит позиции каждого фрагмента в исходном тексте."""
        annotated = ''
        original_clean = ' '.join(original.split())
        for tag,suffix, prefix   in fragments:
            # Ищем точное вхождение (с очисткой от лишних пробелов для надёжности)
            suffix_clean = ' '.join(suffix.split())
            prefix_clean = ' '.join(prefix.split())
            
            
            
            if prefix:
                end = original_clean.find(prefix_clean)
                if end != -1:
                    original_clean = original_clean[:end]+tag+original_clean[end:]

            elif suffix:
                start = original_clean.find(suffix_clean)
                if start != -1:
                    start += len(suffix_clean)
                    original_clean = original_clean[:start]+tag+original_clean[start:]
        return original_clean
            

    @staticmethod
    def process(original: str, ai_response: str) -> str:
        """Полный пайплайн: извлечение → поиск → вставка."""
        fragments = TagMerger.extract_tagged_fragments(ai_response)
        if not fragments:
            print("тегов нет")
            return original  # Если тегов нет, возвращаем как есть
        return TagMerger.find_text_positions(original, fragments)


    

def save_chat(file, id = 1):
    with open(file, 'r', encoding='utf-8') as chat:
        resp = chat.read()
        resp = re.sub(r'[“”]','"', resp)
    tale = read_tale(id)
    text = re.sub(r'[“”]','"', tale['text'])
    
    
    merger = TagMerger()
    annotated = merger.process(text, resp)  
    stages = [],
    
    save_annotated_tale(id,tale['source'], tale['nation'], tale['title'], annotated, stages)
    
def copy_text(file, id, table = 'folk_tales'):
    with open(file, 'w', encoding='utf-8') as fp:
        tale = read_tale(id, table=table)
        fp.write(tale['text'])

if __name__ == "__main__":
    id = 102
    # copy_text('tmp', id, 'folk_tales')
    # save_chat('chat_response', id); copy_text('tmp', id, 'folk_tales_annotated')
    for i in range(104,110):
        delete_tale(i)
    
    
    
    # tale = read_tale(id)
    # t = '"In mansion deck’d with frieze and column,\nDwelt dogs and cats in multitudes;\nDecrees, promulged in manner solemn,\nHad pacified their ancient feuds.\nTheir lord had so arranged their meals and labours,\nAnd threaten’d quarrels with the whip,\nThat, living in sweet cousinship,\nThey edified their wondering neighbours.\n<stage_call_to_adventure>At last, some dainty plate to lick,\nOr profitable bone to pick,\nBestow’d by some partiality,\nBroke up the smooth equality.\nThe side neglected were indignant\nAt such a slight malignant.</stage_call_to_adventure>\n<stage_crossing_threshold>From words to blows the altercation\nSoon grew a perfect conflagration.</stage_crossing_threshold>\n<stage_road_of_trials>In hall and kitchen, dog and cat\nTook sides with zeal for this or that.\nNew rules upon the cat side falling\nProduced tremendous caterwauling.\nTheir advocate, against such rules as these,\nAdvised recurrence to the old decrees.\nThey search’d in vain, for, hidden in a nook,\n<stage_belly_of_whale>The thievish mice had eaten up the book.</stage_belly_of_whale>\nAnother quarrel, in a trice,\nMade many sufferers with the mice;\nFor many a veteran whisker’d-face,\nWith craft and cunning richly stored,\nAnd grudges old against the race,\nNow watch’d to put them to the sword;\nNor mourn’d for this that mansion’s lord.</stage_road_of_trials>\n<stage_ultimate_boon>Look wheresoever we will, we see\nNo creature from opponents free.\n‘Tis nature’s law for earth and sky;\n‘Twere vain to ask the reason why:\nGod’s works are good,—I cannot doubt it,—\nAnd that is all I know about it.</stage_ultimate_boon>'
    # save_annotated_tale(id, tale['source'], tale['nation'], tale['title'], t, ["call_to_adventure", "crossing_threshold", "road_of_trials", "belly_of_whale", "ultimate_boon"])
    
import os
import re
import math
import json
import urllib.request
import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import defaultdict

# ==========================================
# НАСТРОЙКИ
# ==========================================
YML_URL = "https://ctradei.com/x/shop2_1410641-yml.xml"
LOCAL_YML_FILE = "supplier_catalog.xml"
OUTPUT_AVITO_XML = "avito_feed.xml"
ID_MAP_FILE = "id_map.json"

# Базовый адрес твоих обложек с GitHub Pages
GITHUB_COVERS_BASE = "https://vasily58pnz.github.io/avito-beds2/covers"

ID_PREFIX = "MNT-"

STATIC_BRAND = "СИТРЕЙД"
MARGIN_MULTIPLIER = 1.30
DELIVERY_FEE = 500  # Добавлено 500 рублей к каждому товару для бесплатной доставки
PRICE_ROUND_STEP = 50
AVITO_ADDRESS = "Санкт-Петербург, улица Циолковского, 9"

MIN_STOCK = 1
SKIP_BEDSPREADS = False

OUT_OF_STOCK_STOP_WORDS = [
    "под заказ", "подзаказ", "ожидается", "нет в наличии", 
    "нет на складе", "под заказ от", "недоступен", "отсутствует", "0 шт", "0шт"
]


def load_id_map(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"📖 Загружена карта ID из {filepath}: {len(data)} записей.")
                return data
        except Exception as e:
            print(f"⚠️ Ошибка чтения {filepath}: {e}. Создается новая база.")
    return {}


def save_id_map(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Карта ID успешно сохранена в {filepath} (всего: {len(data)} шт.)")
    except Exception as e:
        print(f"❌ Ошибка сохранения {filepath}: {e}")


def extract_video_file_url(raw_video_str):
    if not raw_video_str:
        return ""
        
    parts = re.split(r'[,;\s]+', str(raw_video_str).strip())
    
    for link in parts:
        link = link.strip()
        if not link:
            continue
            
        is_yandex_disk = any(d in link.lower() for d in ["disk.yandex.ru", "disk.360.yandex.ru", "yadi.sk"])
        is_direct_video = bool(re.search(r'\.(mp4|mov|hevc|webm)(\?[^\s<>"]*)?$', link, flags=re.IGNORECASE))
        
        if is_yandex_disk or is_direct_video:
            return link
            
    return ""


def download_supplier_feed(url, local_path):
    print("Скачивание фида поставщика...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(local_path, 'wb') as out_file:
            out_file.write(response.read())
        print("Фид успешно скачан.")
        return True
    except Exception as e:
        print(f"Ошибка при скачивании: {e}")
        if os.path.exists(local_path):
            print("Используем локальный файл...")
            return True
        return False


def round_up_price(price, step=50):
    return int(math.ceil(price / step) * step)


def truncate_title(title, max_len=90):
    title = title.strip()
    if len(title) <= max_len:
        return title
    truncated = title[:max_len]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.strip()


def determine_subtype(title):
    title_lower = title.lower()
    if "наматрасник" in title_lower or "топпер" in title_lower:
        return "Наматрасники"
    elif "подушк" in title_lower:
        return "Подушки"
    elif "покрывал" in title_lower:
        return "Покрывала"
    elif "плед" in title_lower:
        return "Пледы"
    
    if "наволочк" in title_lower and not any(kw in title_lower for kw in ["комплект", "кпб", "постельное белье"]):
        return "Наволочки"
    if "простын" in title_lower and not any(kw in title_lower for kw in ["комплект", "кпб", "постельное белье"]):
        return "Простыни"
    if "пододеяльник" in title_lower and not any(kw in title_lower for kw in ["комплект", "кпб", "постельное белье"]):
        return "Пододеяльники"
        
    return "Комплект постельного белья"


def normalize_avito_bed_linen_size(size_str):
    raw = (size_str or "").lower()
    if "1.5" in raw or "полутор" in raw:
        return "Полуторный"
    if "2.0" in raw or "2" in raw or "двуспальн" in raw:
        return "Двуспальный"
    if "дуэт" in raw or "семейн" in raw:
        return "Семейный"
    return "Евро"


def detect_exact_offer_size(offer_elem, title, raw_desc, params_dict, category_names):
    exact_param = (
        params_dict.get("Выбрать размер", "") + " " +
        params_dict.get("Размер", "") + " " +
        params_dict.get("Размер комплекта", "")
    ).lower()

    if "1.5" in exact_param or "полутор" in exact_param:
        return "1.5-спальный"
    if "2.0" in exact_param or "2-спальн" in exact_param or "2 спальн" in exact_param or "двуспальн" in exact_param:
        return "2-спальный"
    if "дуэт" in exact_param or "семейн" in exact_param:
        return "Семейный"
    if "евро" in exact_param or "euro" in exact_param:
        return "Евро"

    url_text = (offer_elem.findtext("url") or "").lower()
    if re.search(r'[-_/](1sp|1-sp|1[\.,\-_]5|polutor|1-5|1_5)', url_text):
        return "1.5-спальный"
    if re.search(r'[-_/](2sp|2-sp|2[\.,\-_]0|2-spaln|2spaln)', url_text):
        return "2-спальный"
    if re.search(r'[-_/](duet|fam|semejn)', url_text):
        return "Семейный"
    if re.search(r'[-_/](euro|evro)', url_text):
        return "Евро"

    cat_id = offer_elem.findtext("categoryId") or ""
    cat_name = category_names.get(cat_id, "").lower()
    if "1.5" in cat_name or "полутор" in cat_name:
        return "1.5-спальный"
    if "2" in cat_name or "двуспальн" in cat_name:
        return "2-спальный"
    if "дуэт" in cat_name or "семейн" in cat_name:
        return "Семейный"
    if "евро" in cat_name or "euro" in cat_name:
        return "Евро"

    title_lower = title.lower()
    if re.search(r'\b(1[\.,]5|1[\.,]5\s*сп|полуторн\w*)\b', title_lower):
        return "1.5-спальный"
    if re.search(r'\b(2[\.,]0|2-?спальн\w*|2-?сп\b|двуспальн\w*)\b', title_lower):
        return "2-спальный"
    if re.search(r'\b(дуэт|семейн\w*)\b', title_lower):
        return "Семейный"
    if re.search(r'\b(евро|euro)\b', title_lower):
        return "Евро"

    return "Евро"


def parse_dimensions_from_supplier_section(offer_elem, raw_desc, target_size, params_dict):
    clean_desc = re.sub(r'<[^>]+>', '\n', raw_desc)
    url_text = (offer_elem.findtext("url") or "").lower()

    param_nav = (
        params_dict.get("Выбрать наволочки", "") + " " +
        params_dict.get("Наволочки", "") + " " +
        params_dict.get("Размер наволочек", "")
    ).lower()

    if "50-70" in param_nav or "50*70" in param_nav or "50х70" in param_nav or "sp50" in url_text:
        pillow = "50х70 см (2 шт.)"
    elif "70-70" in param_nav or "70*70" in param_nav or "70х70" in param_nav or "sp70" in url_text:
        pillow = "70х70 см (2 шт.)"
    elif "4" in param_nav:
        pillow = "4 шт. (50х70 см — 2 шт. + 70х70 см — 2 шт.)"
    else:
        pillow = "70х70 см (2 шт.)"

    section_patterns = {
        "1.5-спальный": r'(?:1[\.,]5\s*спальн\w*|1[\.,]5\s*сп)',
        "2-спальный": r'(?:2\s*спальн\w*|2[\.,]0\s*сп|двуспальн\w*)',
        "Евро": r'(?:евро(?!\s*макси)|euro)',
        "Семейный": r'(?:дуэт|семейн\w*)'
    }
    target_pat = section_patterns.get(target_size, r'евро')
    match = re.search(target_pat, clean_desc, flags=re.IGNORECASE)
    section_text = ""
    if match:
        start_pos = match.start()
        tail = clean_desc[start_pos:]
        other_pats = [p for k, p in section_patterns.items() if k != target_size]
        next_pos = len(tail)
        for op in other_pats:
            m_next = re.search(r'\n\s*' + op, tail[15:], flags=re.IGNORECASE)
            if m_next:
                next_pos = min(next_pos, m_next.start() + 15)
        section_text = tail[:next_pos]

    param_duvet = (params_dict.get("Размер пододеяльника", "") or params_dict.get("Пододеяльник", "")).strip()
    m_d = re.search(r'(\d{2,3})\s*[\*хx×-]\s*(\d{2,3})', param_duvet)
    if not m_d:
        m_d = re.search(r'пододеяльник[^\d\n]*(\d{2,3})\s*[\*хx×-]\s*(\d{2,3})', section_text, flags=re.IGNORECASE)

    cnt_str = " (2 шт.)" if target_size == "Семейный" else " (1 шт.)"
    if m_d:
        duvet = f"{m_d.group(1)}х{m_d.group(2)} см{cnt_str}"
    else:
        defaults_d = {"1.5-спальный": "150х210 см", "2-спальный": "180х215 см", "Евро": "200х220 см", "Семейный": "150х210 см"}
        duvet = f"{defaults_d.get(target_size, '200х220 см')}{cnt_str}"

    is_elastic = ("резин" in params_dict.get("Тип простыни", "").lower()) or ("резин" in url_text)
    m_s = re.search(r'простын[^\d\n]*(\d{2,3})\s*[\*хx×-]\s*(\d{2,3})(?:\s*[\*хx×\+]+\s*(\d{2}))?', section_text, flags=re.IGNORECASE)
    
    if m_s:
        w, l = m_s.group(1), m_s.group(2)
        h = m_s.group(3)
        h_str = f"+{h}" if h else ""
        pfx = "на резинке" if is_elastic else "обычная"
        sheet = f"{pfx} {w}х{l}{h_str} см"
    else:
        defaults_s = {"1.5-спальный": "180х220 см", "2-спальный": "200х230 см", "Евро": "220х230 см", "Семейный": "220х230 см"}
        pfx = "на резинке" if is_elastic else "обычная"
        sheet = f"{pfx} {defaults_s.get(target_size, '220х230 см')}"

    return duvet, sheet, pillow


def extract_item_dimensions(title, params_dict, raw_description="", url=""):
    if url:
        match_url = re.search(r'(1\d{2}|2\d{2})[-xх](1\d{2}|2\d{2})', url.lower())
        if match_url:
            return f"{match_url.group(1)}х{match_url.group(2)} см"

    scan_primary = f"{params_dict.get('Выбрать размер', '')} {params_dict.get('Размер', '')} {params_dict.get('Размер комплекта', '')} {params_dict.get('Размер покрывала', '')} {params_dict.get('Размер пододеяльника', '')} {params_dict.get('Габариты', '')} {title}".lower()
    
    match_primary = re.search(r'(?<!\d)(1[0-9]{2}|2[0-9]{2})\s*[\*хx×-]\s*(1[0-9]{2}|2[0-9]{2})(?!\d)', scan_primary)
    if match_primary:
        return f"{match_primary.group(1)}х{match_primary.group(2)} см"

    match_desc = re.search(r'(?<!\d)(1[0-9]{2}|2[0-9]{2})\s*[\*хx×-]\s*(1[0-9]{2}|2[0-9]{2})(?!\d)', raw_description.lower())
    if match_desc:
        return f"{match_desc.group(1)}х{match_desc.group(2)} см"

    return "240х260 см"


def parse_bedsheet_numeric(title, params_dict, raw_description=""):
    scan = f"{params_dict.get('Выбрать размер', '')} {params_dict.get('Размер простыни', '')} {params_dict.get('Размер', '')} {title} {raw_description}".lower()
    is_elastic = "резин" in scan
    type_str = "На резинке" if is_elastic else "Обычная"
    
    match = re.search(r'(?<!\d)(8\d|9\d|1\d{2}|2\d{2})\s*[\*хx×-]\s*(1\d{2}|2\d{2})(?!\d)', scan)
    if match:
        w, l = int(match.group(1)), int(match.group(2))
        return str(min(w, l)), str(max(w, l)), type_str
    if is_elastic:
        return "160", "200", type_str
    return "220", "240", type_str


def parse_pillowcase_numeric(title, params_dict, raw_description=""):
    scan = f"{params_dict.get('Выбрать наволочки', '')} {params_dict.get('Размер наволочки', '')} {params_dict.get('Размер наволочек', '')} {params_dict.get('Наволочки', '')} {title} {raw_description}".lower()
    count = 4 if "4" in scan else 2
    
    match = re.search(r'(?<!\d)(4\d|5\d|6\d|7\d)\s*[\*хx×-]\s*(5\d|6\d|7\d)(?!\d)', scan)
    if match:
        w, l = int(match.group(1)), int(match.group(2))
        return str(min(w, l)), str(max(w, l)), str(count)
    if "50" in scan and "70" in scan:
        return "50", "70", str(count)
    return "70", "70", str(count)


def parse_duvet_numeric(title, params_dict, raw_description=""):
    scan = f"{params_dict.get('Выбрать размер', '')} {params_dict.get('Размер пододеяльника', '')} {params_dict.get('Размер', '')} {title} {raw_description}".lower()
    
    match = re.search(r'(?<!\d)(1\d{2}|2\d{2})\s*[\*хx×-]\s*(1\d{2}|2\d{2})(?!\d)', scan)
    if match:
        w, l = int(match.group(1)), int(match.group(2))
        return str(min(w, l)), str(max(w, l))
    return "200", "220"


def format_supplier_description_block(raw_desc):
    if not raw_desc:
        return ""
    text = re.sub(r'<(?:br|br\s*/|/p|/li|/div)>', '\n', raw_desc, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    
    stop_patterns = [
        r'размер[ыа-я]*\s+(?:комплект|издели|покрывал|плед)\w*[:\s]?',
        r'размер[ы]?\s*:',
        r'комплектаци[яи]\s*:'
    ]
    for pat in stop_patterns:
        parts = re.split(pat, text, flags=re.IGNORECASE)
        text = parts[0]
        
    lines = text.split('\n')
    paragraphs = []
    dim_keywords_strict = [
        r'пододеяльник', r'простын', r'наволочк',
        r'1[\.,]5\s*сп', r'1\.5\s*спальн', r'2[\.,]0\s*сп', r'2-?спальн',
        r'евро-?макси', r'евро-?стандарт', r'семейн', r'покрывало\s*:\s*\d+',
        r'^\s*размеры\s*$'
    ]
    
    for line in lines:
        clean_line = line.strip()
        if not clean_line or any(re.search(kw, clean_line.lower()) for kw in dim_keywords_strict):
            continue
        if re.search(r'^\D{0,15}\d{2,3}\s*[\*хx×-]\s*\d{2,3}\D{0,10}$', clean_line):
            continue
        clean_line = re.sub(r'["\'«»„“”`]', '', clean_line).strip()
        clean_line = re.sub(r'^(Ткань|Состав|Плотность|Наполнитель|Состав наполнителя|Метод окрашивания|Окрашивание|Упаковка|Особенности)\s*:\s*(.*)', r'🔹 <b>\1:</b> \2', clean_line, flags=re.IGNORECASE)
        paragraphs.append(clean_line)
        
    if not paragraphs:
        return ""
    return f"<p><b>✨ Описание материала и упаковки:</b><br>{'<br>'.join(paragraphs)}</p>"


def extract_textile_material(title, params_dict):
    raw = f"{params_dict.get('Ткань', '')} {params_dict.get('Материал', '')} {title}".lower()
    materials = ["сатин", "поплин", "бязь", "перкаль", "жаккард", "ранфорс", "трикотаж", "махра", "микрофибра", "шелк", "лен", "фланель", "бамбук", "тенсель", "полиэстер", "хлопок"]
    for mat in materials:
        if mat in raw:
            return mat.capitalize()
    return "Сатин"


def extract_main_composition(title, params_dict):
    raw = f"{params_dict.get('Ткань', '')} {params_dict.get('Материал', '')} {title}".lower()
    for comp in ["велюр", "хлопок", "полиэстер", "акрил", "бамбук", "вискоза", "кашемир", "лен", "мех", "тенсель", "шелк", "шерсть"]:
        if comp in raw:
            return comp.capitalize()
    return "Велюр" if "велюр" in raw else "Хлопок"


def generate_group_title(base_title, subtype, material, size_label, has_multiple_sizes=True):
    title = base_title.strip()
    
    title = re.sub(r'\b\d+[\s]*%[\s]*', '', title)
    title = re.sub(r'%+', '', title)
    
    title = re.sub(r'арт\.?\s*[\w-]+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\b[A-Za-z]{1,5}[-_]?\d+[A-Za-z0-9\-_]*\b', '', title)
    title = re.sub(r'\b\d{3,}[A-Za-z0-9\-_]*\b', '', title)
    title = re.sub(r'\b[A-Za-z]+\d+\b', '', title)
    
    title = re.sub(r'\b\d{2,3}\s*[\*хx×-]\s*\d{2,3}\b', '', title)
    title = re.sub(r'\b(полуторн\w*|1[\.,]5|2-?спальн\w*|2[\.,]0|евро-?макси|евро|семейн\w*|дуэт)\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\(.*?\)', '', title)
    title = re.sub(r'["\'«»„“”`]', '', title)
    
    junk_patterns = [
        r'\bдля\s+(бабушк\w*|мам\w*|женщин\w*|мужчин\w*|девушк\w*|детей|ребенка|девочк\w*|мальчик\w*|подруг\w*)\b',
        r'\b(узор|буквы|надпись|полосы|геометрия|абстракция|цветы|однотонный|рисунок)\b',
        r'\b(в подарок|на свадьбу|на юбилей|на новоселье)\b'
    ]
    for pat in junk_patterns:
        title = re.sub(pat, '', title, flags=re.IGNORECASE)
        
    clean_base = re.sub(r'[,/\\|\-–—\s]+', ' ', title).strip(' ,/-–—|')
    
    if len(clean_base) < 10:
        clean_base = f"{subtype} {material}"

    if has_multiple_sizes:
        size_tag = " (Все размеры)"
    else:
        size_tag = f" {size_label}" if size_label else ""

    full_title = f"{clean_base}{size_tag}".strip()
    
    if len(full_title) > 90:
        avail_len = 90 - len(size_tag)
        short_base = truncate_title(clean_base, avail_len)
        short_base = re.sub(r'\b(для|с|со|в|во|на|и|по|из|от|к|над|под)\b[\s,\.\-–—/]*$', '', short_base, flags=re.IGNORECASE).strip(' ,/-–—|')
        return f"{short_base}{size_tag}".strip()

    return full_title.strip(' ,/-–—|')


def parse_yml_and_build_avito(yml_path, output_path):
    if not os.path.exists(yml_path):
        print(f"Файл {yml_path} не найден.")
        return

    # Загружаем сохраненные соответствия ID
    id_map = load_id_map(ID_MAP_FILE)

    print("Парсинг YML фида...")
    tree = ET.parse(yml_path)
    root = tree.getroot()

    category_names = {}
    for cat in root.findall(".//category"):
        c_id = str(cat.attrib.get("id", "")).strip()
        c_text = cat.text.strip() if cat.text else ""
        if c_id and c_text:
            category_names[c_id] = c_text

    offers = root.findall(".//offer")
    print(f"Найдено исходных товаров в YML: {len(offers)}")

    groups = defaultdict(list)
    skipped_custom_order = 0

    for offer in offers:
        available = offer.attrib.get("available", "true")
        if available.lower() in ["false", "0"]:
            continue
            
        quantity_elem = offer.find("quantity") or offer.find("stock")
        if quantity_elem is not None and quantity_elem.text:
            try:
                if int(quantity_elem.text) < MIN_STOCK:
                    continue
            except ValueError:
                pass

        offer_id = str(offer.attrib.get("id", "")).strip()
        name_elem = offer.find("name")
        title = name_elem.text.strip() if (name_elem is not None and name_elem.text) else ""
        if not title:
            model_elem = offer.find("model")
            vendor_elem = offer.find("vendor")
            title = f"{vendor_elem.text if vendor_elem is not None else ''} {model_elem.text if model_elem is not None else ''}".strip()
            
        if not title:
            continue

        price_elem = offer.find("price")
        if price_elem is None or not price_elem.text:
            continue
            
        try:
            wholesale_price = float(price_elem.text.strip())
            raw_retail_price = (wholesale_price * MARGIN_MULTIPLIER) + DELIVERY_FEE
            retail_price = round_up_price(raw_retail_price, PRICE_ROUND_STEP)
        except ValueError:
            continue

        desc_elem = offer.find("description")
        raw_desc = desc_elem.text.strip() if (desc_elem is not None and desc_elem.text) else ""
        url_text = offer.findtext("url") or ""

        params_dict = {}
        for param in offer.findall("param"):
            p_name = param.attrib.get("name", "").strip()
            p_val = param.text.strip() if param.text else ""
            if p_name and p_val:
                params_dict[p_name] = p_val

        stock_status_text = f"{params_dict.get('Наличие', '')} {params_dict.get('Наличие на складе', '')} {params_dict.get('Склад', '')} {params_dict.get('Статус', '')} {title}".lower()

        if any(stop_phrase in stock_status_text for stop_phrase in OUT_OF_STOCK_STOP_WORDS):
            skipped_custom_order += 1
            continue

        vendor_code = (offer.findtext("vendorCode") or params_dict.get("Артикул", "") or params_dict.get("Код", "") or "").strip().upper()
        group_id_attr = offer.attrib.get("group_id", "").strip()
        
        pictures = [p.text.strip() for p in offer.findall("picture") if p.text and p.text.strip()]
        main_photo = pictures[0] if pictures else ""

        if group_id_attr:
            group_key = f"GRP_{group_id_attr}"
        elif vendor_code:
            base_code_clean = re.sub(r'[-_](1\.5|2\.0|E|EURO|DUET|FAM|5070|7070|1SP|2SP).*$', '', vendor_code)
            group_key = f"CODE_{base_code_clean}"
        elif main_photo:
            group_key = f"IMG_{main_photo}"
        else:
            group_key = f"ID_{offer_id}"

        offer_size = detect_exact_offer_size(offer, title, raw_desc, params_dict, category_names)
        duvet_det, sheet_det, pillow_det = parse_dimensions_from_supplier_section(offer, raw_desc, offer_size, params_dict)
        direct_dims = extract_item_dimensions(title, params_dict, raw_desc, url_text)
        
        raw_supplier_video = params_dict.get("Яндекс Видео", "") or \
                             params_dict.get("Ссылка на видео", "") or \
                             params_dict.get("Видео", "")
        feed_video = extract_video_file_url(raw_supplier_video)

        groups[group_key].append({
            "offer_id": offer_id,
            "group_id": group_id_attr,
            "title": title,
            "price": retail_price,
            "vendor_code": vendor_code,
            "params": params_dict,
            "pictures": pictures,
            "description": raw_desc,
            "size": offer_size,
            "direct_dims": direct_dims,
            "pillow_details": pillow_det,
            "duvet_details": duvet_det,
            "sheet_details": sheet_det,
            "feed_video": feed_video
        })

    print(f"🛡️ Отфильтровано товаров 'под заказ': {skipped_custom_order} шт.")
    print(f"Сформировано уникальных объявлений (строго 1 объявление на дизайн): {len(groups)}")

    ads_node = ET.Element("Ads", formatVersion="3", target="Avito.ru")
    attached_videos_log = []
    processed_count = 0
    desc_storage = {}
    video_storage = {}

    for group_key, items in groups.items():
        primary_item = items[0]
        base_code = primary_item["vendor_code"] or primary_item["offer_id"]
        base_title = primary_item["title"]
        params_dict = primary_item["params"]
        subtype = determine_subtype(base_title)
        
        if SKIP_BEDSPREADS and subtype in ["Покрывала", "Пледы"]:
            continue

        # -------------------------------------------------------------
        # СТАБИЛЬНЫЙ МЕХАНИЗМ ID ЧЕРЕЗ id_map.json
        # -------------------------------------------------------------
        # Уникальный ключ модели (отрезаем суффиксы размеров, если они есть)
        clean_model_key = re.sub(r'[-_](1\.5|2\.0|E|EURO|DUET|FAM|5070|7070|1SP|2SP).*$', '', base_code).strip()
        if not clean_model_key:
            clean_model_key = group_key

        if clean_model_key in id_map:
            # 1. Если модель уже публиковалась — берем ее постоянный ID
            final_ad_id = id_map[clean_model_key]
        else:
            # 2. Если новинка: берем group_id или стабильный минимальный offer_id
            group_id_val = primary_item.get("group_id") or ""
            if group_id_val:
                chosen_num = group_id_val
            else:
                digits = [int(it["offer_id"]) for it in items if it["offer_id"].isdigit()]
                chosen_num = str(min(digits)) if digits else primary_item["offer_id"]

            final_ad_id = f"{ID_PREFIX}{chosen_num}"
            id_map[clean_model_key] = final_ad_id

        min_price = min(item["price"] for item in items)

        if subtype == "Комплект постельного белья":
            unique_sizes = set(it["size"] for it in items)
            has_multiple = len(unique_sizes) > 1
            single_size_label = primary_item["size"]
        elif subtype == "Пододеяльники":
            d_w, d_l = parse_duvet_numeric(base_title, params_dict, primary_item["description"])
            single_size_label = f"{d_w}х{d_l} см"
            unique_sizes = set(parse_duvet_numeric(it["title"], it["params"], it["description"]) for it in items)
            has_multiple = len(unique_sizes) > 1
        elif subtype == "Простыни":
            s_w, s_l, _ = parse_bedsheet_numeric(base_title, params_dict, primary_item["description"])
            single_size_label = f"{s_w}х{s_l} см"
            unique_sizes = set(parse_bedsheet_numeric(it["title"], it["params"], it["description"])[:2] for it in items)
            has_multiple = len(unique_sizes) > 1
        elif subtype == "Наволочки":
            p_w, p_l, _ = parse_pillowcase_numeric(base_title, params_dict, primary_item["description"])
            single_size_label = f"{p_w} x {p_l} см"
            unique_sizes = set(parse_pillowcase_numeric(it["title"], it["params"], it["description"])[:2] for it in items)
            has_multiple = len(unique_sizes) > 1
        elif subtype in ["Покрывала", "Пледы", "Наматрасники", "Подушки"]:
            unique_dims = set(it["direct_dims"] for it in items if it["direct_dims"])
            has_multiple = len(unique_dims) > 1
            single_size_label = primary_item["direct_dims"]
        else:
            has_multiple = len(items) > 1
            single_size_label = ""

        # Собираем фото поставщика
        all_images = []
        seen_imgs = set()
        for it in items:
            for img in it["pictures"]:
                if img not in seen_imgs:
                    seen_imgs.add(img)
                    all_images.append(img)

        # Замещение первой фотографии обложкой с инфографикой
        safe_art = re.sub(r'[\\/*?:"<>| ]', '_', base_code)
        custom_cover_url = f"{GITHUB_COVERS_BASE}/{safe_art}.jpg"

        final_gallery = [custom_cover_url]
        other_photos = all_images[1:] if len(all_images) > 1 else []

        for img in other_photos:
            if img != custom_cover_url and img not in final_gallery:
                final_gallery.append(img)

        material = extract_textile_material(base_title, params_dict)
        final_avito_title = generate_group_title(
            base_title, subtype, material, 
            size_label=single_size_label, 
            has_multiple_sizes=has_multiple
        )

        if subtype == "Наматрасники":
            if has_multiple:
                sorted_items = sorted(items, key=lambda x: x["price"])
                p_lines = []
                for it in sorted_items:
                    dim_str = f" ({it['direct_dims']})" if it['direct_dims'] else ""
                    p_lines.append(f"<li>🔹 <b>Размер{dim_str}:</b> <b>{it['price']} ₽</b></li>")
                variants_block_html = f"""<p><b>📐 Доступные размеры в наличии:</b></p>
<ul>
{''.join(p_lines)}
</ul>"""
            else:
                single_dim = primary_item["direct_dims"]
                variants_block_html = f"<p><b>📐 Размер в наличии:</b> {single_dim} — <b>{min_price} ₽</b></p>"

        elif subtype == "Комплект постельного белья":
            size_order = {"1.5-спальный": 1, "2-спальный": 2, "Евро": 3, "Семейный": 4}
            sorted_items = sorted(items, key=lambda x: (size_order.get(x["size"], 99), x["price"]))
            
            variants_lines = []
            seen_variant = set()
            for it in sorted_items:
                var_key = f"{it['size']}_{it['pillow_details']}_{it['price']}"
                if var_key not in seen_variant:
                    seen_variant.add(var_key)
                    variants_lines.append(
                        f"<li>🔹 <b>{it['size']}</b> (наволочки {it['pillow_details']}): пододеяльник {it['duvet_details']}, простыня {it['sheet_details']} — <b>{it['price']} ₽</b></li>"
                    )
            variants_block_html = f"""<p><b>📐 В наличии размеры и комплектация этой модели:</b></p>
<ul>
{''.join(variants_lines)}
</ul>"""
        elif subtype in ["Покрывала", "Пледы", "Подушки"]:
            if has_multiple:
                sorted_items = sorted(items, key=lambda x: x["price"])
                p_lines = []
                for it in sorted_items:
                    dim_str = f" ({it['direct_dims']})" if it['direct_dims'] else ""
                    p_lines.append(f"<li>🔹 <b>Размер{dim_str}:</b> <b>{it['price']} ₽</b></li>")
                variants_block_html = f"""<p><b>📐 Доступные размеры в наличии:</b></p>
<ul>
{''.join(p_lines)}
</ul>"""
            else:
                single_dim = primary_item["direct_dims"]
                variants_block_html = f"<p><b>📐 Размер в наличии:</b> {single_dim} — <b>{min_price} ₽</b></p>"
        else:
            variants_block_html = f"<p><b>📐 Цена:</b> <b>{min_price} ₽</b></p>"

        supplier_desc_block = format_supplier_description_block(primary_item["description"])

        raw_description_body = f"""<p><b>{final_avito_title}</b></p>
<p><b>🇷🇺 Собственное фабричное производство «СИТРЕЙД» в России</b> — предприятие успешно работает на российском текстильном рынке с 2008 года, изготавливая сертифицированную продукцию наивысшего качества для покупателей по всей России, а также экспортируя текстиль в Беларусь и Казахстан. Фабрика следит за современными тенденциями уюта и дизайна, применять премиальные гипоаллергенные ткани стойкого крашения и обеспечивает строгий контроль фабричного пошива.</p>
{supplier_desc_block}
{variants_block_html}
<p><b>🌟 ПОЧЕМУ ВЫБИРАЮТ ИМЕННО НАС (Наши преимущества):</b></p>
<ul><li>🛡️ <b>Сертифицированная продукция:</b> Товар имеет официальные сертификаты качества, декларации соответствия и обязательную маркировку «Честный Знак».</li><li>🎬 <b>Детальные видеообзоры:</b> Для большинства комплектов у нас есть подробные видеообзоры — напишите нам в чат, и мы с удовольствием пришлем ссылку на видео!</li><li>✅ <b>Гарантия соответствия фото 100%:</b> Вы получите именно тот рисунок и расцветку, которую заказывали.</li><li>🔒 <b>Безопасная сделка Авито:</b> Оплата резервируется сайтом Авито и переводится продавцу только после того, как вы проверите и заберете товар в пункте выдачи.</li><li>⚡ <b>Быстрая отправка за 24 часа:</b> Заказ передается в доставку со склада в день заказа или на следующий рабочий день.</li><li>📏 <b>Помощь с выбором:</b> Не знаете, какую простынь или размер выбрать? Напишите в чат — подскажем за 2 минуты!</li><li>🎁 <b>Презентабельный вид:</b> Фирменная упаковка — отлично подходит как для себя, так и на подарок.</li><li>🚚 <b>Надежная Авито Доставка:</b> Отправка через СДЭК и Почту России по всей стране.</li></ul>
<p>🛍️ <b>Переходите в наш профиль</b> — там представлен весь каталог домашнего текстиля: постельное белье, простыни на резинке, пледы, покрывала, наволочки и наматрасники. Подписывайтесь на профиль, чтобы первыми узнавать о новинках и скидках!</p>
<p>💬 <b>Напишите нам в чат</b> — поможем с выбором, забронируем нужный размер и оперативно отправим через безопасную сделку Авито!</p>
<p>📌 Артикул модели: {base_code}</p>"""

        description_body = re.sub(r'>\s+<', '><', raw_description_body.strip())

        ad_node = ET.SubElement(ads_node, "Ad")
        
        ET.SubElement(ad_node, "Id").text = final_ad_id
        ET.SubElement(ad_node, "Category").text = "Мебель и интерьер"
        ET.SubElement(ad_node, "GoodsType").text = "Текстиль и ковры"
        
        if subtype in ["Покрывала", "Пледы"]:
            ET.SubElement(ad_node, "GoodsSubType").text = "Пледы и покрывала"
            ET.SubElement(ad_node, "SubType").text = subtype
            main_comp = extract_main_composition(base_title, params_dict)
            ET.SubElement(ad_node, "MainCompositionComponent").text = main_comp
            purpose_elem = ET.SubElement(ad_node, "Purpose")
            ET.SubElement(purpose_elem, "Option").text = "Кровать"
            ET.SubElement(purpose_elem, "Option").text = "Диван"
            
        elif subtype == "Подушки":
            ET.SubElement(ad_node, "GoodsSubType").text = "Одеяла и подушки"
            ET.SubElement(ad_node, "Type").text = "Подушки"

        elif subtype == "Наматрасники":
            ET.SubElement(ad_node, "GoodsSubType").text = "Постельное белье и наматрасники"
            ET.SubElement(ad_node, "BeddingType").text = "Наматрасники"
            ET.SubElement(ad_node, "SubType").text = "Наматрасники"

        elif subtype == "Простыни":
            ET.SubElement(ad_node, "GoodsSubType").text = "Постельное белье и наматрасники"
            ET.SubElement(ad_node, "BeddingType").text = "Постельное белье"
            ET.SubElement(ad_node, "SubType").text = "Простыни"
            ET.SubElement(ad_node, "TextileMaterial").text = material
            
            s_w, s_l, s_type = parse_bedsheet_numeric(base_title, params_dict, primary_item["description"])
            ET.SubElement(ad_node, "BedsheetWidth").text = s_w
            ET.SubElement(ad_node, "BedsheetLength").text = s_l
            ET.SubElement(ad_node, "BedsheetType").text = s_type
            
        elif subtype == "Наволочки":
            ET.SubElement(ad_node, "GoodsSubType").text = "Постельное белье и наматрасники"
            ET.SubElement(ad_node, "BeddingType").text = "Постельное белье"
            ET.SubElement(ad_node, "SubType").text = "Наволочки"
            ET.SubElement(ad_node, "TextileMaterial").text = material
            
            p_w, p_l, p_cnt = parse_pillowcase_numeric(base_title, params_dict, primary_item["description"])
            ET.SubElement(ad_node, "PillowcaseSize").text = f"{p_w} x {p_l}"
            ET.SubElement(ad_node, "PillowcaseCount").text = p_cnt
            
        elif subtype == "Пододеяльники":
            ET.SubElement(ad_node, "GoodsSubType").text = "Постельное белье и наматрасники"
            ET.SubElement(ad_node, "BeddingType").text = "Постельное белье"
            ET.SubElement(ad_node, "SubType").text = "Пододеяльники"
            ET.SubElement(ad_node, "TextileMaterial").text = material
            
            d_w, d_l = parse_duvet_numeric(base_title, params_dict, primary_item["description"])
            ET.SubElement(ad_node, "DuvetCoverWidth").text = d_w
            ET.SubElement(ad_node, "DuvetCoverLength").text = d_l
            
        else:
            ET.SubElement(ad_node, "GoodsSubType").text = "Постельное белье и наматрасники"
            ET.SubElement(ad_node, "BeddingType").text = "Постельное белье"
            ET.SubElement(ad_node, "SubType").text = "Комплект постельного белья"
            ET.SubElement(ad_node, "BedLinenSize").text = normalize_avito_bed_linen_size(primary_item["size"])
            ET.SubElement(ad_node, "TextileMaterial").text = material
        
        ET.SubElement(ad_node, "Brand").text = STATIC_BRAND
        ET.SubElement(ad_node, "AdType").text = "Товар куплен на продажу"
        ET.SubElement(ad_node, "Condition").text = "Новое"
        ET.SubElement(ad_node, "Availability").text = "В наличии"
        ET.SubElement(ad_node, "Title").text = final_avito_title
        
        desc_element = ET.SubElement(ad_node, "Description")
        desc_element.text = f"__DESCRIPTION_PLACEHOLDER_{processed_count}__"
        
        ET.SubElement(ad_node, "Price").text = str(min_price)
        ET.SubElement(ad_node, "Address").text = AVITO_ADDRESS
        
        # Ищем видеофайлы Яндекс Диска в товарах группы
        group_video_url = ""
        for it in items:
            if it.get("feed_video"):
                group_video_url = it["feed_video"]
                break
        
        if group_video_url:
            video_element = ET.SubElement(ad_node, "VideoFileURL")
            video_element.text = f"__VIDEO_PLACEHOLDER_{processed_count}__"
            video_storage[processed_count] = group_video_url
            
            attached_videos_log.append({
                "id": final_ad_id,
                "code": base_code,
                "title": final_avito_title,
                "url": group_video_url
            })
        
        # Запись картинок: кастомная обложка первая, затем ракурсы
        if final_gallery:
            images_node = ET.SubElement(ad_node, "Images")
            for img_url in final_gallery[:10]:
                ET.SubElement(images_node, "Image", url=img_url)

        desc_storage[processed_count] = description_body
        processed_count += 1

    # Сохраняем обновленную карту ID для памяти в GitHub
    save_id_map(ID_MAP_FILE, id_map)

    raw_xml_string = ET.tostring(ads_node, encoding='utf-8').decode('utf-8')
    reparsed = minidom.parseString(raw_xml_string.encode('utf-8'))
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

    for idx, desc_content in desc_storage.items():
        placeholder = f"__DESCRIPTION_PLACEHOLDER_{idx}__"
        cdata_block = f"<![CDATA[{desc_content}]]>"
        pretty_xml = pretty_xml.replace(placeholder, cdata_block)

    for idx, video_url in video_storage.items():
        placeholder = f"__VIDEO_PLACEHOLDER_{idx}__"
        cdata_video = f"<![CDATA[{video_url}]]>"
        pretty_xml = pretty_xml.replace(placeholder, cdata_video)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    print("\n" + "=" * 60)
    print(f"🎉 ИТОГ: Сгенерировано объявлений: {processed_count}")
    print(f"📄 Файл сохранен в: {output_path}")
    print("=" * 60)
    
    if attached_videos_log:
        print(f"\n🎬 СПИСОК ПРИКРЕПЛЕННЫХ ВИДЕОФАЙЛОВ ({len(attached_videos_log)} шт.):")
        for idx, item in enumerate(attached_videos_log, start=1):
            print(f"{idx}. [{item['id']}] (Код: {item['code']}) — {item['title']}")
            print(f"    🔗 {item['url']}")
    else:
        print("\nℹ️ Подходящих видеофайлов поставщика не обнаружено.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        download_supplier_feed(YML_URL, LOCAL_YML_FILE)
        parse_yml_and_build_avito(LOCAL_YML_FILE, OUTPUT_AVITO_XML)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


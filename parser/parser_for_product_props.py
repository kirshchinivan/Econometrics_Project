import datetime
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import pandas as pd
import re
import time

def collect_product_data(url, city_code='2398'):
    """
    Собирает данные о продукте с указанной страницы магазина.

    Параметры:
        url (str): URL страницы продукта для парсинга
        city_code (str, optional): Гео-идентификатор города. По умолчанию '2398' (Москва).

    Возвращает:
        Tuple[List[bs4.element.Tag], ...]: Кортеж с четырьмя списками элементов:
        - Характеристики продукта
        - Информация о предложениях
        - Пищевая ценность
        - Состав продукта
    """
    ua = UserAgent()

    header = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'User-Agent': ua.random,
    }

    cookie = {
        'mg_geo_id': f'{city_code}',
    }

    response = requests.get(url=url, headers=header, cookies=cookie)
    soup = BeautifulSoup(response.text, 'lxml')
    card1 = soup.find_all('section', class_='product-details-parameters-list')
    card2 = soup.find_all('section', class_='product-details-offer')
    card3 = soup.find_all('section', class_='product-details-nutrition-facts')
    card4 = soup.find_all('section', class_='product-details-parameters-flat')
    return card1, card2, card3, card4

def parse_characteristics(soup):
    """
    Парсит характеристики продукта из HTML-структуры.
    Возвращает Dict[str, Union[str, float]] с характеристиками, где:
            - ключ (str): Название характеристики
            - значение (str | float): Значение характеристики. Числовые значения конвертируются в float.

    """
    characteristics = {}
    
    items = soup.find_all('div', class_='product-details-parameters-list__item')
    
    for item in items:
        try:
            name_span = item.find('span', style=lambda s: s and '--pl-text-secondary' in s)
            if not name_span:
                continue
                
            name = re.sub(r'\s+', ' ', name_span.text).strip()
            name = name.replace(',', '').strip()

            brand = item.find('span', itemprop='brand')
            manufacturer = item.find('span', itemprop='manufacturer')
            weight = item.find('span', itemprop='weight')
            
            if brand:
                value = brand.text.strip()
            elif manufacturer:
                value = manufacturer.text.strip()
            elif weight:
                value = weight.text.strip()
            else:
                meta_value = item.find('meta', {'itemprop': 'value'})
                if meta_value:
                    value = meta_value.get('content', '').strip()
                else:
                    value_span = item.find('span', style=lambda s: s and '--pl-text-primary' in s)
                    value = value_span.text.strip() if value_span else ''

            if any(keyword in name.lower() for keyword in ['вес', 'содержание', 'температура', 'срок']):
                try:
                    value = float(value.replace(',', '.'))
                except (ValueError, AttributeError):
                    pass

            name_mapping = {
                'Вес кг': 'Вес (кг)',
                'Содержание какао %': 'Какао (%)',
                'Тип продукта': 'Тип',
                'Вид шоколада': 'Тип шоколада',
                'Тип упаковки': 'Упаковка'
            }
            name = name_mapping.get(name, name)

            if name and value:
                characteristics[name] = value

        except Exception as e:
            print(f"Ошибка парсинга характеристики: {str(e)}")
            continue

    return characteristics

def parse_offer(section):
    """
    Парсит секцию с информацией о товарном предложении.
    Возвращает Dict[str, Union[float, int, str, None]] с распарсенными данными:
            - Название (str): Полное название товара
            - Текущая цена (float): Актуальная цена в рублях
            - Старая цена (float): Исходная цена (если есть скидка)
            - Скидка (str): Размер скидки в процентах (например, "-15%")
            - Рейтинг (float): Средняя оценка товара от 1 до 5
            - Количество оценок (int): Общее число оценок товара
            - Количество отзывов (int): Количество текстовых отзывов
    """
    offer = {
        'Название': None,
        'Текущая цена': None,
        'Старая цена': None,
        'Скидка': None,
        'Рейтинг': None,
        'Количество оценок': None,
        'Количество отзывов': None
    }
    
    try:
        offer['Название'] = section.find('span', class_='product-details-offer__title').text.strip()
    except AttributeError:
        pass
    
    try:
        price_current = section.find('span', class_='product-details-price__current').text
        offer['Текущая цена'] = float(price_current.replace('₽', '').replace(' ', '').replace('\u202f', ''))
    except (AttributeError, ValueError):
        pass
    
    try:
        price_old = section.find('span', class_='product-details-price__old').text
        offer['Старая цена'] = float(price_old.replace('₽', '').replace(' ', '').replace('\u202f', ''))
    except (AttributeError, ValueError):
        pass
    
    try:
        offer['Скидка'] = section.find('div', class_='pl-label_discount').text.strip()
    except AttributeError:
        pass
    
    try:
        rating_block = section.find('div', class_='product-rating')
        offer['Рейтинг'] = float(rating_block.find('span', class_='product-rating-score').text.strip())
        
        reviews_text = rating_block.find('div', class_='product-rating-count').text
        numbers = [int(n) for n in re.findall(r'\d+', reviews_text)]
        if len(numbers) >= 2:
            offer['Количество оценок'], offer['Количество отзывов'] = numbers[:2]
    except Exception:
        pass
    
    return offer

def parse_nutrition(section):
    """
    Парсит секцию с информацией о пищевой ценности продукта (информация о количестве белков, жиров, углеводов, ккал)
    """
    nutrition = {}
    
    try:
        list_container = section.find('div', class_='product-details-nutrition-facts__list')
        if not list_container:
            return nutrition
            
        items = list_container.find_all('div', class_='product-details-nutrition-facts__list-item')
        
        for item in items:
            try:
                name_tag = item.find('div', class_='product-details-nutrition-facts__list-item__title')
                if not name_tag:
                    continue
                    
                name = name_tag.get_text(strip=True)
                
                value_tag = name_tag.find_next_sibling('div', class_='pl-text')
                if not value_tag:
                    continue
                    
                value = value_tag.get_text(strip=True)
                
                clean_value = ''.join(c for c in value if c.isdigit() or c == '.')
                if clean_value:
                    nutrition[name] = float(clean_value) if '.' in clean_value else int(clean_value)
                    
            except Exception as e:
                print(f"Ошибка парсинга элемента питания: {str(e)}")
                continue
                
    except AttributeError as e:
        print(f"Ошибка структуры секции питания: {str(e)}")
        
    return nutrition

def parse_additional_info(section):
    """
    Парсит секцию с информацией о составе продукта
    """
    result = {'Состав': ''}
    
    try:
        marked_text = section.find('div', class_='marked-text')
        if not marked_text:
            return result
            
        paragraphs = [p.get_text(strip=True) for p in marked_text.find_all('p')]
        if paragraphs:
            result['Состав'] = ' '.join(paragraphs)
            
    except Exception as e:
        print(f"Ошибка парсинга состава: {str(e)}")
        
    return result


def parse_all_sections(sections):
    """Обработка всех секций и объединение данных"""
    parameters_section = sections[0]
    offer_section = sections[1]
    nutrition_section = sections[2]
    additional_sections = sections[3]

    params = parse_characteristics(parameters_section)
    offer = parse_offer(offer_section)
    nutrition = parse_nutrition(nutrition_section)
    additional_info = parse_additional_info(additional_sections)
    
    combined = {}
    combined.update(params)
    combined.update(offer)
    combined.update(nutrition)
    combined.update(additional_info)
    
    return combined

def save_to_html(soup, filename):
    """
    Вспомогательная функция для сохранения собранного html-кода
    """
    with open(filename, 'w', encoding='utf-8') as f:
        for element in soup:
            f.write(element.get_text() + "\n\n")


def main(df):
    all_products_data = []
    for index, row in df.iterrows():
        if index%10 == 0:
            time.sleep(3)
        det, inf, nutr, sostav = collect_product_data(row['link'])

        has_all_sections = all([
            len(det) > 0, 
            len(inf) > 0, 
            len(nutr) > 0,
            len(sostav) > 0
        ])
        
        product_data = (
            parse_all_sections([det[0], inf[0], nutr[0], sostav[0]]) 
            if has_all_sections 
            else {}
        )

        product_data['Ссылка'] = row['link']
        product_data['Артикул'] = row.get('product_id', '') 

        all_products_data.append(product_data)
        print(f'добавлен товар {index}')


    final_df = pd.DataFrame(all_products_data)
        
    final_df.columns = final_df.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
        
    column_order = [
            'Название', 'Ссылка', 'Артикул', 'Текущая цена', 'Старая цена', 'Скидка',
            'Тип продукта', 'Бренд', 'Производитель', 'Вес кг', 'Тип упаковки',
            'Вид шоколада', 'Содержание какао %', 'Вкусовая добавка',
            'Рейтинг', 'Количество оценок', 'Количество отзывов',
            'Ккал', 'Белки', 'Жиры', 'Углеводы']

    existing_columns = [col for col in column_order if col in final_df.columns]
    final_df = final_df[existing_columns + 
                        [col for col in final_df.columns if col not in column_order]]


    output_filename = f'final_products_{datetime.datetime.now().strftime("%d_%m_%Y_%H_%M")}.csv'
    final_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        
    print(f"\nИтоговые данные сохранены в файл: {output_filename}")
    print(f"Обработано товаров: {len(final_df)} из {len(df)}")


df = pd.read_csv('04_05_2025_02_16_all.csv')
main()
import datetime
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from urllib.parse import urljoin
import pandas as pd
import re

BASE_URL = 'https://magnit.ru' 


def collect_data(page_num, city_code='2398'):
    """
    Собирает данные о шоколадках из каталога магазина Магнит по заданной странице поиска.

    Параметры:
        page_num (int): Номер страницы для пагинации поисковой выдачи
        city_code (str, optional): Гео-идентификатор города. По умолчанию '2398' (Москва).

    Возвращает:
        pd.DataFrame: DataFrame с данными о продуктах, где каждая строка - отдельный товар.
        Столбцы зависят от реализации функции extract_product_data.

    """
    url = f'https://magnit.ru/search?term=шоколад&page={page_num}'
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
    cards = soup.find_all('article', class_='unit-catalog-product-preview')
    data = []
    for card in cards:
        product_data = extract_product_data(card)
        data.append(product_data)

    return pd.DataFrame(data)

def extract_product_data(card):
    """Извлекает данные из карточки товара"""
    product = {
        'title': '',
        'link': '',
        'description': '',
        'regular_price': '',
        'sale_price': '',
        'discount': '',
        'sale_period': '',
        'favorite': '',
        'labels': '',
        'badges': ''
    }

    try:
        link_tag = card.find('a', class_='pl-hover-base')
        product['link'] = urljoin(BASE_URL, link_tag['href'])
        product['title'] = link_tag.get('title', '')
    except (AttributeError, TypeError):
        pass

    try:
        product['description'] = card.find('div', class_='unit-catalog-product-preview-description').text.strip()
    except AttributeError:
        pass

    try:
        prices = card.find('div', class_='unit-catalog-product-preview-prices')
        product['regular_price'] = prices.find('div', class_='unit-catalog-product-preview-prices__regular').text.strip()
        product['sale_price'] = prices.find('div', class_='unit-catalog-product-preview-prices__sale').text.strip()
        
        if product['regular_price'] and product['sale_price']:
            old_price = clean_price(product['regular_price'])
            new_price = clean_price(product['sale_price'])
            if old_price and new_price:
                product['discount'] = round((1 - new_price/old_price)*100)
    except (AttributeError, ValueError):
        pass

    try:
        product['favorite'] = card.find('div', class_='unit-catalog-product-preview-favorite').text.strip()
    except AttributeError:
        pass

    try:
        labels = card.find('div', class_='unit-catalog-product-preview-labels')
        product['labels'] = labels.text.strip()
    except AttributeError:
        pass

    try:
        badges = card.find('div', class_='unit-catalog-product-preview-labels__badges')
        product['badges'] = '; '.join([b.text.strip() for b in badges.find_all('div', class_='unit-catalog-product-preview-labels__badges-item')])
    except AttributeError:
        pass

    return product

def clean_price(price_str):
    """Очищает цену от лишних символов и конвертирует в float"""
    try:
        return float(price_str.replace(' ', '').replace('₽', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return None
    
def extract_product_id(url):
    """Извлекает числовой ID из URL"""
    match = re.search(r'/product/(\d+)-', url)
    return match.group(1) if match else None


def main():
    all_data = pd.DataFrame()
    
    for page in range(1, 10):
        print(f'Обработка страницы {page}...')
        page_data = collect_data(page, city_code='2398')
        all_data = pd.concat([all_data, pd.DataFrame(page_data)], ignore_index=True)
    
    all_data['product_id'] = all_data['link'].apply(extract_product_id)
    all_data.drop_duplicates(subset='product_id')
    cur_time = datetime.datetime.now().strftime('%d_%m_%Y_%H_%M')
    filename = f'{cur_time}_all.csv'
    all_data.to_csv(filename, index=False, encoding='utf-8')
    print(f'Все данные сохранены в файл: {filename}')


main()
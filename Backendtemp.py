import requests
from bs4 import BeautifulSoup
import time
import random
import json
import re
import logging
from discord_webhook import DiscordWebhook, DiscordEmbed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin, urlparse
from datetime import datetime
import os
import signal
import sys
import csv

# Configure directories and logging for Windows
PROJECT_DIR = r"C:\Users\Roryi\Desktop\Chapter 8\Coding\Price Monitor"
LOG_DIR = os.path.join(PROJECT_DIR, 'logs')
STATE_DIR = os.path.join(PROJECT_DIR, 'state')
CSV_FILE = os.path.join(PROJECT_DIR, 'johnlewisv2.csv')
GLOBAL_STATE_FILE = os.path.join(STATE_DIR, 'global_state.json')
LOG_FILE = os.path.join(LOG_DIR, 'price_monitor.log')
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Discord webhook URL for notifications
WEBHOOK_URL = "https://discord.com/api/webhooks/1369560794769133609/g-XtphNUL0kMICbJj88viJ7t4bUSeJMgRUvOFevKZvBJUcWE-jcLke9epNrzaS0uH2Dl"

# Multiple category URLs with configs
CATEGORY_URLS = {
    "John Lewis Branded": {
        "url": "https://www.johnlewis.com/brand/john-lewis/all-offers/_/N-1z141ilZ1yzvw1q?sortBy=discount",
        "min_discount": 50.0,
        "max_pages": 4,
        "max_products_per_page": 192,
        "state_file": os.path.join(STATE_DIR, 'category_state.json'),
        "log_tag": "John Lewis Branded"
    },
    "Boots": {
        "url": "https://www.johnlewis.com/browse/women/womens-boots/all-offers/_/N-7oo3Z1yzvw1q?sortBy=discount",
        "min_discount": 0.0,
        "max_pages": 3,  # For ~163 products
        "max_products_per_page": 200,
        "state_file": os.path.join(STATE_DIR, 'boots_state.json'),
        "log_tag": "Boots"
    }
}

# Single User-Agent
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"

# Excluded keywords
EXCLUDED_KEYWORDS = [
    "kids", "baby", "bikini", "top", "bra", "hat", "bodysuit", "dress", "pyjama", "boys", "girls", "Knickers", "Blouse", "Cincher", "Children", "Swimsuit", "Skirt", "Briefs"
]

# Session with retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[400, 429, 500, 502, 503, 504, 403, 408])
session.mount("https://", HTTPAdapter(max_retries=retries))

# Counters
cycle_count = 0
ssl_error_count = 0
excluded_keyword_count = 0
NOTIFY_EVERY_CYCLES = 3
MAX_CHUNKS = 8  # Set to 8 as requested
MAX_PAGE_REQUESTS = 50

def get_headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }

def clean_price(text):
    if not text:
        return None
    text = re.split(r'\s*-\s*', text)[0]
    text = re.sub(r'[^\d.]', '', text)
    try:
        return float(text)
    except ValueError:
        return None

def extract_product_id(url):
    match = re.search(r"p(\d+)$", url)
    if match:
        product_id = match.group(1)
        logging.debug(f"Extracted product ID {product_id} from URL: {url}")
        return product_id
    logging.error(f"Failed to extract product ID from URL: {url}")
    print(f"Failed to extract product ID from URL: {url}")
    return None

def normalize_url(url):
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    return f"{parsed.scheme}://{parsed.netloc}{path}"

def normalize_size(size):
    size = size.strip()
    size = re.sub(r'^(uk|eu)(\d+)$', r'\1 \2', size, flags=re.I)
    return size

def fetch_category_page(url, page=1, chunk=1):
    global ssl_error_count
    max_attempts = 3
    page_url = f"{url}&page={page}&chunk={chunk}" if chunk > 1 else f"{url}&page={page}"
    for attempt in range(max_attempts):
        try:
            delay = random.uniform(2, 4)
            print(f"Fetching page {page}, chunk {chunk}, waiting {delay:.2f}s...")
            logging.info(f"Fetching {page_url} (Attempt {attempt+1}/{max_attempts}, waiting {delay:.2f}s)")
            time.sleep(delay)
            response = session.get(page_url, headers=get_headers(), timeout=8)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            product_urls = []
            json_ld_script = soup.find('script', type='application/ld+json')
            if json_ld_script:
                try:
                    json_data = json.loads(json_ld_script.string)
                    if json_data.get('@type') == 'ItemList' and 'itemListElement' in json_data:
                        product_urls = [item['url'] for item in json_data['itemListElement'] if item.get('url') and '/p' in item['url']]
                        product_urls = [urljoin("https://www.johnlewis.com", url) for url in product_urls]
                except json.JSONDecodeError:
                    logging.warning(f"Failed to parse JSON-LD on {page_url}")

            if not product_urls:
                links = soup.select('a.product-card_c-product-card__link___7IQk')
                product_urls = [urljoin("https://www.johnlewis.com", link.get('href')) for link in links if link.get('href')]

            if not product_urls:
                debug_file = os.path.join(LOG_DIR, f"debug_page_{page}_chunk_{chunk}.html")
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(soup.prettify())
                logging.warning(f"No product links found on {page_url}. Saved HTML to {debug_file}")
                print(f"No product links found on {page_url}. Saved HTML to {debug_file}")

            if product_urls:
                print(f"Sample product URLs: {product_urls[:3]}")
            print(f"Found {len(product_urls)} products on page {page}, chunk {chunk}")
            logging.info(f"Found {len(product_urls)} products on page {page}, chunk {chunk} (Response size: {len(response.text)} bytes, Status: {response.status_code})")
            return list(set(product_urls))

        except requests.exceptions.SSLError as ssl_err:
            ssl_error_count += 1
            logging.error(f"SSL error fetching {page_url} (attempt {attempt+1}/{max_attempts}): {ssl_err}")
            print(f"SSL error fetching page {page}, chunk {chunk} (attempt {attempt+1}/{max_attempts}): {ssl_err}")
            if attempt == max_attempts - 1:
                message = f"Failed to fetch {page_url} after {max_attempts} attempts: {ssl_err}"
                logging.error(message)
                print(message)
                send_error_webhook(message)
                return []
            time.sleep(random.uniform(5, 10))
        except Exception as e:
            logging.error(f"Error fetching {page_url} (attempt {attempt+1}/{max_attempts}): {e}")
            print(f"Error fetching page {page}, chunk {chunk} (attempt {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                message = f"Failed to fetch {page_url} after {max_attempts} attempts: {e}"
                logging.error(message)
                print(message)
                send_error_webhook(message)
                return []
            time.sleep(random.uniform(1, 2))

def fetch_category_products(category_name, category_config, global_seen_ids, force_new=False):
    all_product_urls = []
    request_count = 0
    max_pages = category_config["max_pages"]
    max_products_per_page = category_config["max_products_per_page"]

    for page in range(1, max_pages + 1):
        page_urls = []
        chunk = 1
        previous_chunk_urls = set()
        total_products = 0
        while chunk <= MAX_CHUNKS:
            if request_count >= MAX_PAGE_REQUESTS:
                print(f"Reached max page requests ({MAX_PAGE_REQUESTS}) on page {page}, chunk {chunk} for {category_name}.")
                logging.warning(f"Reached max page requests ({MAX_PAGE_REQUESTS}) on page {page}, chunk {chunk} for {category_name}.")
                break
            product_urls = fetch_category_page(category_config["url"], page, chunk)
            request_count += 1
            if not product_urls or len(product_urls) < 5:
                print(f"Low product count ({len(product_urls)}) in page {page}, chunk {chunk} for {category_name}.")
                logging.info(f"Low product count ({len(product_urls)}) in page {page}, chunk {chunk} for {category_name}.")
                break
            normalized_urls = []
            for url in product_urls:
                normalized_url = normalize_url(url)
                product_id = extract_product_id(normalized_url)
                if product_id and (force_new or product_id not in global_seen_ids):
                    normalized_urls.append(normalized_url)
            current_chunk_urls = set(normalized_urls)
            total_products += len(current_chunk_urls - previous_chunk_urls)
            if current_chunk_urls <= previous_chunk_urls or total_products >= max_products_per_page:
                print(f"Reached {total_products} products in page {page}, chunk {chunk} for {category_name}. Stopping chunk loop.")
                logging.info(f"Reached {total_products} products in page {page}, chunk {chunk} for {category_name}. Stopping chunk loop.")
                break
            page_urls.extend(normalized_urls)
            previous_chunk_urls.update(current_chunk_urls)
            chunk += 1

        page_urls = list(set(page_urls))
        print(f"Total unique products on page {page} ({category_name}): {len(page_urls)}")
        logging.info(f"Total unique products on page {page} ({category_name}): {len(page_urls)}")
        all_product_urls.extend(page_urls)

    all_product_urls = list(set(all_product_urls))
    print(f"Total unique products fetched for {category_name}: {len(all_product_urls)}, {request_count} requests made")
    logging.info(f"Total unique products fetched for {category_name}: {len(all_product_urls)}, {request_count} requests made")
    return all_product_urls

def fetch_product_info(url, counter, total, category_name, global_seen_ids):
    global ssl_error_count, excluded_keyword_count
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            delay = random.uniform(2, 4)
            print(f"Fetching product {counter}/{total} ({category_name}): {url}, waiting {delay:.2f}s...")
            logging.info(f"Fetching product {counter}/{total} ({category_name}): {url} (Attempt {attempt+1}/{max_attempts}, waiting {delay:.2f}s)")
            time.sleep(delay)
            response = session.get(url, headers=get_headers(), timeout=8)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            data_script = soup.find('script', type='application/ld+json')
            if not data_script:
                logging.warning(f"Scraping {url} ({category_name}): No JSON-LD found, attempting fallback")
                print(f"Scraping {counter}/{total} ({category_name}) - {url}: No JSON-LD found, attempting fallback")

                name = soup.select_one("h1.product-header__name")
                name = name.get_text(strip=True) if name else "Unknown Product"

                current_price = soup.select_one(".prod-price__current") or \
                               soup.select_one("span[data-testid='price-current']") or \
                               soup.find("span", class_=re.compile(r"price", re.I))
                current_price = clean_price(current_price.get_text(strip=True)) if current_price else None

                original_price = soup.select_one(".prod-price__was") or \
                                soup.find("span", attrs={"data-testid": "price-prev"})
                original_price = clean_price(original_price.get_text(strip=True)) if original_price else None

                stock_status = soup.select_one(".stock-availability-message") or soup.select_one(".prod-header__availability")
                stock_status = stock_status.get_text(strip=True) if stock_status else "Not listed"

                sizes = soup.select(".prod-size__option")
                sizes = [normalize_size(size.get_text(strip=True)) for size in sizes] if sizes else ["One Size"]
                logging.info(f"Normalized sizes for {name} ({category_name}): {sizes}")

                image = soup.select_one("img.product-image")
                image_url = image.get("src") if image else None
            else:
                try:
                    json_data = json.loads(data_script.string)
                except json.JSONDecodeError as e:
                    logging.error(f"Skipping {url} ({category_name}): JSON decode error: {e}")
                    print(f"Skipping {counter}/{total} ({category_name}) - {url}: JSON decode error")
                    return None

                name = json_data.get("name") or "Unknown"
                image_url = json_data.get("image")

                current_price = json_data.get("offers", {}).get("price")
                current_price = float(current_price) if current_price and current_price.replace(".", "").isdigit() else None
                if current_price is None:
                    current_price_elem = soup.select_one(".prod-price__current") or \
                                        soup.select_one("span[data-testid='price-current']") or \
                                        soup.find("span", class_=re.compile(r"price", re.I))
                    current_price = clean_price(current_price_elem.get_text(strip=True)) if current_price_elem else None

                original_price = None
                price_prev = soup.find("span", attrs={"data-testid": "price-prev"})
                if price_prev:
                    original_price = clean_price(price_prev.get_text(strip=True))
                    logging.info(f"Found original price for {name} ({category_name}): £{original_price}")
                else:
                    price_was = soup.find(lambda tag: tag.name in ['span', 'div', 's'] and (
                        re.search(r'was\s*£?\d', tag.get_text(strip=True), re.I) or
                        'price--was' in tag.get('class', []) or
                        'price--original' in tag.get('class', []) or
                        tag.name == 's'
                    ))
                    if price_was:
                        original_price = clean_price(price_was.get_text(strip=True))
                        logging.info(f"Found original price (fallback) for {name} ({category_name}): £{original_price}")

                availability = json_data.get("offers", {}).get("availability")
                stock_status = "In Stock" if availability and "InStock" in availability else "Out of Stock"

                sizes = []
                size_elements = soup.find_all("a", attrs={"data-testid": "size:option:button"}) or \
                               soup.find_all("span", class_=re.compile(r"size", re.I))
                for size in size_elements:
                    label = size.get_text(strip=True)
                    if label:
                        sizes.append(normalize_size(label))
                if not sizes:
                    sizes = ["One Size"]
                logging.info(f"Normalized sizes for {name} ({category_name}): {sizes}")

            product_id = extract_product_id(url)
            if not product_id:
                logging.warning(f"Skipping {url} ({category_name}): Could not extract product ID")
                print(f"Skipping {counter}/{total} ({category_name}) - {url}: Could not extract product ID")
                return None

            name_lower = name.lower()
            has_excluded_keyword = any(keyword.lower() in name_lower for keyword in EXCLUDED_KEYWORDS)
            if has_excluded_keyword:
                excluded_keyword_count += 1
                logging.warning(f"Skipping {name} ({category_name}): Contains excluded keyword")
                print(f"Skipping {counter}/{total} ({category_name}) - {name}: Contains excluded keyword")
                return None

            discount = 0.0
            if original_price is not None and current_price is not None and original_price > current_price > 0:
                discount = ((original_price - current_price) / original_price) * 100

            variants = []
            variant_elements = soup.find_all("a", attrs={"data-testid": re.compile(r"colour:option", re.I)}) or \
                              soup.find_all("span", class_=re.compile(r"colour", re.I))
            for variant in variant_elements:
                variant_name = variant.get_text(strip=True)
                if variant_name:
                    variants.append(variant_name)
            if variants:
                logging.info(f"Variants for {name} ({category_name}): {', '.join(variants)}")

            category_min_discount = CATEGORY_URLS[category_name]["min_discount"]
            if discount < category_min_discount:
                logging.warning(f"Skipping {name} ({category_name}): Discount {discount:.2f}% < {category_min_discount}%")
                print(f"Skipping {counter}/{total} ({category_name}) - {name}: Discount {discount:.2f}% < {category_min_discount}%")
                return None

            product = {
                "product_id": product_id,
                "name": name,
                "url": url,
                "current_price": current_price,
                "original_price": original_price,
                "discount": discount,
                "stock_status": stock_status,
                "image": image_url or "",
                "sizes": sizes,
                "variants": variants,
                "category": category_name
            }
            price_status = f"Current: {current_price if current_price is not None else 'None'}, Original: {original_price if original_price is not None else 'None'}, Discount: {discount:.2f}%"
            print(f"Fetched product {counter}/{total} ({category_name}): {name}, {price_status}")
            logging.info(f"Fetched product {counter}/{total} ({category_name}): {name}, {price_status}")
            return product

        except requests.exceptions.SSLError as ssl_err:
            ssl_error_count += 1
            logging.error(f"SSL error fetching {url} ({category_name}) (attempt {attempt+1}/{max_attempts}): {ssl_err}")
            print(f"SSL error fetching {counter}/{total} ({category_name}) - {url} (attempt {attempt+1}/{max_attempts}): {ssl_err}")
            if attempt == max_attempts - 1:
                message = f"Failed to fetch product {url} ({category_name}) after {max_attempts} attempts: {ssl_err}"
                logging.error(message)
                print(message)
                send_error_webhook(message)
                return None
            time.sleep(random.uniform(5, 10))
        except Exception as e:
            logging.error(f"Error fetching {url} ({category_name}) (attempt {attempt+1}/{max_attempts}): {e}")
            print(f"Error fetching {counter}/{total} ({category_name}) - {url} (attempt {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                message = f"Failed to fetch product {url} ({category_name}) after {max_attempts} attempts: {e}"
                logging.error(message)
                print(message)
                send_error_webhook(message)
                return None

def load_global_state():
    try:
        if os.path.exists(GLOBAL_STATE_FILE):
            with open(GLOBAL_STATE_FILE, "r") as f:
                state = json.load(f)
                seen_ids = set(state.get("seen_product_ids", []))
                logging.info(f"Loaded global state with {len(seen_ids)} seen product IDs")
                print(f"Loaded global state with {len(seen_ids)} seen product IDs")
                return seen_ids
        else:
            logging.warning("No global state file found. Starting fresh.")
            print("No global state file found. Starting fresh.")
            return set()
    except (json.JSONDecodeError, Exception) as e:
        logging.error(f"Error loading global state: {e}")
        print(f"Error loading global state: {e}")
        return set()

def save_global_state(seen_product_ids):
    try:
        state = {"seen_product_ids": list(seen_product_ids)}
        with open(GLOBAL_STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
        logging.info(f"Saved global state with {len(seen_product_ids)} seen product IDs")
        print(f"Saved global state with {len(seen_product_ids)} seen product IDs")
    except Exception as e:
        logging.error(f"Failed to save global state: {e}")
        print(f"Failed to save global state: {e}")

def load_previous_state(state_file):
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
            cleaned_state = {}
            for product_id, data in state.items():
                try:
                    original_price = float(data.get("original_price")) if data.get("original_price") is not None else None
                    latest_price = float(data.get("latest_price")) if data.get("latest_price") is not None else None
                    stock_status = data.get("stock_status", "Unknown")
                    url = data.get("url", "Unknown")
                    if not product_id or not url:
                        logging.error(f"Invalid state entry: Missing product_id or URL in {state_file}")
                        continue
                    cleaned_state[product_id] = {
                        "name": data.get("name"),
                        "url": url,
                        "original_price": original_price,
                        "latest_price": latest_price,
                        "stock_status": stock_status
                    }
                except (ValueError, TypeError) as e:
                    logging.error(f"Skipping invalid state entry for product ID {product_id} in {state_file}: {e}")
                    print(f"Skipping invalid state entry for product ID {product_id}")
            logging.info(f"Loaded category state from {state_file} with {len(cleaned_state)} items")
            print(f"Loaded category state from {state_file} with {len(cleaned_state)} items")
            return cleaned_state
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"No state file or error in {state_file}: {e}. Starting fresh.")
        print(f"No state file or error in {state_file}: {e}. Starting fresh.")
        return {}

def save_state(products, current_product_ids, state_file):
    new_state = {}
    for product in products:
        product_id = product["product_id"]
        if not product_id:
            logging.error(f"Skipping save for product {product['name']}: No product_id")
            print(f"Skipping save for product {product['name']}: No product_id")
            continue
        name_lower = product["name"].lower()
        has_excluded_keyword = any(keyword.lower() in name_lower for keyword in EXCLUDED_KEYWORDS)
        if has_excluded_keyword:
            logging.warning(f"Skipping save for product ID {product_id}: Contains excluded keyword")
            continue
        new_state[product_id] = {
            "name": product["name"],
            "url": product["url"],
            "original_price": product["original_price"],
            "latest_price": product["current_price"],
            "stock_status": product["stock_status"]
        }
        logging.info(f"Saving state for product ID {product_id}: {product['url']}")

    previous_state = load_previous_state(state_file)
    previous_state.update(new_state)

    for product_id in list(previous_state.keys()):
        if product_id in current_product_ids:
            continue
        stock_status = previous_state[product_id].get("stock_status", "Not listed")
        if stock_status == "Out of Stock":
            logging.info(f"Removing product ID {product_id} from state: Out of Stock")
            del previous_state[product_id]

    try:
        with open(state_file, "w") as f:
            json.dump(previous_state, f, indent=4)
        with open(state_file, "r") as f:
            saved_state = json.load(f)
        if len(saved_state) != len(previous_state):
            logging.error(f"State file mismatch in {state_file}: Expected {len(previous_state)} items, found {len(saved_state)}")
            print(f"State file mismatch in {state_file}: Expected {len(previous_state)} items, found {len(saved_state)}")
            send_error_webhook(f"State file mismatch in {state_file}: Expected {len(previous_state)} items, found {len(saved_state)}")
        else:
            logging.info(f"Saved and verified category state in {state_file} with {len(previous_state)} items")
            print(f"Saved and verified category state in {state_file} with {len(previous_state)} items")
    except Exception as e:
        logging.error(f"Failed to save or verify state file {state_file}: {e}")
        print(f"Failed to save or verify state file {state_file}: {e}")
        send_error_webhook(f"Failed to save or verify state file {state_file}: {e}")

def send_error_webhook(message):
    webhook = DiscordWebhook(url=WEBHOOK_URL, content=message)
    for attempt in range(3):
        try:
            delay = random.uniform(1, 1.5)
            logging.info(f"Waiting {delay:.2f}s before sending error webhook (attempt {attempt+1}/3)")
            print(f"Sending error webhook, waiting {delay:.2f}s...")
            time.sleep(delay)
            response = webhook.execute()
            logging.info(f"Sent error webhook: {message} (Status: {response.status_code})")
            print(f"Sent error webhook: {message}")
            return
        except Exception as e:
            logging.error(f"Failed to send error webhook (attempt {attempt+1}/3): {e}")
            print(f"Failed to send error webhook (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2)
    logging.error(f"Failed to send error webhook after 3 attempts")
    print(f"Failed to send error webhook after 3 attempts")

def send_cycle_start_webhook(cycle, category_name):
    message = f"🚀 Monitor started - Cycle {cycle}: Checking {category_name} (>= {CATEGORY_URLS[category_name]['min_discount']}% off, no excluded keywords)"
    webhook = DiscordWebhook(url=WEBHOOK_URL, content=message)
    for attempt in range(3):
        try:
            delay = random.uniform(1, 1.5)
            logging.info(f"Waiting {delay:.2f}s before sending cycle start webhook for {category_name} (attempt {attempt+1}/3)")
            print(f"Sending cycle start webhook for {category_name}, Cycle {cycle}, waiting {delay:.2f}s...")
            time.sleep(delay)
            response = webhook.execute()
            logging.info(f"Sent cycle start webhook for {category_name}: Cycle {cycle} (Status: {response.status_code})")
            print(f"Sent cycle start webhook for {category_name}: Cycle {cycle}")
            return
        except Exception as e:
            logging.error(f"Failed to send cycle start webhook for {category_name} (attempt {attempt+1}/3): {e}")
            print(f"Failed to send cycle start webhook for {category_name} (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2)
    logging.error(f"Failed to send cycle start webhook for {category_name} after 3 attempts")
    print(f"Failed to send cycle start webhook for {category_name} after 3 attempts")

def send_periodic_webhook(cycle, category_name, num_products, changes_detected):
    status = "No changes detected" if changes_detected == 0 else f"Detected {changes_detected} changes"
    message = f"✅ Monitor completed - Cycle {cycle}: Checked {num_products} products in {category_name} (>= {CATEGORY_URLS[category_name]['min_discount']}% off, no excluded keywords). {status}"
    webhook = DiscordWebhook(url=WEBHOOK_URL, content=message)
    for attempt in range(3):
        try:
            delay = random.uniform(1, 1.5)
            logging.info(f"Waiting {delay:.2f}s before sending periodic webhook for {category_name} (attempt {attempt+1}/3)")
            print(f"Sending periodic webhook for {category_name}, Cycle {cycle}, waiting {delay:.2f}s...")
            time.sleep(delay)
            response = webhook.execute()
            logging.info(f"Sent periodic webhook for {category_name}: Cycle {cycle} (Status: {response.status_code})")
            print(f"Sent periodic webhook for {category_name}: Cycle {cycle}")
            return
        except Exception as e:
            logging.error(f"Failed to send periodic webhook for {category_name} (attempt {attempt+1}/3): {e}")
            print(f"Failed to send periodic webhook for {category_name} (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2)
    logging.error(f"Failed to send periodic webhook for {category_name} after 3 attempts")
    print(f"Failed to send periodic webhook for {category_name} after 3 attempts")

def is_duplicate_in_csv(product_name, product_url, product_id, check_last_n=100):
    if not os.path.exists(CSV_FILE):
        return False
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)[-check_last_n:]
            for row in rows:
                if row.get('Product Name') == product_name and row.get('URL') == product_url and row.get('Product ID') == product_id:
                    logging.info(f"Skipping CSV append for duplicate: {product_name} (ID: {product_id})")
                    return True
        return False
    except Exception as e:
        logging.error(f"Error checking CSV for duplicates: {e}")
        return False

def send_item_webhook(product, event_type, previous_state, price_diff=None, direction=None):
    discount = product["discount"]
    category = product["category"]
    product_id = product["product_id"]
    logging.info(f"Sending webhook for {product['name']} ({category}): Event={event_type}, Discount={discount:.2f}%")
    print(f"Sending webhook for {product['name']} ({category}): {event_type}")
   
    if is_duplicate_in_csv(product['name'], product['url'], product_id):
        logging.info(f"Skipping webhook and CSV for duplicate product: {product['name']} (ID: {product_id})")
        return
   
    webhook = DiscordWebhook(url=WEBHOOK_URL)
    embed = DiscordEmbed(
        title=product["name"][:256],
        url=product["url"],
        color=0x00ff00 if product["stock_status"] == "In Stock" else 0xff0000
    )
   
    if product.get("image"):
        embed.set_thumbnail(url=product["image"])
   
    current_price = product["current_price"]
    embed.add_embed_field(name="Current Price", value=f"£{current_price:.2f}" if current_price is not None else "No price found", inline=True)
   
    if event_type == "price_change":
        previous_price = previous_state[product["product_id"]]["latest_price"]
        embed.add_embed_field(name="Previous Price", value=f"£{previous_price:.2f}" if previous_price is not None else "No price found", inline=True)
        embed.add_embed_field(name="Price Change", value=f"{direction.capitalize()} by £{abs(price_diff):.2f}" if price_diff is not None else "N/A", inline=True)
    else:
        embed.add_embed_field(name="Previous Price", value="N/A (New Product)", inline=True)
        embed.add_embed_field(name="Price Change", value="N/A (New Product)", inline=True)
   
    original_price = product["original_price"]
    embed.add_embed_field(name="Original Price", value=f"£{original_price:.2f}" if original_price is not None else "No price found", inline=True)
    embed.add_embed_field(name="Discount", value=f"{discount:.2f}%" if discount >= 0 else "N/A", inline=True)
    embed.add_embed_field(name="Stock Status", value=product["stock_status"], inline=True)
    embed.add_embed_field(name="Category", value=category, inline=True)
   
    sizes_value = ", ".join(product["sizes"]) if product["sizes"] else "One Size"
    embed.add_embed_field(name="Sizes", value=sizes_value[:1024], inline=False)
    variants_value = ", ".join(product["variants"]) if product.get("variants") else "None"
    embed.add_embed_field(name="Variants", value=variants_value[:1024], inline=False)
    embed.add_embed_field(name="Link", value=f"[View Product]({product['url']})", inline=False)
   
    footer_text = f"By Alternative Assets | Event: {'New Product' if event_type == 'new' else f'Price {direction.capitalize()}'} | Category: {category}"
    embed.set_footer(text=footer_text[:2048])
   
    webhook.add_embed(embed)
    for attempt in range(3):
        try:
            delay = random.uniform(1, 1.5)
            logging.info(f"Waiting {delay:.2f}s before sending item webhook for {product['name']} ({category}) (attempt {attempt+1}/3)")
            time.sleep(delay)
            response = webhook.execute()
            logging.info(f"Sent webhook for {product['name']} ({category}) ({event_type}) (Status: {response.status_code})")
            print(f"Sent webhook for {product['name']} ({category}) ({event_type})")
            row_data = {
                'Product ID': product_id,
                'Product Name': product['name'],
                'Current Price': f"{product['current_price']:.2f}" if product['current_price'] is not None else "N/A",
                'Original Price': f"{product['original_price']:.2f}" if product['original_price'] is not None else "N/A",
                'Discount': f"{product['discount']:.2f}" if product['discount'] >= 0 else "N/A",
                'Stock Status': product['stock_status'],
                'Sizes': sizes_value,
                'URL': product['url'],
                'Event Type': event_type.capitalize(),
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Image': product['image'] if product['image'] else "",
                'Category': category,
                'Variants': variants_value
            }
            file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
            with open(CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=row_data.keys(), quoting=csv.QUOTE_MINIMAL)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row_data)
                csvfile.flush()
            print(f"Appended to CSV: {row_data['Product Name']} ({category}) - ID: {product_id}")
            logging.info(f"Appended to CSV: {row_data['Product Name']} ({category}) - ID: {product_id}")
            return
        except Exception as e:
            logging.error(f"Failed to send webhook for {product['name']} ({category}) (attempt {attempt+1}/3): {e}")
            print(f"Failed to send webhook for {product['name']} ({category}) (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2)
    logging.error(f"Failed to send webhook for {product['name']} ({category}) after 3 attempts")
    print(f"Failed to send webhook for {product['name']} ({category}) after 3 attempts")

def send_webhook(products, previous_state, category_name, global_seen_ids):
    items_to_report = []
    seen_product_ids = set()
    for product in products:
        product_id = product["product_id"]
        if product_id in seen_product_ids:
            logging.warning(f"Skipping duplicate product ID {product_id} in {category_name}: {product['name']}")
            continue
        seen_product_ids.add(product_id)
        
        current_price = product["current_price"]
        stock_status = product["stock_status"]
       
        name_lower = product["name"].lower()
        has_excluded_keyword = any(keyword.lower() in name_lower for keyword in EXCLUDED_KEYWORDS)
        if has_excluded_keyword:
            logging.warning(f"Skipping {product['name']} ({category_name}): Contains excluded keyword")
            print(f"Skipping {product['name']} ({category_name}): Contains excluded keyword")
            continue

        event_type = None
        price_diff = None
        direction = None

        if product_id not in previous_state:
            event_type = "new"
            items_to_report.append((product, event_type, price_diff, direction))
            logging.info(f"New product detected ({category_name}): {product['name']}, Product ID: {product_id}, URL: {product['url']}")
            print(f"New product detected ({category_name}): {product['name']}")
        else:
            old_price = previous_state[product_id]["latest_price"]
            old_stock_status = previous_state[product_id]["stock_status"]
            price_changed = (old_price is not None and current_price is not None and abs(current_price - old_price) > 0.01) or \
                            (old_price is None and current_price is not None) or (old_price is not None and current_price is None)
            stock_changed = stock_status != old_stock_status

            if price_changed:
                event_type = "price_change"
                price_diff = current_price - old_price if current_price is not None and old_price is not None else None
                direction = "increased" if price_diff and price_diff > 0 else "decreased" if price_diff and price_diff < 0 else "changed"
                items_to_report.append((product, event_type, price_diff, direction))
                logging.info(f"Price change detected ({category_name}) for {product['name']}: Price {old_price} -> {current_price}")
                print(f"Price change detected ({category_name}) for {product['name']}: Price {old_price} -> {current_price}")
            elif stock_changed:
                logging.info(f"Stock status change ({category_name}) for {product['name']}: {old_stock_status} -> {stock_status}")
                print(f"Stock status change ({category_name}) for {product['name']}: {old_stock_status} -> {stock_status}")

    items_to_report.sort(key=lambda x: x[0]["discount"] or 0, reverse=True)
    changes_detected = len(items_to_report)
    for product, event_type, price_diff, direction in items_to_report:
        send_item_webhook(product, event_type, previous_state, price_diff, direction)
        global_seen_ids.add(product["product_id"])
        delay = random.uniform(1, 1.5)
        logging.info(f"Waiting {delay:.2f}s before next webhook ({category_name})")
        time.sleep(delay)

    return changes_detected

def signal_handler(sig, frame):
    logging.info("Received shutdown signal. Saving state and exiting...")
    print("Shutting down gracefully...")
    sys.exit(0)

def main():
    global cycle_count, ssl_error_count, excluded_keyword_count
    logging.info("Starting unified John Lewis monitor (v27 full capture)...")
    print("Starting unified John Lewis monitor (v27 full capture)...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
   
    FORCE_NEW = True  # Force all products as "new" for this run; set to False after

    while True:
        try:
            cycle_count += 1
            ssl_error_count = 0
            excluded_keyword_count = 0
            start_time = datetime.now()
            logging.info(f"Cycle {cycle_count} started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Cycle {cycle_count} started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

            global_seen_ids = set() if FORCE_NEW else load_global_state()
           
            total_products_all = 0
            total_changes_all = 0
            filtered_count_all = 0
            request_count_all = 0

            for category_name, category_config in CATEGORY_URLS.items():
                print(f"\n--- Starting {category_name} ---")
                logging.info(f"--- Starting {category_name} ---")

                send_cycle_start_webhook(cycle_count, category_name)

                previous_state = {} if FORCE_NEW else load_previous_state(category_config["state_file"])
                product_urls = fetch_category_products(category_name, category_config, global_seen_ids, FORCE_NEW)
                products = []
                request_count = len(product_urls)
                filtered_count = 0
                current_product_ids = set()

                total_products = len(product_urls)
                for idx, url in enumerate(product_urls, 1):
                    product = fetch_product_info(url, idx, total_products, category_name, global_seen_ids)
                    if product:
                        products.append(product)
                        current_product_ids.add(product["product_id"])
                    else:
                        filtered_count += 1
                    request_count += 1

                changes_detected = 0
                if products:
                    changes_detected = send_webhook(products, previous_state, category_name, global_seen_ids)
                    save_state(products, current_product_ids, category_config["state_file"])
                else:
                    logging.warning(f"No valid products fetched for {category_name}.")
                    print(f"No valid products fetched for {category_name}.")
                    send_error_webhook(f"No valid products found in {category_name}: {category_config['url']}")

                total_products_all += len(products)
                total_changes_all += changes_detected
                filtered_count_all += filtered_count
                request_count_all += request_count

                print(f"{category_name} complete: Checked {len(products)} products, {filtered_count} filtered out, {changes_detected} changes detected")
                logging.info(f"{category_name} complete: Checked {len(products)} products, {filtered_count} filtered out, {changes_detected} changes detected")

                time.sleep(random.uniform(30, 60))

            save_global_state(global_seen_ids)
           
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds() / 60.0
            logging.info(f"Cycle {cycle_count} finished at {end_time.strftime('%Y-%m-%d %H:%M:%S')}, took {duration:.2f} minutes")
            print(f"Cycle {cycle_count} finished at {end_time.strftime('%Y-%m-%d %H:%M:%S')}, took {duration:.2f} minutes")
            logging.info(f"Cycle {cycle_count} complete: Checked {total_products_all} products across categories, {filtered_count_all} filtered out, {excluded_keyword_count} excluded by keywords, {total_changes_all} changes detected, {request_count_all} requests made, {ssl_error_count} SSL errors")
            print(f"Cycle {cycle_count} complete: Checked {total_products_all} products across categories, {filtered_count_all} filtered out, {excluded_keyword_count} excluded by keywords, {total_changes_all} changes detected, {request_count_all} requests made, {ssl_error_count} SSL errors")

            if cycle_count % NOTIFY_EVERY_CYCLES == 0:
                summary_msg = f"✅ Full Cycle {cycle_count} Complete: {total_products_all} products checked, {total_changes_all} changes across all categories."
                webhook = DiscordWebhook(url=WEBHOOK_URL, content=summary_msg)
                webhook.execute()

            if ssl_error_count > 10:
                logging.warning(f"High SSL error count ({ssl_error_count}) in cycle {cycle_count}. Pausing for 30 minutes...")
                print(f"High SSL error count ({ssl_error_count}). Pausing for 30 minutes...")
                send_error_webhook(f"High SSL error count ({ssl_error_count}) in cycle {cycle_count}. Pausing for 30 minutes.")
                time.sleep(1800)
                check_interval = random.uniform(6900, 7500)
            else:
                check_interval = random.uniform(6900, 7500)

            logging.info(f"Next check in {check_interval/60:.2f} minutes...")
            print(f"Next check in {check_interval/60:.2f} minutes...")
            time.sleep(check_interval)
       
        except Exception as e:
            logging.error(f"Script crashed: {e}. Restarting in 60 seconds...")
            print(f"Script crashed: {e}. Restarting in 60 seconds...")
            send_error_webhook(f"Unified monitor crashed: {e}. Restarting...")
            time.sleep(60)

if __name__ == "__main__":
    main()
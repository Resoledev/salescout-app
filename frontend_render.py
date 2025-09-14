import csv
import os
import re
import traceback
import ast
from flask import Flask, render_template_string, request, make_response
from datetime import datetime

app = Flask(__name__)
CSV_FILE = os.environ.get("CSV_FILE", "/opt/render/project/src/johnlewisv2.csv")

def _extract_image_from_row(row):
    """
    Handle cases where CSV has more fields than headers (DictReader will put extras in key `None`),
    or where an 'Image' header already exists. Return a string URL or empty string.
    """
    image_val = row.get("Image")
    if image_val:
        return str(image_val).strip()

    extra = row.get(None)
    if extra:
        if isinstance(extra, list):
            return str(extra[0]).strip() if extra else ""
        return str(extra).strip()
    return ""

def _clean_sizes_field(sizes_value, category):
    """
    Normalize the Sizes field into a comma-separated human-readable list,
    and return the cleaned string, available sizes list, and filterable sizes based on category.
    """
    if not sizes_value:
        return "N/A", [], []

    cleaned = sizes_value
    try:
        if isinstance(sizes_value, str) and sizes_value.strip().startswith('[') and sizes_value.strip().endswith(']'):
            parsed = ast.literal_eval(sizes_value)
            if isinstance(parsed, (list, tuple)):
                cleaned = ", ".join(str(x).strip() for x in parsed)
    except Exception:
        cleaned = sizes_value

    if isinstance(cleaned, (list, tuple)):
        cleaned = ", ".join(str(x).strip() for x in cleaned)

    cleaned = str(cleaned).strip()
    tokens = [t.strip() for t in re.split(r',\s*|\s*;\s*', cleaned) if t.strip()]
    available = []
    filterable_sizes = []

    shoe_sizes = {'uk 5', 'uk 6', 'uk 7', 'uk 8', 'uk 9', 'uk 10', 'eu 38', 'eu 39', 'eu 40', 'eu 41', 'eu 42', 'eu 43'}
    clothing_sizes = {'extra small', 'small', 'medium', 'large', 'extra large', 'one size'}
    other_sizes = {'one size'}

    for t in tokens:
        tl = t.lower()
        if "currently unavailable" in tl:
            continue
        t_clean = re.sub(r'(?i)\s*currently\s*unavailable', '', t).strip()
        if t_clean:
            available.append(t_clean)
            size_lower = t_clean.lower()
            if category.lower() in ["boots", "shoes"]:
                if size_lower in shoe_sizes or re.match(r'^(uk|eu)\s*\d+(\.\d)?$', size_lower):
                    filterable_sizes.append(t_clean)
            elif category.lower() == "john lewis branded":
                if size_lower in clothing_sizes:
                    filterable_sizes.append(t_clean.title() if size_lower != "one size" else "One Size")
            else:
                if size_lower in other_sizes:
                    filterable_sizes.append("One Size")

    if not available:
        for t in tokens:
            if t.lower().strip() == "one size":
                available = ["One Size"]
                filterable_sizes = ["One Size"]
                break

    available_str = ", ".join(available) if available else "N/A"
    return cleaned, available, list(set(filterable_sizes))

def load_deals(filter_in_stock=False, search_query="", category_filter=None, size_filter=None, sort_by=None, page=1, per_page=50):
    """Load deals from CSV with pagination and sort by specified criterion."""
    deals = []
    errors = []
    print(f"Attempting to load CSV from: {CSV_FILE}")

    if not os.path.exists(CSV_FILE):
        print("CSV file not found.")
        errors.append(f"CSV file not found at {CSV_FILE}")
        return deals, errors, 0, 1

    try:
        file_size = os.path.getsize(CSV_FILE)
        print(f"CSV file size: {file_size} bytes")

        with open(CSV_FILE, 'r', encoding='utf-8-sig', errors='replace') as csvfile:
            try:
                csvfile.locking = False
            except Exception as e:
                print(f"Warning: couldn't handle lock: {e}")

            reader = csv.DictReader(csvfile)
            original_headers = [h.strip() for h in reader.fieldnames] if reader.fieldnames else []
            headers = original_headers.copy()
            if 'Name' in headers and 'Product Name' not in headers:
                headers[headers.index('Name')] = 'Product Name'
            if 'Discount (%)' in headers and 'Discount' not in headers:
                headers[headers.index('Discount (%)')] = 'Discount'
            reader.fieldnames = headers
            missing_headers = [h for h in ['Product Name', 'Current Price', 'Original Price', 'Discount',
                                          'Stock Status', 'Sizes', 'URL', 'Event Type', 'Timestamp', 'Category']
                              if h not in headers]
            if missing_headers:
                warn_msg = f"Warning: Missing expected headers: {missing_headers}. Attempting to continue."
                print(warn_msg)
                errors.append(warn_msg)

            row_count = 0
            for row in reader:
                row_count += 1

                if 'Name' in row and not row.get('Product Name'):
                    row['Product Name'] = row.pop('Name')

                img = _extract_image_from_row(row)
                row['Image'] = img or row.get('Image', '') or ''

                sizes_value = row.get('Sizes', 'N/A') or 'N/A'
                try:
                    if isinstance(sizes_value, str) and sizes_value.strip().startswith('[') and sizes_value.strip().endswith(']'):
                        parsed = ast.literal_eval(sizes_value)
                        if isinstance(parsed, (list, tuple)):
                            sizes_value = ", ".join(str(x).strip() for x in parsed)
                except Exception as e:
                    errors.append(f"Row {row_count}: Sizes parse error - {e}")
                    sizes_value = 'N/A'

                row = {k: (re.sub(r'""', '"', v).strip() if isinstance(v, str) else v) for k, v in row.items()}

                if not row.get('Product Name', '').strip():
                    errors.append(f"Row {row_count}: Skipped due to empty Product Name")
                    continue

                try:
                    current_price_raw = row.get('Current Price', '')
                    current_price = float(current_price_raw) if (current_price_raw and current_price_raw != 'N/A') else None
                except (ValueError, TypeError):
                    current_price = None

                try:
                    original_price_raw = row.get('Original Price', '')
                    original_price = float(original_price_raw) if (original_price_raw and original_price_raw != 'N/A') else None
                except (ValueError, TypeError):
                    original_price = None

                discount = 0.0
                discount_str = row.get('Discount', '') or row.get('Discount (%)', '') or ''
                if discount_str and discount_str != 'N/A':
                    m = re.search(r'(\d+\.?\d*)', str(discount_str))
                    if m:
                        try:
                            discount = float(m.group(1))
                        except Exception:
                            discount = 0.0
                if (discount == 0.0 or discount is None) and (current_price is not None and original_price is not None and original_price != 0):
                    try:
                        calculated_discount = (1 - (current_price / original_price)) * 100
                        discount = max(0.0, min(100.0, calculated_discount))
                    except Exception:
                        pass

                category = row.get('Category', 'Other').strip()
                cleaned_sizes_str, available_sizes_list, filterable_sizes = _clean_sizes_field(sizes_value, category)
                row['Sizes'] = cleaned_sizes_str
                available_sizes_str = ", ".join(available_sizes_list) if available_sizes_list else "N/A"

                stock_status = row.get('Stock Status', '').strip() or "Unknown"
                if available_sizes_list:
                    stock_status = "In Stock"
                elif stock_status.lower() in ["in stock", "out of stock", "not listed"]:
                    stock_status = stock_status.title()
                else:
                    stock_status = "Out of Stock"

                deal = {
                    "Product Name": row.get('Product Name', '').strip(),
                    "Current Price": current_price,
                    "Original Price": original_price,
                    "Discount": discount,
                    "Stock Status": stock_status,
                    "Sizes": row.get("Sizes", "N/A").strip(),
                    "Available Sizes": available_sizes_str,
                    "Filterable Sizes": filterable_sizes,
                    "URL": row.get("URL", "#").strip(),
                    "Event Type": row.get("Event Type", "N/A").strip().capitalize(),
                    "Timestamp": row.get("Timestamp", "N/A").strip(),
                    "Image": row.get("Image", "").strip(),
                    "Category": category
                }

                if filter_in_stock and "In Stock" not in deal["Stock Status"]:
                    continue
                if search_query and search_query.lower() not in deal["Product Name"].lower():
                    continue
                if category_filter and deal["Category"].lower() != category_filter.lower():
                    continue
                if size_filter and size_filter.lower() not in [s.lower() for s in deal["Filterable Sizes"]]:
                    continue

                deals.append(deal)

            if sort_by == "net_reduction":
                deals.sort(key=lambda x: (x['Original Price'] or 0) - (x['Current Price'] or 0) if x['Original Price'] and x['Current Price'] else 0, reverse=True)
            elif sort_by == "price":
                deals.sort(key=lambda x: x['Current Price'] or float('inf'))
            elif sort_by == "timestamp":
                deals.sort(key=lambda x: datetime.strptime(x['Timestamp'], '%Y-%m-%d %H:%M:%S') if x['Timestamp'] != 'N/A' else datetime.min, reverse=True)
            else:
                deals.sort(key=lambda x: x['Discount'] or 0, reverse=True)

            total_deals = len(deals)
            start_idx = (page - 1) * per_page
            end_idx = min(start_idx + per_page, total_deals)
            paginated_deals = deals[start_idx:end_idx]

            print(f"Loaded {len(paginated_deals)} deals (page {page} of {max(1, (total_deals + per_page - 1) // per_page)}) from CSV after filters.")
    except Exception as e:
        print(f"Error loading CSV: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        errors.append(f"Error loading CSV: {e}")

    total_pages = max(1, (len(deals) + per_page - 1) // per_page)
    return paginated_deals, errors, total_deals, total_pages

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main page showing the deals table with images and filter, with pagination."""
    filter_in_stock = request.form.get('filter_in_stock') == 'on'
    search_query = request.form.get('search_query', '')
    category_filter = request.form.get('category_filter', '')
    size_filter = request.form.get('size_filter', '')
    sort_by = request.form.get('sort_by', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    deals, errors, total_deals, total_pages = load_deals(filter_in_stock=filter_in_stock, search_query=search_query, category_filter=category_filter, size_filter=size_filter, sort_by=sort_by, page=page, per_page=per_page)
    num_deals = len(deals)
    last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cache_bust = f"?v={int(datetime.now().timestamp())}"

    all_sizes = set()
    for deal in deals:
        if not category_filter or deal["Category"].lower() == category_filter.lower():
            for size in deal["Filterable Sizes"]:
                all_sizes.add(size)
    size_options = sorted(all_sizes, key=lambda x: x if x not in ["Other", "One Size"] else "Z")

    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pegasus Monitors - John Lewis Deals</title>
        <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
        <meta http-equiv="Pragma" content="no-cache">
        <meta http-equiv="Expires" content="0">
        <link rel="stylesheet" href="/static/style.css{{ cache_bust }}">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap{{ cache_bust }}" rel="stylesheet">
    </head>
    <body>
        <div class="header">
            <img src="https://i.ibb.co/60C5BBMV/Pegasus-removebg-preview.png" alt="Pegasus Logo" class="logo">
            <div class="header-title">
                <h2>PEGASUS MONITORS</h2>
                <h3>John Lewis Deals</h3>
                <p class="tagline">Acquiring Deals</p>
                <p>Last updated: {{ last_updated }} | Auto-refreshing every 30m <span class="spinner"></span> | Found {{ total_deals }} deals</p>
            </div>
        </div>
        <div class="stats-hero">
            <div class="stat-card">
                <div class="stat-icon"></div>
                <h2 class="stat-number">{{ total_deals }}</h2>
                <p class="stat-label">Active Deals</p>
            </div>
            <div class="stat-card">
                <div class="stat-icon"></div>
                <h2 class="stat-number">{{ "%.1f"|format((deals|map(attribute='Discount')|max) if deals else 0) }}%</h2>
                <p class="stat-label">Max Discount</p>
            </div>
            <div class="stat-card">
                <div class="stat-icon"></div>
                <h2 class="stat-number">{{ deals|selectattr('Stock Status', 'equalto', 'In Stock')|list|length }}</h2>
                <p class="stat-label">In Stock</p>
            </div>
        </div>
        <div class="container">
            <form class="search-filter-bar" method="POST" action="?per_page={{ per_page }}">
                <input type="text" name="search_query" class="search-input" placeholder="Search deals by name..." value="{{ search_query }}">
                <div class="filter-bar">
                    <label><input type="checkbox" name="filter_in_stock" {% if filter_in_stock %}checked{% endif %}> Show only in-stock items</label>
                    <select name="category_filter" class="category-input">
                        <option value="">All Categories</option>
                        <option value="john lewis branded" {% if category_filter == 'john lewis branded' %}selected{% endif %}>John Lewis Branded</option>
                        <option value="boots" {% if category_filter == 'boots' %}selected{% endif %}>Boots</option>
                    </select>
                    <select name="size_filter" class="size-input">
                        <option value="">All Sizes</option>
                        {% for size in size_options %}
                            <option value="{{ size }}" {% if size_filter == size %}selected{% endif %}>{{ size }}</option>
                        {% endfor %}
                    </select>
                    <select name="sort_by" class="sort-input">
                        <option value="discount" {% if not sort_by or sort_by == 'discount' %}selected{% endif %}>Sort By: Discount (High to Low)</option>
                        <option value="net_reduction" {% if sort_by == 'net_reduction' %}selected{% endif %}>Sort By: Net Reduction (High to Low)</option>
                        <option value="price" {% if sort_by == 'price' %}selected{% endif %}>Sort By: Price (Low to High)</option>
                        <option value="timestamp" {% if sort_by == 'timestamp' %}selected{% endif %}>Sort By: Newest First</option>
                    </select>
                    <select name="per_page" class="per-page-input">
                        <option value="50" {% if per_page == 50 %}selected{% endif %}>50 per page</option>
                        <option value="100" {% if per_page == 100 %}selected{% endif %}>100 per page</option>
                        <option value="200" {% if per_page == 200 %}selected{% endif %}>200 per page</option>
                    </select>
                    <button type="submit">Apply</button>
                </div>
            </form>
            {% if errors %}
            <div class="error-message">
                <p>Error loading deals:</p>
                <ul>
                {% for error in errors %}
                    <li>{{ error }}</li>
                {% endfor %}
                </ul>
            </div>
            {% endif %}
            {% if deals %}
            <div class="deals-grid">
                {% for deal in deals %}
                <div class="deal-card" data-favorite="{% if deal['Product Name'] in favorites %}true{% else %}false{% endif %}">
                    <div class="image-placeholder">
                        {% if deal['Image'] %}
                        <a href="{{ deal['Image'] }}" target="_blank">
                            <img src="{{ deal['Image'] }}" class="deal-image" alt="Product Image" referrerpolicy="no-referrer" crossorigin="anonymous" onerror="this.src='https://via.placeholder.com/120?text=No+Image';">
                        </a>
                        {% else %}
                        <div class="image-placeholder">No Image</div>
                        {% endif %}
                    </div>
                    <div class="deal-info">
                        <h3 class="deal-name">{{ deal['Product Name'][:70] }}{% if deal['Product Name']|length > 70 %}...{% endif %}</h3>
                        <div class="deal-meta">
                            <div>Current: £{{ "%.2f"|format(deal['Current Price']) if deal['Current Price'] is not none else 'N/A' }}</div>
                            <div>Original: £{{ "%.2f"|format(deal['Original Price']) if deal['Original Price'] is not none else 'N/A' }}</div>
                            <div class="discount">{{ "%.1f"|format(deal['Discount']) if deal['Discount'] != 0 else 'N/A' }}%</div>
                            <div class="{% if 'In Stock' in deal['Stock Status'] %}status-in{% else %}status-out{% endif %}">
                                {{ deal['Stock Status'] }}
                            </div>
                            <div>{{ deal['Available Sizes'] if deal['Available Sizes'] != 'N/A' else 'N/A' }}</div>
                            <div>{{ deal['Event Type'] }}</div>
                            <div class="timestamp">{{ deal['Timestamp'] }}</div>
                        </div>
                    </div>
                    <div class="deal-action">
                        <a href="{{ deal['URL'] }}" target="_blank" class="btn-view" rel="noopener">View Product</a>
                        <button class="btn-favorite" data-product="{{ deal['Product Name'] }}">{% if deal['Product Name'] in favorites %}★{% else %}☆{% endif %}</button>
                    </div>
                </div>
                {% endfor %}
            </div>
            <div class="pagination">
                {% if total_pages > 1 %}
                    {% for p in range(1, total_pages + 1) %}
                        <a href="?page={{ p }}&per_page={{ per_page }}{% if filter_in_stock %}&filter_in_stock=on{% endif %}{% if search_query %}&search_query={{ search_query }}{% endif %}{% if category_filter %}&category_filter={{ category_filter }}{% endif %}{% if size_filter %}&size_filter={{ size_filter }}{% endif %}{% if sort_by %}&sort_by={{ sort_by }}{% endif %}" class="{% if p == page %}active{% endif %}">{{ p }}</a>
                    {% endfor %}
                {% endif %}
            </div>
            {% else %}
            <p class="empty">No deals yet! Our monitor is running in the background. Check back soon!</p>
            {% endif %}
        </div>
        <footer>Created by the original Resoled™</footer>
        <canvas id="stars-canvas"></canvas>
        <script src="/static/script.js{{ cache_bust }}"></script>
    </body>
    </html>
    """

    favorites = request.cookies.get('favorites')
    if favorites:
        try:
            favorites = ast.literal_eval(favorites)
            if not isinstance(favorites, list):
                favorites = []
        except:
            favorites = []
    else:
        favorites = []

    response = make_response(render_template_string(template, deals=deals, num_deals=num_deals, last_updated=last_updated,
                                                   filter_in_stock=filter_in_stock, search_query=search_query, errors=errors,
                                                   cache_bust=cache_bust, category_filter=category_filter, size_filter=size_filter,
                                                   size_options=size_options, sort_by=sort_by, favorites=favorites,
                                                   total_pages=total_pages, page=page, total_deals=total_deals, per_page=per_page))

    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src *; script-src 'self' 'unsafe-eval'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com;"
    print(f"Applied CSP: {response.headers['Content-Security-Policy']}")
    response.set_cookie('favorites', str(favorites), max_age=3600)
    return response

if __name__ == '__main__':
    app.static_folder = 'static'
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))

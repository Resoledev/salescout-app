"""
Updated Flask app for SaleScout with modern design
Replace your current app.py with this
"""
from flask import Flask, render_template, jsonify, request
import csv
import os
import json
from datetime import datetime

app = Flask(__name__)

# Price history file paths
PRICE_HISTORY_FILES = {
    'johnlewis': 'johnlewis_price_history.json',
    'selfridges': 'selfridges_price_history.json'
}

def load_price_history(retailer):
    """Load price history for recently reduced detection"""
    price_history_file = PRICE_HISTORY_FILES.get(retailer)
    if not price_history_file or not os.path.exists(price_history_file):
        return {}

    try:
        with open(price_history_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def is_recently_reduced(product_id, retailer):
    """Check if product is recently reduced"""
    price_history = load_price_history(retailer)
    return price_history.get(str(product_id), {}).get("recently_reduced", False)

def read_selfridges_csv(csv_path='salescout_selfridges.csv'):
    """Read Selfridges CSV data with recently reduced detection"""
    products = []
    if not os.path.exists(csv_path):
        return products

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Handle CSV fields based on your structure
                product_id = row.get('id', '')
                current_price = float(row.get('current_price', 0)) if row.get('current_price') else 0
                original_price = float(row.get('original_price', 0)) if row.get('original_price') else 0

                # Calculate discount if not provided
                discount = 0
                if row.get('discount_percent'):
                    discount = float(row.get('discount_percent', 0))
                elif original_price and current_price and original_price > current_price:
                    discount = ((original_price - current_price) / original_price) * 100

                product = {
                    'id': product_id,
                    'name': row.get('name', ''),
                    'brand': row.get('brand', ''),
                    'current_price': current_price,
                    'original_price': original_price,
                    'discount': round(discount, 1),
                    'stock_status': row.get('stock_status', 'Unknown'),
                    'sizes': 'See product page',  # Selfridges doesn't seem to have sizes in CSV
                    'url': row.get('url', ''),
                    'image': row.get('image_url', ''),
                    'category': row.get('category', 'Selfridges'),
                    'timestamp': row.get('last_updated', ''),
                    'retailer': 'Selfridges',
                    'recently_reduced': is_recently_reduced(product_id, 'selfridges')
                }

                if product['original_price'] and product['current_price']:
                    product['savings'] = product['original_price'] - product['current_price']
                else:
                    product['savings'] = 0

                products.append(product)
    except Exception as e:
        print(f"Error reading Selfridges CSV: {e}")

    return products

def read_johnlewis_csv(csv_path='johnlewisv2.csv'):
    """Read John Lewis CSV data with recently reduced detection"""
    products = []
    if not os.path.exists(csv_path):
        return products

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                product_id = row.get('Product ID', '')
                current_price = float(row.get('Current Price', 0)) if row.get('Current Price') else 0
                original_price = float(row.get('Original Price', 0)) if row.get('Original Price') else 0
                discount = float(row.get('Discount', 0)) if row.get('Discount') else 0

                product = {
                    'id': product_id,
                    'name': row.get('Product Name', ''),
                    'brand': 'John Lewis',
                    'current_price': current_price,
                    'original_price': original_price,
                    'discount': discount,
                    'stock_status': row.get('Stock Status', 'Unknown'),
                    'sizes': row.get('Sizes', 'See product page'),
                    'url': row.get('URL', ''),
                    'image': row.get('Image', ''),
                    'category': row.get('Category', 'John Lewis'),
                    'timestamp': row.get('Timestamp', ''),
                    'retailer': 'John Lewis',
                    'recently_reduced': is_recently_reduced(product_id, 'johnlewis')
                }

                if product['original_price'] and product['current_price']:
                    product['savings'] = product['original_price'] - product['current_price']
                else:
                    product['savings'] = 0

                products.append(product)
    except Exception as e:
        print(f"Error reading John Lewis CSV: {e}")

    return products

@app.route('/')
def home():
    """Modern SaaS homepage"""
    selfridges = read_selfridges_csv()
    johnlewis = read_johnlewis_csv()

    # Calculate live stats for homepage
    jl_stats = {
        'total': len(johnlewis),
        'max_discount': max([p['discount'] for p in johnlewis], default=0),
        'recently_reduced': sum(1 for p in johnlewis if p.get('recently_reduced', False))
    }

    sf_stats = {
        'total': len(selfridges),
        'max_discount': max([p['discount'] for p in selfridges], default=0),
        'recently_reduced': sum(1 for p in selfridges if p.get('recently_reduced', False))
    }

    return render_template('modern_home.html',
                         johnlewis_stats=jl_stats,
                         selfridges_stats=sf_stats)

@app.route('/<retailer>')
def retailer_page(retailer):
    """Modern retailer pages with filtering and sorting"""
    if retailer not in ['selfridges', 'johnlewis']:
        return "Retailer not found", 404

    # Get query parameters for filtering/sorting
    search_query = request.args.get('search', '').lower()
    sort_by = request.args.get('sort', 'discount')
    category_filter = request.args.get('category', '')

    # Load products
    if retailer == 'selfridges':
        products = read_selfridges_csv()
        retailer_name = 'Selfridges'
        color_theme = 'purple'
    else:
        products = read_johnlewis_csv()
        retailer_name = 'John Lewis'
        color_theme = 'green'

    # Apply filters
    if search_query:
        products = [p for p in products if search_query in p['name'].lower()]

    if category_filter:
        products = [p for p in products if category_filter.lower() in p['category'].lower()]

    # Apply sorting
    if sort_by == 'recently_reduced':
        products.sort(key=lambda x: (x.get('recently_reduced', False), x['discount']), reverse=True)
    elif sort_by == 'net_reduction':
        products.sort(key=lambda x: x.get('savings', 0), reverse=True)
    elif sort_by == 'price':
        products.sort(key=lambda x: x['current_price'] or float('inf'))
    elif sort_by == 'name':
        products.sort(key=lambda x: x['name'])
    else:  # discount
        products.sort(key=lambda x: x['discount'], reverse=True)

    # Calculate stats
    stats = {
        'total_products': len(products),
        'avg_discount': round(sum(p['discount'] for p in products if p['discount'] > 0) / max(1, len([p for p in products if p['discount'] > 0])), 1),
        'max_discount': max([p['discount'] for p in products], default=0),
        'total_savings': sum(p.get('savings', 0) for p in products),
        'recently_reduced_count': sum(1 for p in products if p.get('recently_reduced', False)),
        'last_updated': products[0]['timestamp'] if products else 'Never'
    }

    return render_template('modern_retailer.html',
                         products=products,
                         retailer=retailer_name,
                         retailer_key=retailer,
                         stats=stats,
                         color_theme=color_theme,
                         current_search=request.args.get('search', ''),
                         current_sort=sort_by,
                         current_category=category_filter)

# API endpoints (keep existing)
@app.route('/api/selfridges')
def api_selfridges():
    """Selfridges API endpoint"""
    products = read_selfridges_csv()
    return jsonify({
        'retailer': 'Selfridges',
        'total_products': len(products),
        'products': products
    })

@app.route('/api/johnlewis')
def api_johnlewis():
    """John Lewis API endpoint"""
    products = read_johnlewis_csv()
    return jsonify({
        'retailer': 'John Lewis',
        'total_products': len(products),
        'products': products
    })

@app.route('/api/deals')
def api_deals():
    """Combined deals API"""
    selfridges = read_selfridges_csv()
    johnlewis = read_johnlewis_csv()

    all_products = selfridges + johnlewis
    all_products.sort(key=lambda x: x['discount'], reverse=True)

    return jsonify({
        'total_products': len(all_products),
        'selfridges_count': len(selfridges),
        'johnlewis_count': len(johnlewis),
        'products': all_products
    })

if __name__ == '__main__':
    app.run(debug=True)

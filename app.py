"""
Simple Flask app for SaleScout - works with your existing setup
Upload this as your main Flask file to GitHub/Render
"""
from flask import Flask, render_template, jsonify
import csv
import os

app = Flask(__name__)

def read_selfridges_csv(csv_path='salescout_selfridges.csv'):
    """Read Selfridges CSV data"""
    products = []
    if not os.path.exists(csv_path):
        return products

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                product = {
                    'id': row.get('Product ID', ''),
                    'name': row.get('Product Name', ''),
                    'current_price': float(row.get('Current Price', 0)) if row.get('Current Price') else 0,
                    'original_price': float(row.get('Original Price', 0)) if row.get('Original Price') else 0,
                    'discount': float(row.get('Discount', 0)) if row.get('Discount') else 0,
                    'stock_status': row.get('Stock Status', 'Unknown'),
                    'sizes': row.get('Sizes', 'See product page'),
                    'url': row.get('URL', ''),
                    'image': row.get('Image', ''),
                    'category': row.get('Category', 'Selfridges'),
                    'timestamp': row.get('Timestamp', ''),
                    'retailer': 'Selfridges'
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
    """Read John Lewis CSV data"""
    products = []
    if not os.path.exists(csv_path):
        return products

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                product = {
                    'id': row.get('Product ID', ''),
                    'name': row.get('Product Name', ''),
                    'current_price': float(row.get('Current Price', 0)) if row.get('Current Price') else 0,
                    'original_price': float(row.get('Original Price', 0)) if row.get('Original Price') else 0,
                    'discount': float(row.get('Discount', 0)) if row.get('Discount') else 0,
                    'stock_status': row.get('Stock Status', 'Unknown'),
                    'sizes': row.get('Sizes', 'See product page'),
                    'url': row.get('URL', ''),
                    'image': row.get('Image', ''),
                    'category': row.get('Category', 'John Lewis'),
                    'timestamp': row.get('Timestamp', ''),
                    'retailer': 'John Lewis'
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
    """Home page - shows both retailers"""
    selfridges = read_selfridges_csv()
    johnlewis = read_johnlewis_csv()

    total_products = len(selfridges) + len(johnlewis)

    return f"""
    <h1>SaleScout - Retailer Deals</h1>
    <p>Total Products: {total_products}</p>
    <p><a href="/selfridges">Selfridges ({len(selfridges)} products)</a></p>
    <p><a href="/johnlewis">John Lewis ({len(johnlewis)} products)</a></p>
    <p><a href="/api/deals">All Deals API</a></p>
    """

@app.route('/selfridges')
def selfridges():
    """Selfridges deals page"""
    products = read_selfridges_csv()
    products.sort(key=lambda x: x['discount'], reverse=True)

    stats = {
        'total_products': len(products),
        'avg_discount': round(sum(p['discount'] for p in products if p['discount'] > 0) / max(1, len([p for p in products if p['discount'] > 0])), 1),
        'max_discount': max([p['discount'] for p in products], default=0),
        'total_savings': sum(p['savings'] for p in products),
        'last_updated': products[0]['timestamp'] if products else 'Never'
    }

    return render_template('retailer_page.html', products=products, retailer='Selfridges', stats=stats)

@app.route('/johnlewis')
def johnlewis():
    """John Lewis deals page"""
    products = read_johnlewis_csv()
    products.sort(key=lambda x: x['discount'], reverse=True)

    stats = {
        'total_products': len(products),
        'avg_discount': round(sum(p['discount'] for p in products if p['discount'] > 0) / max(1, len([p for p in products if p['discount'] > 0])), 1),
        'max_discount': max([p['discount'] for p in products], default=0),
        'total_savings': sum(p['savings'] for p in products),
        'last_updated': products[0]['timestamp'] if products else 'Never'
    }

    return render_template('retailer_page.html', products=products, retailer='John Lewis', stats=stats)

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
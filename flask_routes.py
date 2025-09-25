"""
Flask routes for SaleScout v3 - Selfridges and John Lewis integration
Copy this code to your main Flask app
"""
import csv
import os
from flask import render_template, jsonify
from datetime import datetime

def read_selfridges_csv(csv_path='salescout_selfridges.csv'):
    """Read Selfridges CSV data"""
    products = []
    if not os.path.exists(csv_path):
        return products

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Clean and format data
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

                # Calculate savings
                if product['original_price'] and product['current_price']:
                    product['savings'] = product['original_price'] - product['current_price']
                else:
                    product['savings'] = 0

                products.append(product)
    except Exception as e:
        print(f"Error reading Selfridges CSV: {e}")

    return products

def read_johnlewis_csv(csv_path='salescout_johnlewis.csv'):
    """Read John Lewis CSV data"""
    products = []
    if not os.path.exists(csv_path):
        return products

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Clean and format data
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

                # Calculate savings
                if product['original_price'] and product['current_price']:
                    product['savings'] = product['original_price'] - product['current_price']
                else:
                    product['savings'] = 0

                products.append(product)
    except Exception as e:
        print(f"Error reading John Lewis CSV: {e}")

    return products

# Flask route for Selfridges page
def selfridges_route():
    """Route handler for /selfridges"""
    products = read_selfridges_csv()

    # Sort by discount descending
    products.sort(key=lambda x: x['discount'], reverse=True)

    stats = {
        'total_products': len(products),
        'avg_discount': round(sum(p['discount'] for p in products if p['discount'] > 0) / max(1, len([p for p in products if p['discount'] > 0])), 1),
        'max_discount': max([p['discount'] for p in products], default=0),
        'total_savings': sum(p['savings'] for p in products),
        'last_updated': products[0]['timestamp'] if products else 'Never'
    }

    return render_template('retailer_page.html',
                         products=products,
                         retailer='Selfridges',
                         stats=stats)

# Flask route for John Lewis page
def johnlewis_route():
    """Route handler for /johnlewis"""
    products = read_johnlewis_csv()

    # Sort by discount descending
    products.sort(key=lambda x: x['discount'], reverse=True)

    stats = {
        'total_products': len(products),
        'avg_discount': round(sum(p['discount'] for p in products if p['discount'] > 0) / max(1, len([p for p in products if p['discount'] > 0])), 1),
        'max_discount': max([p['discount'] for p in products], default=0),
        'total_savings': sum(p['savings'] for p in products),
        'last_updated': products[0]['timestamp'] if products else 'Never'
    }

    return render_template('retailer_page.html',
                         products=products,
                         retailer='John Lewis',
                         stats=stats)

# API endpoints for JSON data
def selfridges_api():
    """API endpoint for Selfridges data"""
    products = read_selfridges_csv()
    return jsonify({
        'retailer': 'Selfridges',
        'total_products': len(products),
        'products': products
    })

def johnlewis_api():
    """API endpoint for John Lewis data"""
    products = read_johnlewis_csv()
    return jsonify({
        'retailer': 'John Lewis',
        'total_products': len(products),
        'products': products
    })

# Combined data endpoint
def combined_deals_api():
    """API endpoint for all deals combined"""
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

"""
ADD THESE ROUTES TO YOUR MAIN FLASK APP:

@app.route('/selfridges')
def selfridges():
    return selfridges_route()

@app.route('/johnlewis')
def johnlewis():
    return johnlewis_route()

@app.route('/api/selfridges')
def api_selfridges():
    return selfridges_api()

@app.route('/api/johnlewis')
def api_johnlewis():
    return johnlewis_api()

@app.route('/api/deals')
def api_deals():
    return combined_deals_api()
"""
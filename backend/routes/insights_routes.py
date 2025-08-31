from flask import Blueprint, jsonify, request
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from prophet import Prophet
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from datetime import datetime, timedelta
from itertools import combinations
import requests
import json
import re
from database import get_db

insights_bp = Blueprint('insights', __name__)

# Cache variables
cached_combos = None
combo_cache_timestamp = None
COMBO_CACHE_DURATION = timedelta(minutes=5)

cached_forecast = None
forecast_cache_timestamp = None
FORECAST_CACHE_DURATION = timedelta(hours=24)

cached_segments = None
segments_cache_timestamp = None
SEGMENTS_CACHE_DURATION = timedelta(hours=24)

def get_most_popular_combos():
    """Get the most popular product combinations using association rules"""
    global cached_combos, combo_cache_timestamp
    
    # Check if cache is valid
    if cached_combos and combo_cache_timestamp and (datetime.now() - combo_cache_timestamp) < COMBO_CACHE_DURATION:
        return cached_combos
    
    try:
        db = get_db()
        bills_collection = db['bills']
        
        # Fetch bills with items
        bills = bills_collection.find({}, {'items.item_name': 1, '_id': 0})
        
        # Prepare transaction data
        transactions = []
        for bill in bills:
            items = [item['item_name'] for item in bill.get('items', [])]
            if len(items) > 1:  # Only include bills with multiple items
                transactions.append(list(set(items)))  # Add all items in the bill as one transaction
                
                if not transactions:
                    cached_combos = [{'combo': "No combos found", 'count': 0}]
                    combo_cache_timestamp = datetime.now()
                    return cached_combos
        
        # Create a one-hot encoded DataFrame
        all_items = sorted(set(item for transaction in transactions for item in transaction))
        transaction_dict = []
        for transaction in transactions:
            transaction_dict.append({item: (item in transaction) for item in all_items})
        
        df = pd.DataFrame(transaction_dict)
        
        # Calculate min_support based on a minimum number of occurrences (e.g., 2 bills)
        min_occurrences = 2
        min_support = max(min_occurrences / len(transactions), 0.001) if transactions else 0.01
        print(f"Debug: Number of transactions = {len(transactions)}, min_support = {min_support}")
        frequent_itemsets = apriori(df, min_support=min_support, use_colnames=True)
        print(f"Debug: Frequent itemsets = {frequent_itemsets}")
        
        # Generate association rules
        if not frequent_itemsets.empty:
            rules = association_rules(frequent_itemsets, metric="support", min_threshold=min_support)
            print(f"Debug: Association rules = {rules}")
            rules['item_count'] = rules['antecedents'].apply(len) + rules['consequents'].apply(len)
            rules = rules[rules['item_count'] == 2]
            if not rules.empty:
                combos = []
                seen_combos = set()
                # Sort rules by support and filter those meeting or exceeding min_support
                rules = rules.sort_values(by='support', ascending=False)
                min_support = max(2 / len(transactions), 0.001)  # Recompute min_support for clarity
                print(f"Debug: Applying min_support = {min_support}")
                for _, rule in rules[rules['support'] >= min_support].iterrows():
                    items = sorted(set(list(rule['antecedents']) + list(rule['consequents'])))
                    combo_str = f"{items[0]} + {items[1]}"
                    if combo_str not in seen_combos:
                        seen_combos.add(combo_str)
                        count = int(round(rule['support'] * len(transactions), 0))
                        combos.append({'combo': combo_str, 'count': count})
                        if len(combos) >= 3:  # Stop after 3 unique combos
                            break
                cached_combos = combos[:3]
                while len(cached_combos) < 3:
                    cached_combos.append({'combo': "N/A", 'count': 0})
                print(f"Debug: Final combos = {cached_combos}")
            else:
                cached_combos = [{'combo': "No combos found", 'count': 0}]
        else:
            cached_combos = [{'combo': "No combos found", 'count': 0}]
        
        # Update cache
        combo_cache_timestamp = datetime.now()
        
    except Exception as e:
        print(f"Error in get_most_popular_combos: {e}")
        cached_combos = [{'combo': "Error loading combos", 'count': 0}]
        combo_cache_timestamp = datetime.now()
    
    return cached_combos

def get_demand_forecast():
    """Get demand forecast for next 7 days using Prophet"""
    global cached_forecast, forecast_cache_timestamp
    
    # Check if cache is valid
    if cached_forecast and forecast_cache_timestamp and (datetime.now() - forecast_cache_timestamp) < FORECAST_CACHE_DURATION:
        return cached_forecast
    
    try:
        db = get_db()
        bills_collection = db['bills']
        
        # Aggregate sales by item and date
        pipeline = [
            {"$unwind": "$items"},
            {"$group": {
                "_id": {
                    "item_name": "$items.item_name",
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}
                },
                "total_quantity": {"$sum": "$items.quantity"}
            }},
            {"$project": {
                "item_name": "$_id.item_name",
                "ds": "$_id.date",
                "y": "$total_quantity",
                "_id": 0
            }}
        ]
        sales_data = list(bills_collection.aggregate(pipeline))
        print(f"Debug: Sales data points = {len(sales_data)}")
        
        if not sales_data:
            cached_forecast = []
            forecast_cache_timestamp = datetime.now()
            return cached_forecast
        
        # Convert to DataFrame
        df = pd.DataFrame(sales_data)
        df['ds'] = pd.to_datetime(df['ds'])
        
        # Get unique items
        items = df['item_name'].unique()
        forecasts = []
        
        # Limit to top 5 items by total quantity to keep it lightweight
        top_items = df.groupby('item_name')['y'].sum().nlargest(5).index
        print(f"Debug: Top 5 items by total quantity: {list(top_items)}")
        
        for item in top_items:
            item_df = df[df['item_name'] == item][['ds', 'y']].sort_values('ds')
            print(f"Debug: Item {item} has {len(item_df)} data points: {item_df}")
            if len(item_df) < 2:  # Reduced from 3 to 2
                print(f"Debug: Skipping {item} due to insufficient data points (< 2)")
                continue
            try:
                model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=False)
                model.fit(item_df)
                future = model.make_future_dataframe(periods=7)
                forecast = model.predict(future)
                future_forecast = forecast[forecast['ds'] > item_df['ds'].max()][['ds', 'yhat']]
                total_predicted = round(future_forecast['yhat'].apply(lambda x: max(0, x)).sum(), 2)
                forecasts.append({'item_name': item, 'predicted_quantity': total_predicted})
            except Exception as e:
                print(f"Debug: Error forecasting for item {item}: {e}")
                continue
        
        # Sort by predicted quantity
        forecasts = sorted(forecasts, key=lambda x: x['predicted_quantity'], reverse=True)
        
        # Update cache
        cached_forecast = forecasts
        forecast_cache_timestamp = datetime.now()
        
    except Exception as e:
        print(f"Error in get_demand_forecast: {e}")
        cached_forecast = []
        forecast_cache_timestamp = datetime.now()
    
    return cached_forecast

def get_customer_segments():
    """Get customer segments using K-means clustering"""
    global cached_segments, segments_cache_timestamp
    
    # Check if cache is valid
    if cached_segments and segments_cache_timestamp and (datetime.now() - segments_cache_timestamp) < SEGMENTS_CACHE_DURATION:
        return cached_segments
    
    try:
        db = get_db()
        bills_collection = db['bills']
        
        # Aggregate customer data
        pipeline = [
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$customer_id",
                "purchase_count": {"$sum": 1},
                "total_spend": {"$sum": "$final_amount"},
                "avg_spend": {"$avg": "$final_amount"},
                "unique_items": {"$addToSet": "$items.item_name"},
                "top_item": {"$first": "$items.item_name"}
            }},
            {"$project": {
                "customer_id": "$_id",
                "purchase_count": 1,
                "total_spend": 1,
                "avg_spend": 1,
                "item_diversity": {"$size": "$unique_items"},
                "top_item": 1,
                "_id": 0
            }}
        ]
        customer_data = list(bills_collection.aggregate(pipeline))
        print(f"Debug: Number of unique customers = {len(customer_data)}")
        
        if not customer_data:
            cached_segments = []
            segments_cache_timestamp = datetime.now()
            return cached_segments
        
        # Convert to DataFrame
        df = pd.DataFrame(customer_data)
        
        # Features for clustering
        features = ['purchase_count', 'avg_spend', 'item_diversity']
        X = df[features].fillna(0)
        n_samples = len(X)
        
        # Determine optimal number of clusters using silhouette score
        max_clusters = min(n_samples // 2, 5)  # Limit to half the samples or 5
        print(f"Debug: Max clusters = {max_clusters}, Samples = {n_samples}")
        if max_clusters < 2:
            max_clusters = 2  # Minimum 2 clusters
        best_score = -1
        best_n_clusters = 2
        if n_samples >= 2:
            for n_clusters in range(2, max_clusters + 1):
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                labels = kmeans.fit_predict(X)
                score = silhouette_score(X, labels)
                print(f"Debug: Clusters = {n_clusters}, Silhouette Score = {score}")
                if score > best_score:
                    best_score = score
                    best_n_clusters = n_clusters
        
        # Apply K-means with optimal number of clusters
        kmeans = KMeans(n_clusters=best_n_clusters, random_state=42, n_init=10)
        df['segment'] = kmeans.fit_predict(X)
        
        # Define segment names based on characteristics
        segment_names = {}
        for segment_id in df['segment'].unique():
            segment_df = df[df['segment'] == segment_id]
            avg_spend = segment_df['avg_spend'].mean()
            avg_purchases = segment_df['purchase_count'].mean()
            avg_diversity = segment_df['item_diversity'].mean()
            if avg_spend > df['avg_spend'].mean() and avg_purchases > df['purchase_count'].mean():
                segment_names[segment_id] = "High-Value Shoppers"
            elif avg_purchases > df['purchase_count'].mean():
                segment_names[segment_id] = "Frequent Shoppers"
            elif avg_diversity > df['item_diversity'].mean():
                segment_names[segment_id] = "Variety Seekers"
            else:
                segment_names[segment_id] = "Occasional Shoppers"
        
        # Summarize segments
        segments = []
        for segment_id in df['segment'].unique():
            segment_df = df[df['segment'] == segment_id]
            segments.append({
                'name': segment_names.get(segment_id, f"Segment {segment_id}"),
                'count': len(segment_df),
                'avg_purchase_count': round(segment_df['purchase_count'].mean(), 2),
                'avg_spend': round(segment_df['avg_spend'].mean(), 2),
                'common_item': segment_df['top_item'].mode()[0] if not segment_df['top_item'].empty else "None"
            })
        
        # Update cache
        cached_segments = segments
        segments_cache_timestamp = datetime.now()
        
    except Exception as e:
        print(f"Error in get_customer_segments: {e}")
        cached_segments = []
        segments_cache_timestamp = datetime.now()
    
    return cached_segments

def format_markdown_to_html(text):
    """Convert basic markdown formatting to HTML"""
    if not text:
        return text
    
    # Convert **bold** to <strong>
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    
    # Convert *italic* to <em>
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    
    # Convert _underline_ to <u>
    text = re.sub(r'_(.*?)_', r'<u>\1</u>', text)
    
    # Convert `code` to <code>
    text = re.sub(r'`(.*?)`', r'<code class="bg-gray-200 px-1 rounded">\1</code>', text)
    
    # Handle bullet points - convert * at beginning of line to proper list items
    lines = text.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('* '):
            if not in_list:
                if formatted_lines and formatted_lines[-1] != '<ul>':
                    formatted_lines.append('<ul>')
                else:
                    formatted_lines.append('<ul>')
                in_list = True
            # Remove the * and add as list item
            list_item = stripped_line[2:].strip()
            formatted_lines.append(f'<li>{list_item}</li>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            if stripped_line:  # Only add non-empty lines
                formatted_lines.append(stripped_line)
            else:
                formatted_lines.append('<br>')
    
    # Close list if still open
    if in_list:
        formatted_lines.append('</ul>')
    
    # Join lines and convert remaining line breaks
    text = '\n'.join(formatted_lines)
    text = text.replace('\n', '<br>')
    
    # Clean up multiple <br> tags
    text = re.sub(r'(<br>\s*){3,}', '<br><br>', text)
    
    return text

def get_hindi_explanation(data_type, data):
    """Get Hindi explanation using Gemini API"""
    # Gemini API endpoint
    api_key = "AIzaSyCpkWlVYQ4YGczyeHqKid-gw26KUSdwznQ"
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    # Prepare prompt based on data type with better Hindi instruction
    base_instruction = "कृपया निम्नलिखित डेटा को हिंदी में समझाएं। यह एक किराना स्टोर के लिए है। सरल और स्पष्ट भाषा का प्रयोग करें।"
    
    if data_type == "combos" and data and data[0]['combo'] != "No combos found":
        prompt = f"{base_instruction} प्रॉडक्ट कॉम्बो डेटा: {data}। इन कॉम्बो की व्याख्या करें कि कौन से प्रॉडक्ट एक साथ खरीदे जाते हैं।"
    elif data_type == "forecast" and data:
        prompt = f"{base_instruction} मांग पूर्वानुमान डेटा: {data}। अगले 7 दिनों में किन प्रॉडक्ट्स की कितनी मांग हो सकती है, इसकी व्याख्या करें।"
    elif data_type == "segments" and data:
        prompt = f"{base_instruction} ग्राहक खंड डेटा: {data}। विभिन्न प्रकार के ग्राहकों की व्याख्या करें।"
    else:
        prompt = f"{base_instruction} फिलहाल {data_type} का कोई डेटा उपलब्ध नहीं है।"
    
    # API request payload
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7, 
            "maxOutputTokens": 800,
            "topK": 40,
            "topP": 0.95
        }
    }
    
    try:
        response = requests.post(
            api_url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
        
        # Handle different response structures
        if 'candidates' in result and result['candidates']:
            candidate = result['candidates'][0]
            if 'content' in candidate and 'parts' in candidate['content'] and candidate['content']['parts']:
                explanation = candidate['content']['parts'][0].get('text', '')
                if explanation.strip():
                    # Format markdown to HTML
                    formatted_explanation = format_markdown_to_html(explanation.strip())
                    return formatted_explanation
        
        # Fallback message
        return "हिंदी में व्याख्या उपलब्ध नहीं है। कृपया बाद में पुनः प्रयास करें।"
        
    except requests.exceptions.Timeout:
        print("Gemini API timeout")
        return "समय सीमा समाप्त। कृपया बाद में पुनः प्रयास करें।"
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Gemini API: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"API Error Details: {e.response.text}")
        return "हिंदी में व्याख्या प्राप्त करने में त्रुटि हुई। कृपया बाद में पुनः प्रयास करें।"
    except Exception as e:
        print(f"Unexpected error in get_hindi_explanation: {e}")
        return "अप्रत्याशित त्रुटि हुई। कृपया बाद में पुनः प्रयास करें।"

@insights_bp.route('/insights', methods=['GET'])
def get_insights():
    """Main insights endpoint that returns all analytics data"""
    try:
        # Check if force refresh is requested
        force_refresh = request.args.get('force', 'false').lower() == 'true'
        
        if force_refresh:
            # Clear all caches
            global cached_combos, combo_cache_timestamp
            global cached_forecast, forecast_cache_timestamp  
            global cached_segments, segments_cache_timestamp
            cached_combos = None
            combo_cache_timestamp = None
            cached_forecast = None
            forecast_cache_timestamp = None
            cached_segments = None
            segments_cache_timestamp = None
        
        # Get all data
        combo_data = get_most_popular_combos()
        forecast_data = get_demand_forecast()
        segment_data = get_customer_segments()
        
        # Get Hindi explanations
        hindi_combo_explanation = get_hindi_explanation("combos", combo_data)
        hindi_forecast_explanation = get_hindi_explanation("forecast", forecast_data)
        hindi_segment_explanation = get_hindi_explanation("segments", segment_data)
        
        return jsonify({
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'combos': combo_data,
            'forecasts': forecast_data,
            'segments': segment_data,
            'explanations': {
                'hindi_combo_explanation': hindi_combo_explanation,
                'hindi_forecast_explanation': hindi_forecast_explanation,
                'hindi_segment_explanation': hindi_segment_explanation
            }
        }), 200
        
    except Exception as e:
        print(f"Error in insights endpoint: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'combos': [{'combo': "Error loading data", 'count': 0}],
            'forecasts': [],
            'segments': [],
            'explanations': {
                'hindi_combo_explanation': "डेटा लोड करने में त्रुटि हुई।",
                'hindi_forecast_explanation': "पूर्वानुमान डेटा उपलब्ध नहीं है।",
                'hindi_segment_explanation': "ग्राहक खंड डेटा उपलब्ध नहीं है।"
            }
        }), 500

@insights_bp.route('/insights/combos', methods=['GET'])
def get_combos_only():
    """Get only combo data"""
    try:
        combo_data = get_most_popular_combos()
        hindi_explanation = get_hindi_explanation("combos", combo_data)
        
        return jsonify({
            'status': 'success',
            'combos': combo_data,
            'explanation': hindi_explanation
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@insights_bp.route('/insights/forecast', methods=['GET'])
def get_forecast_only():
    """Get only forecast data"""
    try:
        forecast_data = get_demand_forecast()
        hindi_explanation = get_hindi_explanation("forecast", forecast_data)
        
        return jsonify({
            'status': 'success',
            'forecasts': forecast_data,
            'explanation': hindi_explanation
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@insights_bp.route('/insights/segments', methods=['GET'])
def get_segments_only():
    """Get only customer segment data"""
    try:
        segment_data = get_customer_segments()
        hindi_explanation = get_hindi_explanation("segments", segment_data)
        
        return jsonify({
            'status': 'success',
            'segments': segment_data,
            'explanation': hindi_explanation
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
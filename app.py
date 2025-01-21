from flask import Flask, render_template, request, jsonify
import requests
import sqlite3
from datetime import datetime
import concurrent.futures
import re
import hashlib
import whois
import dns.resolver
import shodan
from bs4 import BeautifulSoup
import json
import socket
from urllib.parse import urlparse, quote_plus
import phonenumbers
from phonenumbers import geocoder, carrier, timezone

app = Flask(__name__)

# Configuración de APIs
SHODAN_API_KEY = "Your_API_HERE"

def init_db():
    conn = sqlite3.connect('searches.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS searches
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  query TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def save_search(query):
    conn = sqlite3.connect('searches.db')
    c = conn.cursor()
    c.execute('INSERT INTO searches (query) VALUES (?)', (query,))
    conn.commit()
    conn.close()

def check_phone_number(number):
    try:
        # Parsear el número
        parsed_number = phonenumbers.parse(number)
        
        if not phonenumbers.is_valid_number(parsed_number):
            return {
                'valid': False,
                'message': 'Número de teléfono inválido'
            }
        
        # Información básica
        basic_info = {
            'valid': True,
            'formatted': phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            'location': {
                'country': geocoder.description_for_number(parsed_number, "es"),
                'region': geocoder.description_for_number(parsed_number, "es"),
                'carrier': carrier.name_for_number(parsed_number, "es"),
                'timezone': timezone.time_zones_for_number(parsed_number),
                'line_type': 'Móvil' if phonenumbers.number_type(parsed_number) == phonenumbers.PhoneNumberType.MOBILE else 'Fijo',
                'valid': phonenumbers.is_valid_number(parsed_number)
            },
            'security': {
                'voip': phonenumbers.number_type(parsed_number) == phonenumbers.PhoneNumberType.VOIP,
                'premium': phonenumbers.number_type(parsed_number) == phonenumbers.PhoneNumberType.PREMIUM_RATE,
                'trusted': phonenumbers.number_type(parsed_number) in [
                    phonenumbers.PhoneNumberType.MOBILE,
                    phonenumbers.PhoneNumberType.FIXED_LINE
                ]
            }
        }
        
        # Búsqueda en redes sociales
        services = {
            'WhatsApp': f'https://api.whatsapp.com/send?phone={number.replace("+", "")}',
            'Telegram': f'https://t.me/{number.replace("+", "")}',
            'Viber': f'viber://chat?number={number.replace("+", "")}'
        }
        
        social_results = {}
        for platform, url in services.items():
            try:
                response = requests.head(url, timeout=5)
                if response.status_code in [200, 301, 302]:
                    social_results[platform] = {'exists': True, 'url': url}
            except:
                continue
        
        # Búsqueda en bases de datos públicas
        spam_databases = [
            f"https://www.spamcalls.net/en/number/{number}",
            f"https://who-called.co.uk/Number/{number}"
        ]
        
        reputation_results = []
        for url in spam_databases:
            try:
                response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if response.status_code == 200:
                    reputation_results.append({
                        'source': url,
                        'found': True,
                        'url': url
                    })
            except:
                continue
        
        return {
            **basic_info,
            'social_media': social_results,
            'reputation': reputation_results
        }
        
    except Exception as e:
        return {
            'valid': False,
            'message': str(e)
        }

def check_url(url, username):
    try:
        response = requests.get(url.replace('USERNAME', username), 
                              headers={'User-Agent': 'Mozilla/5.0'},
                              timeout=5)
        return {'exists': response.status_code == 200, 'url': url.replace('USERNAME', username)}
    except:
        return {'exists': False, 'url': url.replace('USERNAME', username)}

def check_social_media(username):
    platforms = {
        'GitHub': f'https://github.com/{username}',
        'Twitter': f'https://twitter.com/{username}',
        'Instagram': f'https://www.instagram.com/{username}',
        'Facebook': f'https://www.facebook.com/{username}',
        'LinkedIn': f'https://www.linkedin.com/in/{username}',
        'YouTube': f'https://www.youtube.com/@{username}',
        'TikTok': f'https://www.tiktok.com/@{username}',
        'Pinterest': f'https://pinterest.com/{username}'
    }
    
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_platform = {executor.submit(check_url, url, username): platform 
                            for platform, url in platforms.items()}
        
        for future in concurrent.futures.as_completed(future_to_platform):
            platform = future_to_platform[future]
            try:
                result = future.result()
                if result['exists']:
                    results[platform] = result
            except Exception:
                continue
    
    return results

def check_crypto_platforms(username):
    platforms = {
        'Binance': f'https://p2p.binance.com/en/advertiserDetail?nick={username}',
        'LocalBitcoins': f'https://localbitcoins.com/accounts/profile/{username}/',
        'Kraken': f'https://www.kraken.com/u/{username}',
        'Coinbase': f'https://www.coinbase.com/api/v2/users/{username}'
    }
    
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_platform = {executor.submit(check_url, url, username): platform 
                            for platform, url in platforms.items()}
        
        for future in concurrent.futures.as_completed(future_to_platform):
            platform = future_to_platform[future]
            try:
                result = future.result()
                if result['exists']:
                    results[platform] = result
            except Exception:
                continue
    
    return results

def check_gaming_platforms(username):
    platforms = {
        'Steam': f'https://steamcommunity.com/id/{username}',
        'Xbox': f'https://account.xbox.com/profile?gamertag={username}',
        'PSN': f'https://my.playstation.com/profile/{username}',
        'Twitch': f'https://www.twitch.tv/{username}'
    }
    
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_platform = {executor.submit(check_url, url, username): platform 
                            for platform, url in platforms.items()}
        
        for future in concurrent.futures.as_completed(future_to_platform):
            platform = future_to_platform[future]
            try:
                result = future.result()
                if result['exists']:
                    results[platform] = result
            except Exception:
                continue
    
    return results

def check_tech_platforms(username):
    platforms = {
        'Stack Overflow': f'https://stackoverflow.com/users/{username}',
        'GitHub': f'https://github.com/{username}',
        'GitLab': f'https://gitlab.com/{username}',
        'Docker Hub': f'https://hub.docker.com/u/{username}'
    }
    
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_platform = {executor.submit(check_url, url, username): platform 
                            for platform, url in platforms.items()}
        
        for future in concurrent.futures.as_completed(future_to_platform):
            platform = future_to_platform[future]
            try:
                result = future.result()
                if result['exists']:
                    results[platform] = result
            except Exception:
                continue
    
    return results

def get_ip_info(ip):
    try:
        response = requests.get(f'https://ipapi.co/{ip}/json/')
        if response.status_code == 200:
            data = response.json()
            return {
                'ip': ip,
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', 'Unknown'),
                'country': data.get('country_name', 'Unknown'),
                'org': data.get('org', 'Unknown')
            }
    except:
        return {}

def search_telegram_public(query):
    """
    Busca información pública y legal en Telegram
    """
    try:
        results = {
            'channels': [],
            'bots': [],
            'stickers': []
        }
        
        # Búsqueda en el directorio público de Telegram
        search_url = f"https://t.me/s/{quote_plus(query)}"
        response = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Verificar si es un canal público
            channel_info = soup.find('div', class_='tgme_channel_info')
            if channel_info:
                title = channel_info.find('div', class_='tgme_channel_info_header_title')
                description = channel_info.find('div', class_='tgme_channel_info_description')
                members = channel_info.find('div', class_='tgme_channel_info_counter')
                
                if title:
                    results['channels'].append({
                        'title': title.text.strip(),
                        'description': description.text.strip() if description else '',
                        'members': members.text.strip() if members else 'N/A',
                        'url': search_url,
                        'type': 'channel'
                    })
        
        # Búsqueda de bots públicos
        bot_url = f"https://t.me/{quote_plus(query)}bot"
        response = requests.get(bot_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            bot_info = soup.find('div', class_='tgme_page_description')
            
            if bot_info:
                results['bots'].append({
                    'name': query + 'bot',
                    'description': bot_info.text.strip(),
                    'url': bot_url,
                    'type': 'bot'
                })
        
        # Búsqueda de stickers públicos
        sticker_url = f"https://t.me/addstickers/{quote_plus(query)}"
        response = requests.get(sticker_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            sticker_info = soup.find('div', class_='tgme_page_description')
            
            if sticker_info:
                results['stickers'].append({
                    'name': query,
                    'url': sticker_url,
                    'type': 'sticker_pack'
                })
        
        return results
    except Exception as e:
        return {'error': str(e)}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/check', methods=['POST'])
def check():
    query = request.form.get('email')
    if not query:
        return jsonify({'error': 'Email, usuario o teléfono requerido'})
    
    save_search(query)
    
    # Detectar tipo de búsqueda
    is_email = '@' in query
    is_phone = bool(re.match(r'^\+?[\d\s-]{8,}$', query))
    
    if is_phone:
        # Limpiar el número de teléfono
        clean_number = re.sub(r'[\s-]', '', query)
        if not clean_number.startswith('+'):
            clean_number = '+' + clean_number
        
        phone_info = check_phone_number(clean_number)
        return jsonify({
            'type': 'phone',
            'phone_info': phone_info
        })
    else:
        # Búsqueda normal por email o usuario
        results = {
            'type': 'email' if is_email else 'username',
            'social_media': check_social_media(query),
            'crypto_platforms': check_crypto_platforms(query),
            'gaming_platforms': check_gaming_platforms(query),
            'tech_platforms': check_tech_platforms(query),
            'ip_info': get_ip_info(request.remote_addr)
        }
        
        return jsonify(results)

@app.route('/search_telegram', methods=['POST'])
def search_telegram():
    query = request.form.get('query')
    if not query:
        return jsonify({'error': 'Query requerido'})
    
    results = search_telegram_public(query)
    return jsonify(results)

@app.route('/history')
def view_history():
    conn = sqlite3.connect('searches.db')
    c = conn.cursor()
    c.execute('SELECT * FROM searches ORDER BY timestamp DESC LIMIT 10')
    searches = c.fetchall()
    conn.close()
    return jsonify(searches)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)

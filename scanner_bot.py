import ccxt
import pandas as pd
import time
import requests
import json
import os
import threading
from datetime import datetime, timedelta
import urllib3
import mplfinance as mpf
import matplotlib.pyplot as plt
import numpy as np

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import pandas_ta as ta

# --- НАСТРОЙКИ ---
# ⚠️ ПРОВЕРЬ, ЧТО ТОКЕН ПОЛНЫЙ!
TELEGRAM_BOT_TOKEN = "AAHcPoLYqKscWaTd5MjZGUSNgOwn17lntuM" 
TELEGRAM_CHAT_ID = "8969022054" # Убедись, что это твой верный Chat ID

TIMEFRAMES = ['1h', '4h', '1d']
RSI_PERIOD = 14
SMA_PERIOD = 14
VOLUME_MIN = 5_000_000  # Изменил на 5 млн, как ты просил ранее
SIGNAL_COOLDOWN_HOURS = 24

# Настройки для уровней
MIN_TOUCHES = 2
TOUCH_TOLERANCE = 0.005

SIGNAL_HISTORY_FILE = "signal_history.json"

# --- ИСТОРИЯ СИГНАЛОВ ---
def load_signal_history():
    try:
        if os.path.exists(SIGNAL_HISTORY_FILE):
            with open(SIGNAL_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_signal_history(history):
    try:
        with open(SIGNAL_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")

def can_send_signal(symbol, timeframe):
    history = load_signal_history()
    key = f"{symbol}_{timeframe}"
    current_time = datetime.now()
    
    if key in history:
        last_signal_time = datetime.fromisoformat(history[key])
        time_diff = current_time - last_signal_time
        if time_diff < timedelta(hours=SIGNAL_COOLDOWN_HOURS):
            return False
    return True

def record_signal(symbol, timeframe):
    history = load_signal_history()
    key = f"{symbol}_{timeframe}"
    history[key] = datetime.now().isoformat()
    save_signal_history(history)

# --- TELEGRAM ---
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, json=payload, verify=False, timeout=30)
        return True
    except Exception as e:
        print(f"❌ Telegram ошибка: {e}")
        return False

def send_telegram_with_chart(message, chart_file):
    """Отправляет сообщение с графиком, если он есть"""
    if chart_file and os.path.exists(chart_file):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        try:
            with open(chart_file, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': message,
                    'parse_mode': 'HTML'
                }
                requests.post(url, data=data, files=files, verify=False, timeout=30)
            os.remove(chart_file) # Удаляем файл после отправки
            return True
        except Exception as e:
            print(f"❌ Ошибка отправки графика: {e}")
            return False
    else:
        return send_telegram_message(message)

# --- ПОИСК УРОВНЕЙ (ТОЛЬКО НЕПРОБИТЫЕ) ---
def find_support_resistance_levels(df, current_price, min_touches=MIN_TOUCHES, tolerance=TOUCH_TOLERANCE):
    levels = []
    highs = df['high'].values
    lows = df['low'].values
    
    # Сопротивление (выше текущей цены)
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            level_price = highs[i]
            if level_price <= current_price:
                continue
            touches = sum(1 for j in range(len(highs)) if abs(highs[j] - level_price) / level_price <= tolerance)
            if touches >= min_touches:
                levels.append({'price': level_price, 'touches': touches, 'type': 'resistance'})
    
    # Поддержка (ниже текущей цены)
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            level_price = lows[i]
            if level_price >= current_price:
                continue
            touches = sum(1 for j in range(len(lows)) if abs(lows[j] - level_price) / level_price <= tolerance)
            if touches >= min_touches:
                levels.append({'price': level_price, 'touches': touches, 'type': 'support'})
    
    # Удаляем дубликаты
    unique_levels = []
    for level in levels:
        if not any(abs(level['price'] - u['price']) / u['price'] <= tolerance * 2 for u in unique_levels):
            unique_levels.append(level)
    
    unique_levels.sort(key=lambda x: x['touches'], reverse=True)
    return unique_levels[:5]

# --- ГЕНЕРАЦИЯ ГРАФИКА С УРОВНЯМИ ---
def create_chart_with_levels(bars, symbol, timeframe):
    try:
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        current_price = df['close'].iloc[-1]
        levels = find_support_resistance_levels(df, current_price)
        
        mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', edge='inherit', wick='inherit')
        style = mpf.make_mpf_style(
            marketcolors=mc, figcolor='#131722', facecolor='#131722',
            gridcolor='#2a2e39', gridstyle='-', y_on_right=True
        )
        
        # Создаем addplot для уровней (правильный способ для mplfinance)
        addplots = []
        for level in levels:
            price = level['price']
            touches = level['touches']
            color = 'red' if level['type'] == 'resistance' else 'lime'
            linewidth = 2.5 if touches >= 3 else 1.5
            
            hline_data = pd.DataFrame({'price': [price] * len(df)}, index=df.index)
            addplots.append(mpf.make_addplot(hline_data['price'], color=color, linewidth=linewidth, linestyle='-', secondary_y=False))
        
        # Линия текущей цены
        current_price_data = pd.DataFrame({'price': [current_price] * len(df)}, index=df.index)
        addplots.append(mpf.make_addplot(current_price_data['price'], color='gold', linewidth=1.5, linestyle='--', secondary_y=False))
        
        fig, ax = plt.subplots(figsize=(12, 7), facecolor='#131722')
        mpf.plot(df, type='candle', style=style, ax=ax, volume=False, addplot=addplots if addplots else None)
        
        ax.set_title(f'{symbol} | {timeframe} | Уровни S/R', color='white', fontsize=14, pad=15)
        ax.tick_params(colors='white')
        
        # Легенда с уровнями
        if levels:
            legend_text = "Уровни:\n"
            for level in levels[:3]:
                level_type = "R" if level['type'] == 'resistance' else "S"
                legend_text += f"{level_type}: {level['price']:.6f} ({level['touches']}x)\n"
            ax.text(0.02, 0.98, legend_text, transform=ax.transAxes, fontsize=9, color='white',
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='#131722', edgecolor='white', alpha=0.8))
        
        filename = f'chart_{symbol.replace("/", "")}_{timeframe}.png'
        plt.savefig(filename, dpi=100, bbox_inches='tight', facecolor='#131722')
        plt.close()
        
        return filename
    except Exception as e:
        print(f"❌ Ошибка создания графика {symbol}: {e}")
        return None

# --- СЛУШАТЕЛЬ КОМАНД ---
def telegram_commands_listener():
    print("🎧 Запуск слушателя команд Telegram...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {'offset': offset, 'timeout': 1}
            response = requests.get(url, params=params, verify=False, timeout=5)
            updates = response.json()
            
            if updates.get('ok') and updates.get('result'):
                for update in updates['result']:
                    offset = update['update_id'] + 1
                    if 'message' in update:
                        chat_id = update['message']['chat']['id']
                        text = update['message'].get('text', '').strip().lower()
                        if text == '/start' or text == '/status':
                            uptime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            msg = (
                                f"✅ <b>БОТ РАБОТАЕТ!</b>\n\n"
                                f"🟢 <b>Статус:</b> Активен\n"
                                f"⏰ <b>Время:</b> {uptime}\n"
                                f"📊 <b>Таймфреймы:</b> {', '.join(TIMEFRAMES)}\n"
                                f"💰 <b>Мин. объем:</b> ${VOLUME_MIN:,}\n"
                                f"🎯 <b>Стратегия:</b> SL 3.5% | TP1 3% | TP2 7%\n"
                                f"📏 <b>Уровни S/R:</b> {MIN_TOUCHES}+ касаний (непробитые)\n"
                                f"⏰ <b>Кулдаун:</b> {SIGNAL_COOLDOWN_HOURS} часов\n\n"
                                f"💡 <i>Бот присылает сигналы с графиками и уровнями!</i>"
                            )
                            send_telegram_message(msg)
        except Exception:
            pass
        time.sleep(1)

# --- БИРЖА ---
def init_exchange():
    try:
        exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
        print("✅ Биржа инициализирована")
        return exchange
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

# --- ПРОВЕРКА СИГНАЛА ---
def check_signal(exchange, symbol, timeframe, volume_24h):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        if len(bars) < 50:
            return False, "", None
            
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['rsi'] = ta.rsi(df['close'], length=RSI_PERIOD)
        df['sma_of_rsi'] = ta.sma(df['rsi'], length=SMA_PERIOD)
        df = df.dropna().reset_index(drop=True)
        
        if len(df) < 2:
            return False, "", None
        
        prev_rsi = df['rsi'].iloc[-2]
        curr_rsi = df['rsi'].iloc[-1]
        prev_sma = df['sma_of_rsi'].iloc[-2]
        curr_sma = df['sma_of_rsi'].iloc[-1]
        
        crossover = (prev_rsi <= prev_sma) and (curr_rsi > curr_sma)
        below_40 = (curr_rsi < 40) and (curr_sma < 40)
        
        if crossover and below_40:
            if not can_send_signal(symbol, timeframe):
                return False, "", None
            
            record_signal(symbol, timeframe)
            current_price = df['close'].iloc[-1]
            coin_name = symbol.replace('/USDT', '')
            
            # Создаем график с уровнями
            chart_file = create_chart_with_levels(bars, symbol, timeframe)
            
            stop_loss_price = current_price * 0.965
            tp1_price = current_price * 1.03
            tp2_price = current_price * 1.07
            
            message = (
                f"🚨 <b>СИГНАЛ НА ПОКУПКУ!</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Монета:</b> {coin_name}\n"
                f"🔗 <b>Пара:</b> {symbol.replace('/', '')}\n"
                f"💲 <b>Цена входа:</b> ${current_price:.8f}\n"
                f"📊 <b>Объем 24ч:</b> ${volume_24h:,.0f}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>ЦЕЛЬ 1 (+3%):</b> ${tp1_price:.8f} <i>(Забрать 50%)</i>\n"
                f"🎯 <b>ЦЕЛЬ 2 (+7%):</b> ${tp2_price:.8f} <i>(Забрать остаток)</i>\n"
                f"🛑 <b>СТОП-ЛОСС (-3.5%):</b> ${stop_loss_price:.8f}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💡 <i>Совет: Забери половину на Цели 1 и переведи стоп в безубыток!</i>\n"
                f"⏱ <b>Таймфрейм:</b> {timeframe}\n"
                f"📈 <b>RSI:</b> {curr_rsi:.2f} | <b>SMA:</b> {curr_sma:.2f}\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🔄 #{coin_name}"
            )
            return True, message, chart_file
        
        return False, "", None
    except Exception as e:
        return False, "", None

# --- ГЛАВНАЯ ---
def main():
    print("="*60)
    print("🚀 ЗАПУСК СКАНЕРА СИГНАЛОВ С УРОВНЯМИ S/R")
    print("="*60)
    print(f"⏱ Таймфреймы: {TIMEFRAMES}")
    print(f"💰 Мин. объем: ${VOLUME_MIN:,}")
    print(f"📏 Мин. касаний для уровня: {MIN_TOUCHES}")
    print(f"⏰ Кулдаун: {SIGNAL_COOLDOWN_HOURS} часов")
    print("="*60)
    
    exchange = init_exchange()
    if exchange is None:
        return
    
    send_telegram_message(
        f"🤖 <b>Сканер с уровнями S/R запущен!</b>\n\n"
        f"⏱ Таймфреймы: {', '.join(TIMEFRAMES)}\n"
        f"💰 Мин. объем: ${VOLUME_MIN:,}\n"
        f"🎯 Стратегия: SL 3.5% | TP1 3% | TP2 7%\n"
        f"📏 Уровни: {MIN_TOUCHES}+ касаний (непробитые)\n"
        f"⏰ Кулдаун: {SIGNAL_COOLDOWN_HOURS} часов\n\n"
        f"💡 Напиши <b>/start</b> чтобы проверить статус бота"
    )
    
    listener_thread = threading.Thread(target=telegram_commands_listener, daemon=True)
    listener_thread.start()
    print("✅ Слушатель команд запущен в отдельном потоке")
    
    print("\n📊 Загружаем список монет...")
    tickers = exchange.fetch_tickers()
    
    qualified_symbols = []
    for symbol, ticker in tickers.items():
        if symbol.endswith('/USDT'):
            volume_24h = float(ticker.get('quoteVolume', 0) or 0)
            if volume_24h >= VOLUME_MIN:
                qualified_symbols.append((symbol, volume_24h))
    
    print(f"✅ Найдено {len(qualified_symbols)} монет с объёмом > ${VOLUME_MIN:,}")
    
    cycle = 1
    while True:
        try:
            print(f"\n{'='*60}")
            print(f"🔄 ЦИКЛ #{cycle} | {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*60}")
            
            signals_found = 0
            
            for timeframe in TIMEFRAMES:
                print(f"\n⏰ Таймфрейм: {timeframe}")
                for i, (symbol, volume) in enumerate(qualified_symbols, 1):
                    if i % 50 == 0:
                        print(f"📈 [{i}/{len(qualified_symbols)}] {symbol}")
                    
                    signal_found, message, chart_file = check_signal(exchange, symbol, timeframe, volume)
                    if signal_found:
                        print(f"✅ СИГНАЛ! {symbol} {timeframe}")
                        send_telegram_with_chart(message, chart_file)
                        signals_found += 1
            
            print(f"\n🎯 Цикл #{cycle} завершён. Найдено сигналов: {signals_found}")
            
            if cycle % 10 == 0:
                print("\n🔄 Обновляем список монет...")
                tickers = exchange.fetch_tickers()
                qualified_symbols = []
                for symbol, ticker in tickers.items():
                    if symbol.endswith('/USDT'):
                        volume_24h = float(ticker.get('quoteVolume', 0) or 0)
                        if volume_24h >= VOLUME_MIN:
                            qualified_symbols.append((symbol, volume_24h))
                print(f"✅ Обновлено: {len(qualified_symbols)} монет")
            
            cycle += 1
            print("\n⏳ Пауза 10 секунд...")
            time.sleep(10)
            
        except KeyboardInterrupt:
            print("\n👋 Остановлено")
            send_telegram_message("👋 Сканер остановлен")
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Остановлено")

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
TELEGRAM_BOT_TOKEN = "AAHcPoLYqKscWaTd5MjZGUSNgOwn17lntuM"
TELEGRAM_CHAT_ID = "8969022054"

TIMEFRAMES = ['1h', '4h', '1d']
RSI_PERIOD = 14
SMA_PERIOD = 14
VOLUME_MIN = 5_000_000
SIGNAL_COOLDOWN_HOURS = 24
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
        response = requests.post(url, json=payload, verify=False, timeout=30)
        return True
    except Exception as e:
        print(f"❌ Telegram ошибка: {e}")
        return False

def send_telegram_with_chart(message, chart_file):
    """Отправляет сообщение с графиком"""
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
            os.remove(chart_file)
            return True
        except Exception as e:
            print(f"❌ Ошибка отправки графика: {e}")
            return False
    else:
        return send_telegram_message(message)

# --- ПОИСК УРОВНЕЙ (ТОЛЬКО НЕПРОБИТЫЕ) ---
def find_support_resistance_levels(df, current_price, min_touches=MIN_TOUCHES, tolerance=TOUCH_TOLERANCE):
    """Находит только НЕПРОБИТЫЕ уровни поддержки/сопротивления"""
    levels = []
    
    highs = df['high'].values
    lows = df['low'].values
    
    # Ищем локальные максимумы (сопротивление) — только ВЫШЕ текущей цены
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            level_price = highs[i]
            
            # 🔧 ФИЛЬТР: пропускаем пробитые уровни
            if level_price <= current_price:
                continue
            
            touches = 0
            for j in range(len(highs)):
                if abs(highs[j] - level_price) / level_price <= tolerance:
                    touches += 1
            
            if touches >= min_touches:
                levels.append({
                    'price': level_price,
                    'touches': touches,
                    'type': 'resistance'
                })
    
    # Ищем локальные минимумы (поддержка) — только НИЖЕ текущей цены
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            level_price = lows[i]
            
            # 🔧 ФИЛЬТР: пропускаем пробитые уровни
            if level_price >= current_price:
                continue
            
            touches = 0
            for j in range(len(lows)):
                if abs(lows[j] - level_price) / level_price <= tolerance:
                    touches += 1
            
            if touches >= min_touches:
                levels.append({
                    'price': level_price,
                    'touches': touches,
                    'type': 'support'
                })
    
    # Удаляем дубликаты
    unique_levels = []
    for level in levels:
        is_duplicate = False
        for unique in unique_levels:
            if abs(level['price'] - unique['price']) / unique['price'] <= tolerance * 2:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_levels.append(level)
    
    unique_levels.sort(key=lambda x: x['touches'], reverse=True)
    
    return unique_levels[:5]

# --- СОЗДАНИЕ ГРАФИКА С УРОВНЯМИ ---
def create_chart_with_levels(bars, symbol, timeframe, levels, current_price):
    """Создаёт график с нарисованными уровнями"""
    try:
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        mc = mpf.make_marketcolors(
            up='#26a69a',
            down='#ef5350',
            edge='inherit',
            wick='inherit'
        )
        
        style = mpf.make_mpf_style(
            marketcolors=mc,
            figcolor='#131722',
            facecolor='#131722',
            gridcolor='#2a2e39',
            gridstyle='-',
            y_on_right=True
        )
        
        # Создаём фигуру и оси вручную
        fig = plt.figure(figsize=(12, 7), facecolor='#131722')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#131722')
        
        # Рисуем свечи через mplfinance
        mpf.plot(df, type='candle', style=style, ax=ax, volume=False)
        
        # Устанавливаем заголовок
        ax.set_title(f'{symbol} | {timeframe} | Уровни S/R', color='white', fontsize=14, pad=15)
        
        # Рисуем уровни
        for level in levels:
            price = level['price']
            touches = level['touches']
            level_type = level['type']
            
            color = '#FF4444' if level_type == 'resistance' else '#00FF88'
            linewidth = 2.5 if touches >= 3 else 1.5
            
            # Рисуем горизонтальную линию
            ax.axhline(y=price, color=color, linewidth=linewidth, linestyle='-', alpha=0.8, zorder=5)
            
            # Добавляем текст с ценой и количеством касаний
            ax.text(
                df.index[-1],
                price,
                f'  {price:.6f} ({touches}x)',
                color=color,
                fontsize=10,
                fontweight='bold',
                va='center',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#131722', edgecolor=color, alpha=0.9),
                zorder=6
            )
        
        # Рисуем текущую цену
        ax.axhline(y=current_price, color='#FFD700', linewidth=2, linestyle='--', alpha=0.9, zorder=5)
        ax.text(
            df.index[-1],
            current_price,
            f'  Текущая: {current_price:.6f}',
            color='#FFD700',
            fontsize=10,
            fontweight='bold',
            va='center',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#131722', edgecolor='#FFD700', alpha=0.9),
            zorder=6
        )
        
        # Настройка осей
        ax.tick_params(colors='white', labelsize=9)
        ax.spines['bottom'].set_color('#2a2e39')
        ax.spines['top'].set_color('#2a2e39')
        ax.spines['left'].set_color('#2a2e39')
        ax.spines['right'].set_color('#2a2e39')
        ax.grid(color='#2a2e39', alpha=0.3, zorder=0)
        
        plt.tight_layout()
        
        filename = f'chart_{symbol.replace("/", "")}_{timeframe}.png'
        plt.savefig(filename, dpi=120, bbox_inches='tight', facecolor='#131722', edgecolor='none')
        plt.close()
        
        print(f"✅ График сохранён: {filename} (уровней: {len(levels)})")
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка создания графика: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- ПРОВЕРКА СИГНАЛА С УРОВНЯМИ ---
def check_signal_with_levels(exchange, symbol, timeframe, volume_24h):
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
            
            # Находим уровни (только непробитые)
            levels = find_support_resistance_levels(df, current_price)
            
            # Создаём график с уровнями
            chart_file = create_chart_with_levels(bars, symbol, timeframe, levels, current_price)
            
            stop_loss_price = current_price * 0.965
            tp1_price = current_price * 1.03
            tp2_price = current_price * 1.07
            
            # Текст об уровнях
            levels_text = ""
            if levels:
                levels_text = "\n <b>Уровни S/R (непробитые):</b>\n"
                for i, level in enumerate(levels[:3], 1):
                    level_type = "🔴 Сопротивление" if level['type'] == 'resistance' else "🟢 Поддержка"
                    levels_text += f"  {i}. {level_type}: ${level['price']:.6f} ({level['touches']} касаний)\n"
            
            message = (
                f"🚨 <b>СИГНАЛ НА ПОКУПКУ!</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Монета:</b> {coin_name}\n"
                f" <b>Пара:</b> {symbol.replace('/', '')}\n"
                f"💲 <b>Цена входа:</b> ${current_price:.8f}\n"
                f"📊 <b>Объем 24ч:</b> ${volume_24h:,.0f}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>ЦЕЛЬ 1 (+3%):</b> ${tp1_price:.8f} <i>(Забрать 50%)</i>\n"
                f" <b>ЦЕЛЬ 2 (+7%):</b> ${tp2_price:.8f} <i>(Забрать остаток)</i>\n"
                f"🛑 <b>СТОП-ЛОСС (-3.5%):</b> ${stop_loss_price:.8f}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{levels_text}"
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
                                f"📏 <b>Уровни S/R:</b> {MIN_TOUCHES}+ касаний (только непробитые)\n"
                                f" <b>Кулдаун:</b> {SIGNAL_COOLDOWN_HOURS} часов\n\n"
                                f"💡 <i>Бот рисует уровни на графике!</i>"
                            )
                            send_telegram_message(msg)
                            print(f"📨 Отправлен статус по команде {text}")
                            
        except Exception as e:
            pass
        
        time.sleep(1)

# --- БИРЖА ---
def init_exchange():
    try:
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        print("✅ Биржа инициализирована")
        return exchange
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

# --- ГЛАВНАЯ ---
def main():
    print("="*60)
    print("🚀 ЗАПУСК СКАНЕРА С УРОВНЯМИ S/R")
    print("="*60)
    print(f"⏱ Таймфреймы: {TIMEFRAMES}")
    print(f"💰 Мин. объем: ${VOLUME_MIN:,}")
    print(f"📏 Мин. касаний для уровня: {MIN_TOUCHES}")
    print(f" Кулдаун: {SIGNAL_COOLDOWN_HOURS} часов")
    print("="*60)
    
    exchange = init_exchange()
    if exchange is None:
        return
    
    send_telegram_message(
        f"🤖 <b>Сканер с уровнями S/R запущен!</b>\n\n"
        f"⏱ Таймфреймы: {', '.join(TIMEFRAMES)}\n"
        f"💰 Мин. объем: ${VOLUME_MIN:,}\n"
        f"🎯 Стратегия: SL 3.5% | TP1 3% | TP2 7%\n"
        f"📏 Уровни: {MIN_TOUCHES}+ касаний (только непробитые)\n"
        f"⏰ Кулдаун: {SIGNAL_COOLDOWN_HOURS} часов\n\n"
        f"💡 Напиши <b>/start</b> чтобы проверить статус бота"
    )
    
    listener_thread = threading.Thread(target=telegram_commands_listener, daemon=True)
    listener_thread.start()
    print("✅ Слушатель команд запущен")
    
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
                print(f"\n Таймфрейм: {timeframe}")
                
                for i, (symbol, volume) in enumerate(qualified_symbols, 1):
                    if i % 50 == 0:
                        print(f"📈 [{i}/{len(qualified_symbols)}] {symbol}")
                    
                    signal_found, message, chart_file = check_signal_with_levels(exchange, symbol, timeframe, volume)
                    if signal_found:
                        print(f"✅ СИГНАЛ! {symbol} {timeframe}")
                        send_telegram_with_chart(message, chart_file)
                        signals_found += 1
            
            print(f"\n🎯 Цикл #{cycle} завершён. Найдено сигналов: {signals_found}")
            
            if cycle % 10 == 0:
                print("\n Обновляем список монет...")
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
            print("\n Остановлено")
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

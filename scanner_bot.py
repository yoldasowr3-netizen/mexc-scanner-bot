import ccxt
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import urllib3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as patches
import os
import traceback

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = "8617230812:AAHoTf6dN0tRTxLCIgFvFVqP73thALh4M7s"
MIN_VOLUME = 5_000_000
CHART_CANDLES = 50
MIN_TOUCHES = 2
TOUCH_TOLERANCE = 0.005

def get_exchanges():
    return {
        'Binance': ccxt.binance({'enableRateLimit': True, 'timeout': 30000}),
        'Bybit': ccxt.bybit({'enableRateLimit': True, 'timeout': 30000}),
        'Bitget': ccxt.bitget({'enableRateLimit': True, 'timeout': 30000}),
        'BingX': ccxt.bingx({'enableRateLimit': True, 'timeout': 30000}),
        'MEXC': ccxt.mexc({
            'enableRateLimit': True, 
            'timeout': 30000,
            'options': {'defaultType': 'spot'}
        })
    }

# --- ПОИСК УРОВНЕЙ ---
def find_support_resistance_levels(df, current_price, min_touches=MIN_TOUCHES, tolerance=TOUCH_TOLERANCE):
    levels = []
    highs = df['high'].values
    lows = df['low'].values
    
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            level_price = highs[i]
            if level_price <= current_price:
                continue
            touches = sum(1 for j in range(len(highs)) if abs(highs[j] - level_price) / level_price <= tolerance)
            if touches >= min_touches:
                levels.append({'price': level_price, 'touches': touches, 'type': 'resistance'})
    
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            level_price = lows[i]
            if level_price >= current_price:
                continue
            touches = sum(1 for j in range(len(lows)) if abs(lows[j] - level_price) / level_price <= tolerance)
            if touches >= min_touches:
                levels.append({'price': level_price, 'touches': touches, 'type': 'support'})
    
    unique_levels = []
    for level in levels:
        if not any(abs(level['price'] - u['price']) / u['price'] <= tolerance * 2 for u in unique_levels):
            unique_levels.append(level)
    
    unique_levels.sort(key=lambda x: x['touches'], reverse=True)
    return unique_levels[:5]

# --- РИСОВАНИЕ СВЕЧЕЙ НА MATPLOTLIB ---
def draw_candles(ax, df, color_up='#26a69a', color_down='#ef5350'):
    """Рисует японские свечи на matplotlib"""
    for i, (timestamp, row) in enumerate(df.iterrows()):
        open_price = row['open']
        close_price = row['close']
        high_price = row['high']
        low_price = row['low']
        
        # Фитиль (линия от low до high)
        ax.plot([timestamp, timestamp], [low_price, high_price], 
                color=color_up if close_price >= open_price else color_down, 
                linewidth=0.8)
        
        # Тело свечи (прямоугольник)
        body_bottom = min(open_price, close_price)
        body_height = abs(close_price - open_price)
        if body_height == 0:
            body_height = high_price * 0.0001  # минимальная высота для доджи
        
        rect = patches.Rectangle(
            (timestamp, body_bottom), 
            0.0008,  # ширина свечи (в днях)
            body_height,
            facecolor=color_up if close_price >= open_price else color_down,
            edgecolor=color_up if close_price >= open_price else color_down,
            linewidth=0.5
        )
        ax.add_patch(rect)

# --- ГЕНЕРАЦИЯ ГРАФИКА (ЧИСТЫЙ MATPLOTLIB) ---
def create_chart(symbol, chart_exchanges):
    try:
        print(f"\n🎨 Создаю график для {symbol}...")
        
        ohlcv_1h = None
        ohlcv_4h = None
        
        for ex_name in ['Binance', 'Bybit', 'Bitget', 'BingX', 'MEXC']:
            if ex_name in chart_exchanges and ohlcv_1h is None:
                try:
                    ohlcv_1h = chart_exchanges[ex_name].fetch_ohlcv(symbol, timeframe='1h', limit=CHART_CANDLES)
                    if ohlcv_1h and len(ohlcv_1h) >= 10:
                        print(f"  ✅ 1H данные с {ex_name}: {len(ohlcv_1h)} свечей")
                except Exception as e:
                    ohlcv_1h = None
        
        for ex_name in ['Binance', 'Bybit', 'Bitget', 'BingX', 'MEXC']:
            if ex_name in chart_exchanges and ohlcv_4h is None:
                try:
                    ohlcv_4h = chart_exchanges[ex_name].fetch_ohlcv(symbol, timeframe='4h', limit=CHART_CANDLES)
                    if ohlcv_4h and len(ohlcv_4h) >= 10:
                        print(f"  ✅ 4H данные с {ex_name}: {len(ohlcv_4h)} свечей")
                except Exception as e:
                    ohlcv_4h = None
        
        if ohlcv_1h is None or ohlcv_4h is None:
            print(f"  ❌ Нет данных для {symbol}")
            return None, 0
        
        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
        df_1h.set_index('timestamp', inplace=True)
        
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
        df_4h.set_index('timestamp', inplace=True)
        
        current_price = df_1h['close'].iloc[-1]
        
        levels_1h = find_support_resistance_levels(df_1h, current_price)
        levels_4h = find_support_resistance_levels(df_4h, current_price)
        
        max_touches = 0
        if levels_1h:
            max_touches = max(max_touches, max(level['touches'] for level in levels_1h))
        if levels_4h:
            max_touches = max(max_touches, max(level['touches'] for level in levels_4h))
        
        print(f"  📊 Уровни: 1H={len(levels_1h)}, 4H={len(levels_4h)}, Макс. касаний: {max_touches}")
        
        # Создаём фигуру
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), facecolor='#131722')
        fig.patch.set_facecolor('#131722')
        
        # === 1H ГРАФИК ===
        ax1.set_facecolor('#131722')
        ax1.set_title(f'{symbol} - 1H | Уровни S/R', color='white', fontsize=13, pad=15)
        draw_candles(ax1, df_1h)
        
        # Уровни на 1H
        for level in levels_1h:
            price = level['price']
            touches = level['touches']
            color = '#FF4444' if level['type'] == 'resistance' else '#00FF88'
            linewidth = 2.5 if touches >= 3 else 1.5
            ax1.axhline(y=price, color=color, linewidth=linewidth, alpha=0.85, linestyle='-')
            ax1.text(df_1h.index[-1], price, f'  {price:.6f} ({touches} кас.)', 
                    color=color, fontsize=9, fontweight='bold',
                    bbox=dict(boxstyle='round', facecolor='#131722', edgecolor=color, alpha=0.9))
        
        # Текущая цена
        ax1.axhline(y=current_price, color='#FFD700', linewidth=1.5, linestyle='--', alpha=0.8)
        ax1.text(df_1h.index[-1], current_price, f'  Цена: {current_price:.6f}', 
                color='#FFD700', fontsize=9, fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='#131722', edgecolor='#FFD700', alpha=0.9))
        
        ax1.tick_params(colors='white', labelsize=8)
        ax1.grid(color='#2a2e39', alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # === 4H ГРАФИК ===
        ax2.set_facecolor('#131722')
        ax2.set_title(f'{symbol} - 4H | Уровни S/R', color='white', fontsize=13, pad=15)
        draw_candles(ax2, df_4h)
        
        # Уровни на 4H
        for level in levels_4h:
            price = level['price']
            touches = level['touches']
            color = '#FF4444' if level['type'] == 'resistance' else '#00FF88'
            linewidth = 2.5 if touches >= 3 else 1.5
            ax2.axhline(y=price, color=color, linewidth=linewidth, alpha=0.85, linestyle='-')
            ax2.text(df_4h.index[-1], price, f'  {price:.6f} ({touches} кас.)', 
                    color=color, fontsize=9, fontweight='bold',
                    bbox=dict(boxstyle='round', facecolor='#131722', edgecolor=color, alpha=0.9))
        
        # Текущая цена
        ax2.axhline(y=current_price, color='#FFD700', linewidth=1.5, linestyle='--', alpha=0.8)
        ax2.text(df_4h.index[-1], current_price, f'  Цена: {current_price:.6f}', 
                color='#FFD700', fontsize=9, fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='#131722', edgecolor='#FFD700', alpha=0.9))
        
        ax2.tick_params(colors='white', labelsize=8)
        ax2.grid(color='#2a2e39', alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        
        filename = f'chart_{symbol.replace("/", "")}.png'
        plt.savefig(filename, dpi=110, bbox_inches='tight', facecolor='#131722', edgecolor='none')
        plt.close()
        
        print(f"✅ График сохранён: {filename}")
        return filename, max_touches
        
    except Exception as e:
        print(f"❌ Ошибка создания графика {symbol}: {e}")
        traceback.print_exc()
        return None, 0

# --- СКАНИРОВАНИЕ ---
def scan_markets_task():
    exchanges = get_exchanges()
    all_coins = {}
    mexc_coins = set()
    
    print("🔄 Загрузка рынков...")
    for name, ex in exchanges.items():
        try:
            ex.load_markets()
            print(f"✅ {name} загружена")
        except Exception as e:
            print(f"⚠️ Ошибка {name}: {e}")
            del exchanges[name]

    print(f"\n🔍 Сканирую (мин. объем: ${MIN_VOLUME:,})...")
    for name, ex in exchanges.items():
        try:
            print(f"📊 Сканирую {name}...")
            tickers = ex.fetch_tickers()
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT'):
                    volume = float(ticker.get('quoteVolume', 0) or 0)
                    coin = symbol.replace('/USDT', '')
                    if volume >= MIN_VOLUME:
                        if coin not in all_coins:
                            all_coins[coin] = []
                        if name not in all_coins[coin]:
                            all_coins[coin].append(name)
                    if name == 'MEXC':
                        mexc_coins.add(coin)
        except Exception as e:
            print(f"❌ Ошибка {name}: {e}")
            continue

    final_coins = {}
    for coin, ex_list in all_coins.items():
        if coin in mexc_coins:
            final_coins[coin] = ex_list

    return sorted(final_coins.items(), key=lambda x: len(x[1]), reverse=True)

def get_scan_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Найти монеты", callback_data='scan')]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>СКАНЕР MEXC SPOT С УРОВНЯМИ S/R!</b>\n\n"
        "Бот ищет монеты с объемом > $5 млн.\n"
        "✅ Только те, что есть на <b>MEXC SPOT</b>\n"
        " График (1H + 4H) с точным числом касаний!\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=get_scan_keyboard(),
        parse_mode='HTML'
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    status_msg = await query.message.reply_text(" <b>Сканирую биржи...</b>\n\nЭто займёт 3-5 минут.", parse_mode='HTML')
    
    loop = asyncio.get_event_loop()
    sorted_coins = await loop.run_in_executor(None, scan_markets_task)
    await status_msg.delete()
    
    if not sorted_coins:
        await query.message.reply_text("❌ Монеты не найдены. Попробуй позже.", reply_markup=get_scan_keyboard())
        return
    
    total = len(sorted_coins)
    print(f"\n📊 Найдено {total} монет. Начинаю отправку...")
    
    chart_exchanges = {}
    for name in ['Binance', 'Bybit', 'Bitget', 'BingX', 'MEXC']:
        try:
            if name == 'Binance': chart_exchanges[name] = ccxt.binance({'enableRateLimit': True, 'timeout': 30000})
            elif name == 'Bybit': chart_exchanges[name] = ccxt.bybit({'enableRateLimit': True, 'timeout': 30000})
            elif name == 'Bitget': chart_exchanges[name] = ccxt.bitget({'enableRateLimit': True, 'timeout': 30000})
            elif name == 'BingX': chart_exchanges[name] = ccxt.bingx({'enableRateLimit': True, 'timeout': 30000})
            elif name == 'MEXC': chart_exchanges[name] = ccxt.mexc({'enableRateLimit': True, 'timeout': 30000, 'options': {'defaultType': 'spot'}})
            chart_exchanges[name].load_markets()
        except Exception as e:
            print(f"️ {name} не подключена: {e}")
    
    sent_count = 0
    no_chart_count = 0
    
    for i, (coin, ex_list) in enumerate(sorted_coins, 1):
        try:
            symbol = f"{coin}/USDT"
            ex_str = ', '.join(ex_list)
            
            chart_result = create_chart(symbol, chart_exchanges)
            
            if chart_result and chart_result[0]:
                chart_file, max_touches = chart_result
                
                caption = (
                    f"<b>{i}) {coin}USDT</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🏦 <b>Биржи:</b> {ex_str}\n"
                    f"📊 <b>График:</b> 1H + 4H с уровнями S/R\n"
                    f"📏 <b>Макс. касаний на уровне:</b> {max_touches} раз\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
                
                with open(chart_file, 'rb') as photo:
                    await query.message.reply_photo(photo=photo, caption=caption, parse_mode='HTML')
                os.remove(chart_file)
                sent_count += 1
                print(f"✅ [{i}/{total}] {coin} отправлен (касаний: {max_touches})")
            else:
                await query.message.reply_text(f"<b>{i}) {coin}USDT</b>\n️ <i>График не удалось построить</i>", parse_mode='HTML')
                no_chart_count += 1
            
            await asyncio.sleep(3)
            
        except Exception as e:
            print(f"❌ [{i}/{total}] {coin} ошибка: {e}")
            continue
    
    summary = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>СКАНИРОВАНИЕ ЗАВЕРШЕНО!</b>\n\n"
        f"📊 <b>Всего:</b> {total} монет\n"
        f"✅ <b>С графиками:</b> {sent_count}\n"
        f"️ <b>Без графиков:</b> {no_chart_count}\n"
        f"💰 <b>Фильтр:</b> объем > $5,000,000\n"
        f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await query.message.reply_text(summary, reply_markup=get_scan_keyboard(), parse_mode='HTML')
    print(f"\n✅ Готово! С графиками: {sent_count}")

def main():
    print("🚀 ЗАПУСК СКАНЕРА MEXC SPOT С УРОВНЯМИ S/R")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    print("✅ Бот готов. Жду команду /start в Telegram...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

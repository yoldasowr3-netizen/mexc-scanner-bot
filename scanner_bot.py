import ccxt
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import urllib3
import mplfinance as mpf
import pandas as pd
import matplotlib.pyplot as plt
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = "8969022054:AAFW624orWdf7zjc6ZzoSfjvRlP9PmZHAOE"
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

# --- ГЕНЕРАЦИЯ ГРАФИКА ---
def create_chart(symbol, chart_exchanges):
    try:
        ohlcv_1h = None
        ohlcv_4h = None
        
        for ex_name in ['Binance', 'Bybit', 'Bitget', 'BingX', 'MEXC']:
            if ex_name in chart_exchanges:
                try:
                    ohlcv_1h = chart_exchanges[ex_name].fetch_ohlcv(symbol, timeframe='1h', limit=CHART_CANDLES)
                    ohlcv_4h = chart_exchanges[ex_name].fetch_ohlcv(symbol, timeframe='4h', limit=CHART_CANDLES)
                    if ohlcv_1h and ohlcv_4h and len(ohlcv_1h) >= 10 and len(ohlcv_4h) >= 10:
                        print(f"  📊 Данные взяты с {ex_name}")
                        break
                except:
                    ohlcv_1h = None
                    ohlcv_4h = None
                    continue
        
        if not ohlcv_1h or not ohlcv_4h:
            return None
        
        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
        df_1h.set_index('timestamp', inplace=True)
        
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
        df_4h.set_index('timestamp', inplace=True)
        
        current_price = df_1h['close'].iloc[-1]
        levels_1h = find_support_resistance_levels(df_1h, current_price)
        levels_4h = find_support_resistance_levels(df_4h, current_price)
        
        mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', edge='inherit', wick='inherit')
        style = mpf.make_mpf_style(
            marketcolors=mc, figcolor='#131722', facecolor='#131722',
            gridcolor='#2a2e39', gridstyle='-', y_on_right=True
        )
        
        fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=False)
        fig.patch.set_facecolor('#131722')
        
        mpf.plot(df_1h, type='candle', style=style, ax=axes[0], volume=False)
        axes[0].set_title(f'{symbol} - 1H | Уровни S/R', color='white', fontsize=12, pad=10)
        axes[0].set_facecolor('#131722')
        axes[0].tick_params(colors='white')
        
        for level in levels_1h:
            price = level['price']
            touches = level['touches']
            color = '#FF4444' if level['type'] == 'resistance' else '#00FF88'
            linewidth = 2.5 if touches >= 3 else 1.5
            axes[0].axhline(y=price, color=color, linewidth=linewidth, alpha=0.8)
            axes[0].text(len(df_1h) * 0.02, price, f' {price:.6f} ({touches}x)', 
                        color=color, fontsize=9, fontweight='bold',
                        bbox=dict(boxstyle='round', facecolor='#131722', edgecolor=color, alpha=0.8))
        
        axes[0].axhline(y=current_price, color='#FFD700', linewidth=1.5, linestyle='--', alpha=0.7)
        
        mpf.plot(df_4h, type='candle', style=style, ax=axes[1], volume=False)
        axes[1].set_title(f'{symbol} - 4H | Уровни S/R', color='white', fontsize=12, pad=10)
        axes[1].set_facecolor('#131722')
        axes[1].tick_params(colors='white')
        
        for level in levels_4h:
            price = level['price']
            touches = level['touches']
            color = '#FF4444' if level['type'] == 'resistance' else '#00FF88'
            linewidth = 2.5 if touches >= 3 else 1.5
            axes[1].axhline(y=price, color=color, linewidth=linewidth, alpha=0.8)
            axes[1].text(len(df_4h) * 0.02, price, f' {price:.6f} ({touches}x)', 
                        color=color, fontsize=9, fontweight='bold',
                        bbox=dict(boxstyle='round', facecolor='#131722', edgecolor=color, alpha=0.8))
        
        axes[1].axhline(y=current_price, color='#FFD700', linewidth=1.5, linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        
        filename = f'chart_{symbol.replace("/", "")}.png'
        plt.savefig(filename, dpi=100, bbox_inches='tight', facecolor='#131722')
        plt.close()
        
        print(f"✅ График сохранён: {filename}")
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка создания графика {symbol}: {e}")
        return None

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

    sorted_coins = sorted(final_coins.items(), key=lambda x: len(x[1]), reverse=True)
    return sorted_coins

def get_scan_keyboard():
    keyboard = [[InlineKeyboardButton("🔍 Найти монеты", callback_data='scan')]]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>СКАНЕР MEXC SPOT С УРОВНЯМИ S/R!</b>\n\n"
        "Бот ищет монеты с объемом > $5 млн на:\n"
        "Binance, Bybit, Bitget, BingX, MEXC.\n"
        "✅ Показывает только те, что есть на <b>MEXC SPOT</b>\n"
        " К каждой монете график (1H + 4H) с уровнями!\n"
        " Уровни: 2+ касаний (только непробитые)\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=get_scan_keyboard(),
        parse_mode='HTML'
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    status_msg = await query.message.reply_text(
        "⏳ <b>Сканирую биржи...</b>\n\n"
        "Это займёт 3-5 минут (графики с уровнями).",
        parse_mode='HTML'
    )
    
    loop = asyncio.get_event_loop()
    sorted_coins = await loop.run_in_executor(None, scan_markets_task)
    
    await status_msg.delete()
    
    if not sorted_coins:
        await query.message.reply_text(
            "❌ Монеты не найдены. Попробуй позже.",
            reply_markup=get_scan_keyboard()
        )
        return
    
    total = len(sorted_coins)
    print(f"\n📊 Найдено {total} монет. Начинаю отправку с графиками...")
    
    chart_exchanges = {}
    for name in ['Binance', 'Bybit', 'Bitget', 'BingX', 'MEXC']:
        try:
            if name == 'Binance':
                chart_exchanges[name] = ccxt.binance({'enableRateLimit': True, 'timeout': 30000})
                chart_exchanges[name].load_markets()
            elif name == 'Bybit':
                chart_exchanges[name] = ccxt.bybit({'enableRateLimit': True, 'timeout': 30000})
                chart_exchanges[name].load_markets()
            elif name == 'Bitget':
                chart_exchanges[name] = ccxt.bitget({'enableRateLimit': True, 'timeout': 30000})
                chart_exchanges[name].load_markets()
            elif name == 'BingX':
                chart_exchanges[name] = ccxt.bingx({'enableRateLimit': True, 'timeout': 30000})
                chart_exchanges[name].load_markets()
            elif name == 'MEXC':
                chart_exchanges[name] = ccxt.mexc({'enableRateLimit': True, 'timeout': 30000, 'options': {'defaultType': 'spot'}})
                chart_exchanges[name].load_markets()
            print(f"✅ {name} подключена для графиков")
        except Exception as e:
            print(f"⚠️ {name} не подключена: {e}")
    
    sent_count = 0
    failed_count = 0
    no_chart_count = 0
    
    for i, (coin, ex_list) in enumerate(sorted_coins, 1):
        try:
            symbol = f"{coin}/USDT"
            ex_str = ', '.join(ex_list)
            
            chart_file = create_chart(symbol, chart_exchanges)
            
            caption = (
                f"<b>{i}) {coin}USDT</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Биржи:</b> {ex_str}\n"
                f"📊 <b>График:</b> 1H + 4H с уровнями S/R\n"
                f"📏 <b>Уровни:</b> 2+ касаний (непробитые)\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            
            if chart_file and os.path.exists(chart_file):
                with open(chart_file, 'rb') as photo:
                    await query.message.reply_photo(
                        photo=photo,
                        caption=caption,
                        parse_mode='HTML'
                    )
                os.remove(chart_file)
                sent_count += 1
                print(f"✅ [{i}/{total}] {coin} отправлен с графиком")
            else:
                await query.message.reply_text(
                    f"{caption}\n️ <i>График не удалось загрузить</i>",
                    parse_mode='HTML'
                )
                no_chart_count += 1
                print(f"⚠️ [{i}/{total}] {coin} без графика")
            
            await asyncio.sleep(3)
            
        except Exception as e:
            error_msg = str(e)
            
            if 'Flood control' in error_msg or 'flood' in error_msg.lower():
                print(f"️ [{i}/{total}] Flood control! Ждём 60 секунд...")
                await asyncio.sleep(60)
                try:
                    if chart_file and os.path.exists(chart_file):
                        with open(chart_file, 'rb') as photo:
                            await query.message.reply_photo(
                                photo=photo,
                                caption=caption,
                                parse_mode='HTML'
                            )
                        os.remove(chart_file)
                        sent_count += 1
                        print(f"✅ [{i}/{total}] {coin} отправлен после ожидания")
                    else:
                        await query.message.reply_text(caption, parse_mode='HTML')
                        no_chart_count += 1
                except Exception as retry_error:
                    failed_count += 1
                    print(f"❌ [{i}/{total}] {coin} повторная ошибка: {retry_error}")
            else:
                failed_count += 1
                print(f"❌ [{i}/{total}] {coin} ошибка: {e}")
            continue
    
    summary = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>СКАНИРОВАНИЕ ЗАВЕРШЕНО!</b>\n\n"
        f"📊 <b>Всего найдено:</b> {total} монет\n"
        f"✅ <b>С графиками:</b> {sent_count}\n"
        f"️ <b>Без графиков:</b> {no_chart_count}\n"
        f" <b>Ошибок:</b> {failed_count}\n"
        f"💰 <b>Фильтр:</b> объем > $5,000,000\n"
        f"✅ <b>Проверка:</b> есть на MEXC SPOT\n"
        f"📏 <b>Уровни:</b> 2+ касаний (непробитые)\n"
        f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await query.message.reply_text(
        summary,
        reply_markup=get_scan_keyboard(),
        parse_mode='HTML'
    )
    
    print(f"\n✅ Готово! С графиками: {sent_count}, Без графиков: {no_chart_count}, Ошибок: {failed_count}")

def main():
    print("="*50)
    print("🚀 ЗАПУСК СКАНЕРА MEXC SPOT С УРОВНЯМИ S/R")
    print("="*50)
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("✅ Бот готов. Жду команду /start в Telegram...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

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
MIN_VOLUME = 1_000_000
CHART_CANDLES = 50

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

# --- ГЕНЕРАЦИЯ ГРАФИКА (1H + 4H) ---
def create_chart(symbol, chart_exchanges):
    """Создаёт график с двумя таймфреймами: 1H и 4H"""
    try:
        ohlcv_1h = None
        ohlcv_4h = None
        used_exchange = None
        
        # Приоритет бирж
        for ex_name in ['Binance', 'Bybit', 'Bitget', 'BingX', 'MEXC']:
            if ex_name in chart_exchanges:
                try:
                    ohlcv_1h = chart_exchanges[ex_name].fetch_ohlcv(symbol, timeframe='1h', limit=CHART_CANDLES)
                    ohlcv_4h = chart_exchanges[ex_name].fetch_ohlcv(symbol, timeframe='4h', limit=CHART_CANDLES)
                    if ohlcv_1h and ohlcv_4h and len(ohlcv_1h) >= 10 and len(ohlcv_4h) >= 10:
                        used_exchange = ex_name
                        print(f"   Данные взяты с {ex_name}")
                        break
                except:
                    ohlcv_1h = None
                    ohlcv_4h = None
                    continue
        
        if not ohlcv_1h or not ohlcv_4h:
            return None
        
        # Преобразуем в DataFrame
        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
        df_1h.set_index('timestamp', inplace=True)
        
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
        df_4h.set_index('timestamp', inplace=True)
        
        # Стиль
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
        
        # Создаём два подграфика
        fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=False)
        fig.patch.set_facecolor('#131722')
        
        # 1H график (сверху)
        mpf.plot(df_1h, type='candle', style=style, ax=axes[0], volume=False)
        axes[0].set_title(f'{symbol} - 1H', color='white', fontsize=12, pad=10)
        axes[0].set_facecolor('#131722')
        axes[0].tick_params(colors='white')
        axes[0].spines['bottom'].set_color('#2a2e39')
        axes[0].spines['top'].set_color('#2a2e39')
        axes[0].spines['left'].set_color('#2a2e39')
        axes[0].spines['right'].set_color('#2a2e39')
        axes[0].grid(color='#2a2e39', alpha=0.3)
        
        # 4H график (снизу)
        mpf.plot(df_4h, type='candle', style=style, ax=axes[1], volume=False)
        axes[1].set_title(f'{symbol} - 4H', color='white', fontsize=12, pad=10)
        axes[1].set_facecolor('#131722')
        axes[1].tick_params(colors='white')
        axes[1].spines['bottom'].set_color('#2a2e39')
        axes[1].spines['top'].set_color('#2a2e39')
        axes[1].spines['left'].set_color('#2a2e39')
        axes[1].spines['right'].set_color('#2a2e39')
        axes[1].grid(color='#2a2e39', alpha=0.3)
        
        plt.tight_layout()
        
        # Сохраняем
        filename = f'chart_{symbol.replace("/", "")}.png'
        plt.savefig(filename, dpi=100, bbox_inches='tight', facecolor='#131722')
        plt.close()
        
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка создания графика {symbol}: {e}")
        return None

# --- СКАНИРОВАНИЕ ---
def scan_markets_task():
    exchanges = get_exchanges()
    all_coins = {}
    mexc_coins = set()
    
    print(" Загрузка рынков...")
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

# --- КНОПКА ---
def get_scan_keyboard():
    keyboard = [[InlineKeyboardButton("🔍 Найти монеты", callback_data='scan')]]
    return InlineKeyboardMarkup(keyboard)

# --- /START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>СКАНЕР MEXC SPOT ЗАПУЩЕН!</b>\n\n"
        "Бот ищет монеты с объемом > $1 млн на:\n"
        "Binance, Bybit, Bitget, BingX, MEXC.\n"
        "✅ Показывает только те, что есть на <b>MEXC SPOT</b>\n"
        " К каждой монете будет приложен график (1H + 4H)!\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=get_scan_keyboard(),
        parse_mode='HTML'
    )

# --- КНОПКА СКАНИРОВАНИЯ (ИСПРАВЛЕННАЯ) ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    status_msg = await query.message.reply_text(
        "⏳ <b>Сканирую биржи...</b>\n\n"
        "Это займёт 2-3 минуты (графики 1H+4H).",
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
    
    # Создаём подключения ко всем биржам для графиков
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
            
            # Создаём график (1H + 4H)
            chart_file = create_chart(symbol, chart_exchanges)
            
            # Текст сообщения
            caption = (
                f"<b>{i}) {coin}USDT</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Биржи:</b> {ex_str}\n"
                f"📊 <b>График:</b> 1H (сверху) | 4H (снизу)\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            
            if chart_file and os.path.exists(chart_file):
                # Отправляем с картинкой
                with open(chart_file, 'rb') as photo:
                    await query.message.reply_photo(
                        photo=photo,
                        caption=caption,
                        parse_mode='HTML'
                    )
                # Удаляем файл
                os.remove(chart_file)
                sent_count += 1
                print(f"✅ [{i}/{total}] {coin} отправлен с графиком")
            else:
                # Если график не создался — отправляем только текст
                await query.message.reply_text(
                    f"{caption}\n⚠️ <i>График не удалось загрузить</i>",
                    parse_mode='HTML'
                )
                no_chart_count += 1
                print(f"⚠️ [{i}/{total}] {coin} без графика")
            
            # 🔧 ИЗМЕНЕНО: Пауза 3 секунды вместо 0.5 (чтобы не было flood control)
            await asyncio.sleep(3)
            
        except Exception as e:
            error_msg = str(e)
            
            # 🔧 НОВОЕ: Обработка flood control
            if 'Flood control' in error_msg or 'flood' in error_msg.lower():
                print(f"⏸️ [{i}/{total}] Flood control! Ждём 60 секунд...")
                await asyncio.sleep(60)
                # Пробуем ещё раз
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
                    print(f" [{i}/{total}] {coin} повторная ошибка: {retry_error}")
            else:
                failed_count += 1
                print(f"❌ [{i}/{total}] {coin} ошибка: {e}")
            continue
    
    # Итоговое сообщение
    summary = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>СКАНИРОВАНИЕ ЗАВЕРШЕНО!</b>\n\n"
        f"📊 <b>Всего найдено:</b> {total} монет\n"
        f"✅ <b>С графиками:</b> {sent_count}\n"
        f"⚠️ <b>Без графиков:</b> {no_chart_count}\n"
        f"❌ <b>Ошибок:</b> {failed_count}\n"
        f"💰 <b>Фильтр:</b> объем > $1,000,000\n"
        f"✅ <b>Проверка:</b> есть на MEXC SPOT\n"
        f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await query.message.reply_text(
        summary,
        reply_markup=get_scan_keyboard(),
        parse_mode='HTML'
    )
    
    print(f"\n✅ Готово! С графиками: {sent_count}, Без графиков: {no_chart_count}, Ошибок: {failed_count}")

# --- ЗАПУСК ---
def main():
    print("="*50)
    print("🚀 ЗАПУСК СКАНЕРА MEXC SPOT С ГРАФИКАМИ")
    print("="*50)
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("✅ Бот готов. Жду команду /start в Telegram...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

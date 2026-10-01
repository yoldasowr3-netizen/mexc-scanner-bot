import ccxt
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = "8969022054:AAFW624orWdf7zjc6ZzoSfjvRlP9PmZHAOE"
MIN_VOLUME = 1_000_000

def get_exchanges():
    return {
        'Binance': ccxt.binance({'enableRateLimit': True, 'timeout': 30000}),
        'Bybit': ccxt.bybit({'enableRateLimit': True, 'timeout': 30000}),
        'Bitget': ccxt.bitget({'enableRateLimit': True, 'timeout': 30000}),
        'BingX': ccxt.bingx({'enableRateLimit': True, 'timeout': 30000}),
        # 🔧 ИСПРАВЛЕНО: Только SPOT для MEXC
        'MEXC': ccxt.mexc({
            'enableRateLimit': True, 
            'timeout': 30000,
            'options': {'defaultType': 'spot'}  # Только спот!
        })
    }

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
            print(f" Ошибка {name}: {e}")
            del exchanges[name]

    print(f"\n🔍 Сканирую (мин. объем: ${MIN_VOLUME:,})...")
    print("💡 MEXC проверяет только SPOT пары")
    
    for name, ex in exchanges.items():
        try:
            print(f" Сканирую {name}...")
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
            print(f"❌ Ошибка при сканировании {name}: {e}")
            continue

    final_coins = {}
    for coin, ex_list in all_coins.items():
        if coin in mexc_coins:
            final_coins[coin] = ex_list

    sorted_coins = sorted(final_coins.items(), key=lambda x: len(x[1]), reverse=True)
    
    return sorted_coins

def format_messages(sorted_coins):
    total = len(sorted_coins)
    
    header = (
        f"🔍 <b>РЕЗУЛЬТАТЫ СКАНИРОВАНИЯ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Найдено:</b> {total} монет\n"
        f"💰 <b>Фильтр:</b> объем > $1,000,000\n"
        f"✅ <b>Проверка:</b> есть на MEXC SPOT\n"
        f" <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    coins_list = ""
    for i, (coin, ex_list) in enumerate(sorted_coins, 1):
        ex_str = ', '.join(ex_list)
        coins_list += f"{i}) {coin}USDT\n"
        coins_list += f"   Активна на: {ex_str}\n\n"
        
        if len(header + coins_list) > 3500:
            yield header + coins_list
            header = f"🔍 <b>ПРОДОЛЖЕНИЕ ({i+1}-{total})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            coins_list = ""
    
    if coins_list:
        yield header + coins_list

def get_scan_keyboard():
    keyboard = [[InlineKeyboardButton("🔍 Найти монеты", callback_data='scan')]]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>СКАНЕР MEXC SPOT ЗАПУЩЕН!</b>\n\n"
        "Бот ищет монеты с объемом > $1 млн на:\n"
        "Binance, Bybit, Bitget, BingX, MEXC.\n"
        "✅ Показывает только те, что есть на <b>MEXC SPOT</b>\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=get_scan_keyboard(),
        parse_mode='HTML'
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    status_msg = await query.message.reply_text("⏳ <b>Сканирую биржи...</b>\nЭто займёт 15-30 секунд.", parse_mode='HTML')
    
    loop = asyncio.get_event_loop()
    sorted_coins = await loop.run_in_executor(None, scan_markets_task)
    
    await status_msg.delete()
    
    if not sorted_coins:
        await query.message.reply_text("❌ Монеты не найдены. Попробуй позже.", reply_markup=get_scan_keyboard())
        return
    
    messages = list(format_messages(sorted_coins))
    
    for idx, message_text in enumerate(messages):
        is_last = (idx == len(messages) - 1)
        reply_markup = get_scan_keyboard() if is_last else None
        
        await query.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
            
    print(f"✅ Отправлено {len(sorted_coins)} монет в {len(messages)} сообщениях")

def main():
    print("="*50)
    print("🚀 ЗАПУСК СКАНЕРА MEXC SPOT")
    print("="*50)
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("✅ Бот готов. Жду команду /start в Telegram...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

# --- ГЕНЕРАЦИЯ ГРАФИКА С УРОВНЯМИ (ПРАВИЛЬНЫЙ СПОСОБ) ---
def create_chart(symbol, chart_exchanges):
    """Создаёт график с двумя таймфреймами и уровнями S/R"""
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
        
        # Находим уровни
        levels_1h = find_support_resistance_levels(df_1h, current_price)
        levels_4h = find_support_resistance_levels(df_4h, current_price)
        
        # Стиль
        mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', edge='inherit', wick='inherit')
        style = mpf.make_mpf_style(
            marketcolors=mc, figcolor='#131722', facecolor='#131722',
            gridcolor='#2a2e39', gridstyle='-', y_on_right=True
        )
        
        # 🔧 ПРАВИЛЬНЫЙ СПОСОБ: создаём addplot для уровней
        def make_hlines_addplot(levels, df):
            """Создаёт addplot для горизонтальных линий"""
            if not levels:
                return []
            
            addplots = []
            for level in levels:
                price = level['price']
                touches = level['touches']
                color = 'red' if level['type'] == 'resistance' else 'lime'
                linewidth = 2.5 if touches >= 3 else 1.5
                
                # Создаём DataFrame с одинаковой ценой для всех свечей
                hline_data = pd.DataFrame(
                    {'price': [price] * len(df)},
                    index=df.index
                )
                
                addplot = mpf.make_addplot(
                    hline_data['price'],
                    color=color,
                    linewidth=linewidth,
                    linestyle='-',
                    secondary_y=False
                )
                addplots.append(addplot)
            
            # Добавляем текущую цену
            current_price_data = pd.DataFrame(
                {'price': [current_price] * len(df)},
                index=df.index
            )
            current_price_addplot = mpf.make_addplot(
                current_price_data['price'],
                color='gold',
                linewidth=1.5,
                linestyle='--',
                secondary_y=False
            )
            addplots.append(current_price_addplot)
            
            return addplots
        
        # Создаём addplots для 1H и 4H
        addplots_1h = make_hlines_addplot(levels_1h, df_1h)
        addplots_4h = make_hlines_addplot(levels_4h, df_4h)
        
        # Создаём два подграфика
        fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=False)
        fig.patch.set_facecolor('#131722')
        
        # 1H график с уровнями
        mpf.plot(
            df_1h,
            type='candle',
            style=style,
            ax=axes[0],
            volume=False,
            addplot=addplots_1h if addplots_1h else None
        )
        axes[0].set_title(f'{symbol} - 1H | Уровни S/R', color='white', fontsize=12, pad=10)
        axes[0].set_facecolor('#131722')
        axes[0].tick_params(colors='white')
        
        # Добавляем легенду с уровнями для 1H
        if levels_1h:
            legend_text = "Уровни 1H:\n"
            for level in levels_1h[:3]:
                level_type = "R" if level['type'] == 'resistance' else "S"
                legend_text += f"{level_type}: {level['price']:.6f} ({level['touches']}x)\n"
            axes[0].text(
                0.02, 0.98, legend_text,
                transform=axes[0].transAxes,
                fontsize=9,
                color='white',
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='#131722', edgecolor='white', alpha=0.8)
            )
        
        # 4H график с уровнями
        mpf.plot(
            df_4h,
            type='candle',
            style=style,
            ax=axes[1],
            volume=False,
            addplot=addplots_4h if addplots_4h else None
        )
        axes[1].set_title(f'{symbol} - 4H | Уровни S/R', color='white', fontsize=12, pad=10)
        axes[1].set_facecolor('#131722')
        axes[1].tick_params(colors='white')
        
        # Добавляем легенду с уровнями для 4H
        if levels_4h:
            legend_text = "Уровни 4H:\n"
            for level in levels_4h[:3]:
                level_type = "R" if level['type'] == 'resistance' else "S"
                legend_text += f"{level_type}: {level['price']:.6f} ({level['touches']}x)\n"
            axes[1].text(
                0.02, 0.98, legend_text,
                transform=axes[1].transAxes,
                fontsize=9,
                color='white',
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='#131722', edgecolor='white', alpha=0.8)
            )
        
        plt.tight_layout()
        
        filename = f'chart_{symbol.replace("/", "")}.png'
        plt.savefig(filename, dpi=100, bbox_inches='tight', facecolor='#131722')
        plt.close()
        
        print(f"✅ График сохранён: {filename} (1H: {len(levels_1h)} уровней, 4H: {len(levels_4h)} уровней)")
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка создания графика {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

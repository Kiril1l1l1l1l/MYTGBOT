import telebot
from telebot import types
import json
import requests
import os
import threading
import time

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    raise ValueError("❌ HF_TOKEN не найден! Убедись, что он добавлен в переменные окружения Railway.")


TG_TOKEN = os.getenv("TG_TOKEN")

if not TG_TOKEN:
    raise ValueError("❌ TG_TOKEN не найден! Убедись, что он добавлен в Environment Variables Railway.")

PORTFOLIO_FILE = 'portfolio.json'
ALERTS = {
    'USD': {'buy_below': 82.0, 'sell_above': 85.5},
    'MTSS': {'buy_below': 203.0, 'sell_above': 213.0},
    'OGKB': {'buy_below': 0.34, 'sell_above': 0.355},
    'VKCO': {'buy_below': 318.0, 'sell_above': 335.0}
}
MOEX_URL = 'https://iss.moex.com/iss/engines/stock/markets/shares/securities/{}.json'

bot = telebot.TeleBot(TG_TOKEN)
user_chat_id = None
monitoring_active = True

def get_stock_price(symbol):
    try:
        url = MOEX_URL.format(symbol.lower())
        res = requests.get(url).json()
        return float(res['marketdata']['data'][0][8])
    except:
        return None
        def ask_huggingface(prompt):
    """
    Отправляет запрос в Hugging Face API и возвращает ответ модели.
    """
    url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        if isinstance(result, list) and "generated_text" in result[0]:
            return result[0]["generated_text"]
        else:
            return str(result)
    except Exception as e:
        return f"Ошибка при запросе к Hugging Face: {e}"


def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, 'r') as f:
            return json.load(f)
    return []

def save_portfolio(data):
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def alert_loop():
    global monitoring_active
    while True:
        if not user_chat_id or not monitoring_active:
            time.sleep(10)
            continue
        try:
            for symbol, limits in ALERTS.items():
                price = get_stock_price(symbol)
                if price is None:
                    continue
                if price <= limits['buy_below']:
                    bot.send_message(user_chat_id, f"📉 {symbol} упал до {price}₽ — возможна покупка")
                elif price >= limits['sell_above']:
                    bot.send_message(user_chat_id, f"📈 {symbol} поднялся до {price}₽ — возможна продажа")
        except Exception as e:
            print(f"[ОШИБКА]: {e}")
        time.sleep(60)

@bot.message_handler(commands=['start'])
def start_handler(message):
    global user_chat_id, monitoring_active
    user_chat_id = message.chat.id
    monitoring_active = True
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📈 Профит", callback_data="profit"),
        types.InlineKeyboardButton("📄 Список", callback_data="list"),
        types.InlineKeyboardButton("🧠 Совет", callback_data="advice"),
        types.InlineKeyboardButton("➕ Добавить", callback_data="add"),
        types.InlineKeyboardButton("➖ Удалить", callback_data="delete"),
        types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh")
    )
    bot.send_message(message.chat.id, "✅ Бот запущен и следит за рынком", reply_markup=markup)

@bot.message_handler(commands=['stop'])
def stop_handler(message):
    global monitoring_active
    monitoring_active = False
    bot.send_message(message.chat.id, "⛔️ Мониторинг остановлен. Чтобы включить — /start")
    @bot.message_handler(commands=['ask'])
def handle_ask(message):
    """
    Обрабатывает команду /ask — отправляет запрос в Hugging Face и присылает ответ.
    """
    question = message.text.replace("/ask", "").strip()
    if not question:
        bot.reply_to(message, "❓ Введите запрос после команды /ask, например:\n/ask Найди свежие новости по Газпрому")
        return
    bot.send_message(message.chat.id, "⏳ Ищу информацию, подождите...")
    answer = ask_huggingface(question)
    bot.send_message(message.chat.id, answer)


@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    if call.data == "profit":
        show_profit(call.message)
    elif call.data == "list":
        show_list(call.message)
    elif call.data == "add":
        msg = bot.send_message(call.message.chat.id, "✍️ Введите тикер, количество и цену\nПример: MTSS 10 207.5")
        bot.register_next_step_handler(msg, handle_add)
    elif call.data == "delete":
        handle_delete(call.message)
    elif call.data == "refresh":
        show_profit(call.message)
    elif call.data == "advice":
        show_advice(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def confirm_delete(call):
    index = int(call.data.split("_")[1])
    portfolio = load_portfolio()
    removed = portfolio.pop(index)
    save_portfolio(portfolio)
    bot.send_message(call.message.chat.id, f"✅ {removed['symbol']} удалена.")

def handle_add(message):
    try:
        parts = message.text.strip().split()
        if len(parts) != 3:
            return bot.reply_to(message, "❌ Формат: TICKER КОЛ-ВО ЦЕНА")
        symbol, amount, price = parts
        data = load_portfolio()
        data.append({"symbol": symbol.upper(), "amount": float(amount), "buy_price": float(price)})
        save_portfolio(data)
        bot.send_message(message.chat.id, f"✅ {symbol.upper()} добавлена.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

def handle_delete(message):
    portfolio = load_portfolio()
    if not portfolio:
        return bot.send_message(message.chat.id, "❌ Портфель пуст.")
    markup = types.InlineKeyboardMarkup()
    for i, stock in enumerate(portfolio):
        markup.add(types.InlineKeyboardButton(f"{stock['symbol']}", callback_data=f"del_{i}"))
    bot.send_message(message.chat.id, "Выбери акцию для удаления:", reply_markup=markup)

def show_list(message):
    data = load_portfolio()
    if not data:
        return bot.send_message(message.chat.id, "📄 Портфель пуст.")
    text = "📄 Портфель:\n"
    for s in data:
        text += f"{s['symbol']}: {s['amount']} по {s['buy_price']}\n"
    bot.send_message(message.chat.id, text)

def show_profit(message):
    data = load_portfolio()
    if not data:
        return bot.send_message(message.chat.id, "📄 Портфель пуст.")
    total = 0
    text = "📊 Профит:\n"
    for s in data:
        price = get_stock_price(s['symbol'])
        if price:
            profit = (price - s['buy_price']) * s['amount']
            total += profit
            text += f"{s['symbol']}: {round(profit, 2)}₽ (сейчас {price}₽)\n"
        else:
            text += f"{s['symbol']}: ❓ цена не найдена\n"
    text += f"\n💰 Общий профит: {round(total, 2)}₽"
    bot.send_message(message.chat.id, text)

def show_advice(message):
    data = load_portfolio()
    advice = "🧠 Совет:\n"
    for s in data:
        price = get_stock_price(s['symbol'])
        level = ALERTS.get(s['symbol'].upper())
        if price and level:
            if price >= level['sell_above']:
                advice += f"{s['symbol']}: 📈 Можно продавать (сейчас {price})\n"
            elif price <= level['buy_below']:
                advice += f"{s['symbol']}: 📉 Возможна покупка ({price})\n"
            else:
                advice += f"{s['symbol']}: 🟡 Держать ({price})\n"
    bot.send_message(message.chat.id, advice)

print("[INFO] Бот запущен.")
threading.Thread(target=alert_loop, daemon=True).start()
bot.polling(none_stop=True)

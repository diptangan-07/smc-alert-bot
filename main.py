from flask import Flask, request
import requests

app = Flask(__name__)

# Your Credentials
TELEGRAM_TOKEN = "8893050202:AAHrl0kzyt5Bjptbuoy9ae2c9SwF0KAOsmE"
CHAT_ID = "7476331970"

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data:
        strategy_name = data.get('strat', 'SMC Alert')
        msg = data.get('msg', 'New Trading Signal Generated!')
        
        # Formatting Alert Message
        telegram_text = f"🚨 *TRADING ALERT* 🚨\n\n📌 *Strategy:* {strategy_name}\n📊 *Details:* {msg}"
        send_telegram_msg(telegram_text)
        return "SUCCESS", 200
    return "BAD REQUEST", 400

@app.route('/', methods=['GET'])
def home():
    return "Diptangan SMC Trading Bot Server is Running Live 24/7!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
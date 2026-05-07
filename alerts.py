import requests
from datetime import datetime

class AlertManager:
    def __init__(self, webhook_url: str):
        self.url = webhook_url
    
    def send(self, title: str, msg: str, color: int = 5814783):
        if not self.url:
            return
        try:
            requests.post(self.url, json={"embeds": [{"title": title, "description": msg, "color": color}]}, timeout=5)
        except:
            pass
    
    def trade(self, action: str, symbol: str, qty: int, price: float, reason: str):
        color = 3066993 if action == "BUY" else 15158332
        emoji = "🟢" if action == "BUY" else "🔴"
        self.send(
            f"{emoji} {action} {symbol}",
            f"**{qty} shares** @ ${price:.2f}\n**Reason:** {reason}",
            color
        )
    
    def error(self, msg: str):
        self.send("🚨 Bot Error", f"```{msg[:1900]}```", 15158332)
    
    def startup(self, stocks: int):
        self.send("✅ Bot Started", f"**Universe:** {stocks} stocks\n**Mode:** Paper Trading", 3447003)
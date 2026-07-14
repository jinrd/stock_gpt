import requests
import os
from dotenv import load_dotenv

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def send_message(self, message):
        """텔레그램 메시지 전송"""
        if not self.token or not self.chat_id:
            print("❌ 텔레그램 설정이 비어있습니다.")
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": f"🤖 [Trading Bot]\n{message}",
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(url, data=payload)
            if response.status_code != 200:
                print(f"❌ 텔레그램 전송 실패: {response.text}")
        except Exception as e:
            print(f"❌ 텔레그램 연결 에러: {e}")
            
# 테스트 코드 (이 파일만 실행했을 때 작동)
# if __name__ == "__main__":
#     notifier = TelegramNotifier()
#     notifier.send_message("연결 테스트 성공! 🚀")
import json
import os
import logging
import random
from typing import List, Optional, Dict, Union
from threading import Lock
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)

# === إعداد Logging ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# === إعداد متغيرات البيئة ===
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("يجب تعيين LINE_CHANNEL_ACCESS_TOKEN و LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# === Locks للتزامن ===
content_lock = Lock()

# === مدير المحتوى ===
class ContentManager:
    """مدير المحتوى مع معالجة الأخطاء"""
    def __init__(self):
        self.content_files: Dict[str, List[str]] = {}
        self.more_questions: List[str] = []
        self.proverbs_list: List[dict] = []
        self.riddles_list: List[dict] = []
        self.games_list: List[dict] = []
        self.poems_list: List[dict] = []
        self.quotes_list: List[dict] = []
        self.detailed_results: Dict = {}
        self.used_indices: Dict[str, List[int]] = {}

    def load_file_lines(self, filename: str) -> List[str]:
        if not os.path.exists(filename):
            logger.warning(f"الملف غير موجود: {filename}")
            return []
        try:
            with open(filename, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                logger.info(f"تم تحميل {len(lines)} سطر من {filename}")
                return lines
        except Exception as e:
            logger.error(f"خطأ في قراءة الملف {filename}: {e}")
            return []

    def load_json_file(self, filename: str) -> Union[dict, list]:
        if not os.path.exists(filename):
            logger.warning(f"الملف غير موجود: {filename}")
            return [] if filename.endswith("s.json") else {}
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"تم تحميل {filename}")
                return data
        except Exception as e:
            logger.error(f"خطأ في قراءة JSON {filename}: {e}")
            return [] if filename.endswith("s.json") else {}

    def initialize(self):
        """تحميل جميع الملفات"""
        self.content_files = {
            "سؤال": self.load_file_lines("questions.txt"),
            "تحدي": self.load_file_lines("challenges.txt"),
            "اعتراف": self.load_file_lines("confessions.txt"),
        }
        self.used_indices = {key: [] for key in self.content_files.keys()}
        for key in ["أكثر","أمثال","لغز","شعر","اقتباسات"]:
            self.used_indices[key] = []

        self.more_questions = self.load_file_lines("more_file.txt")
        self.proverbs_list = self.load_json_file("proverbs.json")
        self.riddles_list = self.load_json_file("riddles.json")
        self.detailed_results = self.load_json_file("detailed_results.json")
        self.poems_list = self.load_json_file("poems.json")
        self.quotes_list = self.load_json_file("quotes.json")
        data = self.load_json_file("personality_games.json")
        if isinstance(data, dict):
            self.games_list = [data[key] for key in sorted(data.keys())]
        else:
            self.games_list = []

        logger.info("تم تهيئة جميع الملفات بنجاح")

    def get_random_index(self, command: str, max_length: int) -> int:
        with content_lock:
            if len(self.used_indices[command]) >= max_length:
                self.used_indices[command] = []
            available_indices = [i for i in range(max_length) if i not in self.used_indices[command]]
            index = random.choice(available_indices) if available_indices else random.randint(0, max_length - 1)
            self.used_indices[command].append(index)
            return index

    def get_content(self, command: str) -> Optional[str]:
        file_list = self.content_files.get(command, [])
        if not file_list:
            return None
        return file_list[self.get_random_index(command, len(file_list))]

    def get_more_question(self) -> Optional[str]:
        if not self.more_questions:
            return None
        return self.more_questions[self.get_random_index("أكثر", len(self.more_questions))]

    def get_proverb(self) -> Optional[dict]:
        if not self.proverbs_list:
            return None
        return self.proverbs_list[self.get_random_index("أمثال", len(self.proverbs_list))]

    def get_riddle(self) -> Optional[dict]:
        if not self.riddles_list:
            return None
        return self.riddles_list[self.get_random_index("لغز", len(self.riddles_list))]

    def get_poem(self) -> Optional[str]:
        if not self.poems_list:
            return None
        poem_entry = self.poems_list[self.get_random_index("شعر", len(self.poems_list))]
        return f"📝 شعر - {poem_entry.get('poet','')}:\n\n{poem_entry.get('text','')}"

    def get_quote(self) -> Optional[str]:
        if not self.quotes_list:
            return None
        quote_entry = self.quotes_list[self.get_random_index("اقتباسات", len(self.quotes_list))]
        return f"💭 اقتباس - {quote_entry.get('author','')}:\n\n{quote_entry.get('text','')}"

# تهيئة مدير المحتوى
content_manager = ContentManager()
content_manager.initialize()

# === تحميل القصص ===
with open("stories.json","r",encoding="utf-8") as f:
    stories_list = json.load(f)

def get_random_story() -> str:
    """
    تختار قصة عشوائية من stories_list وتعيدها في رسالة واحدة.
    كل قصة تحتوي على:
    - title: عنوان القصة
    - story: نص القصة
    - moral: العبرة
    """
    if not stories_list:
        return "⚠️ لا توجد قصص متاحة حالياً."

    story_entry = random.choice(stories_list)
    title = story_entry.get("title", "قصة غير معروفة")
    story_text = story_entry.get("story", "")
    moral = story_entry.get("moral", "")

    return f"📖 {title}\n\n{story_text}\n\n{moral}"

# === المستخدمين وحالتهم ===
user_game_state: Dict[str, dict] = {}
user_proverb_state: Dict[str, dict] = {}
user_riddle_state: Dict[str, dict] = {}

# === الأوامر المتاحة ===
COMMANDS_MAP = {
    "سؤال": ["سؤال", "سوال", "اسأله", "اسئلة", "اسأل"],
    "تحدي": ["تحدي", "تحديات", "تحد"],
    "اعتراف": ["اعتراف", "اعترافات"],
    "أكثر": ["أكثر", "اكثر", "زيادة"],
    "أمثال": ["أمثال", "امثال", "مثل"],
    "لغز": ["لغز", "الغاز", "ألغاز"],
    "شعر": ["شعر"],
    "اقتباسات": ["اقتباسات"]
}

def find_command(text: str) -> Optional[str]:
    text_lower = text.lower().strip()
    for key, variants in COMMANDS_MAP.items():
        if text_lower in [v.lower() for v in variants]:
            return key
    return None

# === الأزرار الرئيسية ===
def create_main_menu() -> QuickReply:
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="❓ سؤال", text="سؤال")),
        QuickReplyButton(action=MessageAction(label="🎯 تحدي", text="تحدي")),
        QuickReplyButton(action=MessageAction(label="💬 اعتراف", text="اعتراف")),
        QuickReplyButton(action=MessageAction(label="✨ أكثر", text="أكثر")),
        QuickReplyButton(action=MessageAction(label="📝 شعر", text="شعر")),
        QuickReplyButton(action=MessageAction(label="💭 اقتباسات", text="اقتباسات")),
        QuickReplyButton(action=MessageAction(label="🧩 لغز", text="لغز")),
        QuickReplyButton(action=MessageAction(label="📜 أمثال", text="أمثال")),
        QuickReplyButton(action=MessageAction(label="🎮 لعبة", text="لعبه")),
        QuickReplyButton(action=MessageAction(label="📚 قصة", text="قصة")),
    ])

# === ردود الأوامر ===
def handle_content_command(event, command: str):
    if command == "أمثال":
        proverb = content_manager.get_proverb()
        if proverb:
            user_proverb_state[event.source.user_id] = proverb
            content = f"📜 المثل:\n{proverb['question']}\n\n💡 اكتب 'جاوب' لمعرفة المعنى"
        else:
            content = "⚠️ لا توجد أمثال حالياً."
    elif command == "لغز":
        riddle = content_manager.get_riddle()
        if riddle:
            user_riddle_state[event.source.user_id] = riddle
            content = f"🧩 اللغز:\n{riddle['question']}\n\n💡 اكتب 'لمح' للتلميح أو 'جاوب' للإجابة"
        else:
            content = "⚠️ لا توجد ألغاز حالياً."
    elif command == "أكثر":
        q = content_manager.get_more_question()
        content = q if q else "⚠️ لا توجد أسئلة في هذا القسم."
    elif command == "شعر":
        poem = content_manager.get_poem()
        content = poem if poem else "⚠️ لا يوجد شعر حالياً."
    elif command == "اقتباسات":
        quote = content_manager.get_quote()
        content = quote if quote else "⚠️ لا توجد اقتباسات حالياً."
    else:
        content = content_manager.get_content(command) or f"⚠️ لا توجد بيانات في قسم '{command}'."
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=content, quick_reply=create_main_menu()))

def handle_answer_command(event, user_id: str):
    if user_id in user_proverb_state:
        proverb = user_proverb_state.pop(user_id)
        msg = f"✅ معنى المثل:\n{proverb['answer']}"
    elif user_id in user_riddle_state:
        riddle = user_riddle_state.pop(user_id)
        msg = f"✅ الإجابة:\n{riddle['answer']}"
    else:
        msg = "⚠️ لا توجد إجابة حالياً."
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg, quick_reply=create_main_menu()))

def handle_hint_command(event, user_id: str):
    if user_id in user_riddle_state:
        hint = user_riddle_state[user_id].get('hint','لا يوجد تلميح')
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"💡 التلميح:\n{hint}"))

# === التعامل مع الرسائل ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    text_lower = text.lower()

    try:
        if text_lower in ["مساعدة","help","start","بداية"]:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text="اختر من القائمة أدناه:", quick_reply=create_main_menu()))
            return

        command = find_command(text)
        if command:
            handle_content_command(event, command)
            return

        if text_lower in ["جاوب","الجواب","اجابة","الاجابة"]:
            handle_answer_command(event, user_id)
            return

        if text_lower in ["لمح","تلميح","hint"]:
            handle_hint_command(event, user_id)
            return

        if text_lower in ["لعبه","لعبة","العاب","ألعاب","game"]:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🎮 الألعاب مؤقتاً غير مفعلة"))
            return

        if text_lower in ["قصة","story"]:
            story_msg = get_random_story()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=story_msg, quick_reply=create_main_menu()))
            return

    except Exception as e:
        logger.error(f"خطأ في معالجة الرسالة: {e}", exc_info=True)
        try:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ حدث خطأ، يرجى المحاولة مرة أخرى"))
        except:
            pass

# === تشغيل السيرفر ===
@app.route("/", methods=["GET"])
def home():
    return "✅ البوت يعمل!", 200

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature","")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body,signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    logger.info(f"البوت يعمل على المنفذ {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

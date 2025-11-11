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

class ContentManager:
    """مدير المحتوى المطور"""
    
    def __init__(self):
        self.content_files: Dict[str, List[str]] = {}
        self.poems_list: List[dict] = []
        self.quotes_list: List[dict] = []
        self.stories_list: List[dict] = []
        self.would_you_rather: List[dict] = []
        self.games_list: List[dict] = []
        self.detailed_results: Dict = {}
        
        # تتبع العناصر المستخدمة
        self.used_indices: Dict[str, List[int]] = {}
        
    def load_file_lines(self, filename: str) -> List[str]:
        """تحميل محتوى ملف نصي"""
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
        """تحميل ملف JSON"""
        if not os.path.exists(filename):
            logger.warning(f"الملف غير موجود: {filename}")
            return [] if filename.endswith("s.json") else {}
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"تم تحميل {filename}")
                return data
        except Exception as e:
            logger.error(f"خطأ في قراءة {filename}: {e}")
            return [] if filename.endswith("s.json") else {}
    
    def initialize(self):
        """تحميل جميع الملفات"""
        # تحميل الملفات الأساسية
        self.content_files = {
            "سؤال": self.load_file_lines("questions.txt"),
            "تحدي": self.load_file_lines("challenges.txt"),
            "اعتراف": self.load_file_lines("confessions.txt"),
            "أكثر": self.load_file_lines("more_questions.txt"),
        }
        
        # تهيئة قوائم التتبع
        self.used_indices = {
            "سؤال": [], "تحدي": [], "اعتراف": [], "أكثر": [],
            "شعر": [], "حكمة": [], "قصة": [], "اختيار": []
        }
        
        # تحميل المحتوى الإضافي
        self.poems_list = self.load_json_file("poems.json")
        self.quotes_list = self.load_json_file("quotes.json")
        self.stories_list = self.load_json_file("stories.json")
        self.would_you_rather = self.load_json_file("would_you_rather.json")
        self.detailed_results = self.load_json_file("detailed_results.json")
        
        # تحميل الألعاب
        data = self.load_json_file("personality_games.json")
        if isinstance(data, dict):
            self.games_list = [data[key] for key in sorted(data.keys())]
        else:
            self.games_list = []
        
        logger.info("تم تهيئة جميع الملفات بنجاح")
    
    def get_random_index(self, command: str, max_length: int) -> int:
        """الحصول على index عشوائي غير مكرر"""
        with content_lock:
            if len(self.used_indices[command]) >= max_length:
                self.used_indices[command] = []
            
            available_indices = [i for i in range(max_length) 
                               if i not in self.used_indices[command]]
            
            if available_indices:
                index = random.choice(available_indices)
                self.used_indices[command].append(index)
                return index
            
            return random.randint(0, max_length - 1)
    
    def get_content(self, command: str) -> Optional[str]:
        """الحصول على محتوى عشوائي"""
        file_list = self.content_files.get(command, [])
        if not file_list:
            return None
        
        index = self.get_random_index(command, len(file_list))
        return file_list[index]
    
    def get_poem(self) -> Optional[dict]:
        """الحصول على قصيدة عشوائية"""
        if not self.poems_list:
            return None
        
        index = self.get_random_index("شعر", len(self.poems_list))
        return self.poems_list[index]
    
    def get_quote(self) -> Optional[dict]:
        """الحصول على حكمة عشوائية"""
        if not self.quotes_list:
            return None
        
        index = self.get_random_index("حكمة", len(self.quotes_list))
        return self.quotes_list[index]
    
    def get_story(self) -> Optional[dict]:
        """الحصول على قصة عشوائية"""
        if not self.stories_list:
            return None
        
        index = self.get_random_index("قصة", len(self.stories_list))
        return self.stories_list[index]
    
    def get_would_you_rather(self) -> Optional[dict]:
        """الحصول على سؤال 'هل تفضل'"""
        if not self.would_you_rather:
            return None
        
        index = self.get_random_index("اختيار", len(self.would_you_rather))
        return self.would_you_rather[index]

# تهيئة مدير المحتوى
content_manager = ContentManager()
content_manager.initialize()

# === حالات المستخدمين ===
user_game_state: Dict[str, dict] = {}
user_story_state: Dict[str, dict] = {}

# === خريطة الأوامر ===
COMMANDS_MAP = {
    "سؤال": ["سؤال", "سوال", "اسأله", "اسئلة", "اسأل"],
    "تحدي": ["تحدي", "تحديات", "تحد"],
    "اعتراف": ["اعتراف", "اعترافات"],
    "أكثر": ["أكثر", "اكثر", "زيادة"],
    "شعر": ["شعر", "قصيدة", "قصيده", "ابيات"],
    "حكمة": ["حكمة", "حكم", "اقتباس", "اقتباسات", "quote"],
    "قصة": ["قصة", "قصه", "حكاية", "story"],
    "اختيار": ["اختيار", "هل تفضل", "خيار", "would you rather"]
}

def find_command(text: str) -> Optional[str]:
    """البحث عن الأمر المطابق"""
    text_lower = text.lower().strip()
    for key, variants in COMMANDS_MAP.items():
        if text_lower in [v.lower() for v in variants]:
            return key
    return None

def create_main_menu() -> QuickReply:
    """إنشاء القائمة السريعة المطورة"""
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="❓ سؤال", text="سؤال")),
        QuickReplyButton(action=MessageAction(label="🎯 تحدي", text="تحدي")),
        QuickReplyButton(action=MessageAction(label="💬 اعتراف", text="اعتراف")),
        QuickReplyButton(action=MessageAction(label="✨ أكثر", text="أكثر")),
        QuickReplyButton(action=MessageAction(label="📖 شعر", text="شعر")),
        QuickReplyButton(action=MessageAction(label="💡 حكمة", text="حكمة")),
        QuickReplyButton(action=MessageAction(label="📚 قصة", text="قصة")),
        QuickReplyButton(action=MessageAction(label="🤔 اختيار", text="اختيار")),
        QuickReplyButton(action=MessageAction(label="🎮 لعبة", text="لعبه")),
    ])

def get_games_list() -> str:
    """قائمة الألعاب المتاحة"""
    if not content_manager.games_list:
        return "⚠️ لا توجد ألعاب متاحة حالياً."
    
    titles = ["🎮 الألعاب المتاحة:", ""]
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, game in enumerate(content_manager.games_list):
        emoji = number_emojis[i] if i < len(number_emojis) else f"{i+1}️⃣"
        game_title = game.get('title', f'اللعبة {i+1}')
        titles.append(f"{emoji} {game_title}")
    
    titles.append("")
    titles.append(f"📌 أرسل رقم اللعبة (1-{len(content_manager.games_list)})")
    
    return "\n".join(titles)

def calculate_result(answers: List[str], game_index: int) -> str:
    """حساب نتيجة اللعبة"""
    count = {"أ": 0, "ب": 0, "ج": 0}
    for ans in answers:
        if ans in count:
            count[ans] += 1
    
    most_common = max(count, key=count.get)
    game_key = f"لعبة{game_index + 1}"
    result_text = content_manager.detailed_results.get(game_key, {}).get(
        most_common,
        f"✅ إجابتك الأكثر: {most_common}\n\n🎯 نتيجتك تعكس شخصية فريدة!"
    )
    
    stats = f"\n\n📊 إحصائياتك:\n"
    stats += f"أ: {count['أ']} | ب: {count['ب']} | ج: {count['ج']}"
    return result_text + stats

# === Routes ===
@app.route("/", methods=["GET"])
def home():
    return "✅ البوت المطور يعمل بنجاح!", 200

@app.route("/health", methods=["GET"])
def health_check():
    return {"status": "healthy", "service": "enhanced-line-bot"}, 200

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("توقيع غير صالح")
        abort(400)
    except Exception as e:
        logger.error(f"خطأ في معالجة الطلب: {e}")
        abort(500)
    
    return "OK"

# === معالج الرسائل ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    text_lower = text.lower()
    
    try:
        # أمر المساعدة
        if text_lower in ["مساعدة", "help", "بداية", "start", "قائمة", "menu"]:
            welcome_msg = "🌟 مرحباً بك في البوت الشامل!\n\n"
            welcome_msg += "📋 الميزات المتاحة:\n"
            welcome_msg += "❓ أسئلة عميقة ومثيرة\n"
            welcome_msg += "🎯 تحديات ممتعة\n"
            welcome_msg += "💬 اعترافات صادقة\n"
            welcome_msg += "📖 أشعار وأبيات\n"
            welcome_msg += "💡 حكم واقتباسات\n"
            welcome_msg += "📚 قصص ملهمة\n"
            welcome_msg += "🤔 أسئلة الاختيار\n"
            welcome_msg += "🎮 ألعاب شخصية\n\n"
            welcome_msg += "✨ اختر من القائمة أدناه:"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome_msg, quick_reply=create_main_menu())
            )
            return
        
        # معالجة الأوامر الأساسية
        command = find_command(text)
        if command:
            handle_content_command(event, command)
            return
        
        # معالجة طلب تكملة القصة
        if text_lower in ["كمل", "كمل القصة", "التكملة", "استمر"]:
            handle_story_continuation(event, user_id)
            return
        
        # معالجة طلب الألعاب
        if text_lower in ["لعبه", "لعبة", "العاب", "ألعاب", "game"]:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=get_games_list())
            )
            return
        
        # معالجة اختيار اللعبة
        if text.isdigit():
            handle_game_selection(event, user_id, int(text))
            return
        
        # معالجة إجابات اللعبة
        if user_id in user_game_state:
            handle_game_answer(event, user_id, text)
            return
        
        # رسالة افتراضية
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="💫 اكتب 'قائمة' لعرض الخيارات المتاحة",
                quick_reply=create_main_menu()
            )
        )
        
    except Exception as e:
        logger.error(f"خطأ في معالجة الرسالة: {e}", exc_info=True)
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ حدث خطأ، يرجى المحاولة مرة أخرى")
            )
        except:
            pass

def handle_content_command(event, command: str):
    """معالجة أوامر المحتوى المطورة"""
    
    if command == "شعر":
        poem = content_manager.get_poem()
        if not poem:
            content = "⚠️ لا توجد قصائد متاحة حالياً."
        else:
            content = f"📖 {poem.get('title', 'قصيدة')}\n"
            content += f"✍️ {poem.get('poet', 'شاعر')}\n\n"
            content += f"{poem['text']}\n\n"
            if 'meaning' in poem:
                content += f"💡 {poem['meaning']}"
    
    elif command == "حكمة":
        quote = content_manager.get_quote()
        if not quote:
            content = "⚠️ لا توجد حكم متاحة حالياً."
        else:
            content = f"💡 {quote['text']}\n\n"
            if 'author' in quote and quote['author']:
                content += f"✍️ {quote['author']}"
    
    elif command == "قصة":
        story = content_manager.get_story()
        if not story:
            content = "⚠️ لا توجد قصص متاحة حالياً."
        else:
            user_story_state[event.source.user_id] = story
            content = f"📚 {story.get('title', 'قصة')}\n\n"
            content += f"{story['part1']}\n\n"
            if 'part2' in story:
                content += "💬 اكتب 'كمل' لقراءة التكملة"
    
    elif command == "اختيار":
        choice = content_manager.get_would_you_rather()
        if not choice:
            content = "⚠️ لا توجد أسئلة متاحة حالياً."
        else:
            content = f"🤔 هل تفضل:\n\n"
            content += f"🅰️ {choice['option_a']}\n\n"
            content += f"أم\n\n"
            content += f"🅱️ {choice['option_b']}\n\n"
            content += "💭 فكّر جيداً قبل الاختيار!"
    
    else:
        content = content_manager.get_content(command)
        if not content:
            content = f"⚠️ لا توجد بيانات متاحة في قسم '{command}' حالياً."
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=content, quick_reply=create_main_menu())
    )

def handle_story_continuation(event, user_id: str):
    """معالجة طلب تكملة القصة"""
    if user_id in user_story_state:
        story = user_story_state.pop(user_id)
        if 'part2' in story:
            msg = f"📚 تكملة القصة:\n\n{story['part2']}\n\n"
            if 'moral' in story:
                msg += f"🌟 العبرة:\n{story['moral']}"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=msg, quick_reply=create_main_menu())
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ لا توجد تكملة لهذه القصة")
            )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⚠️ لم تبدأ قصة بعد! اكتب 'قصة' للبدء")
        )

def handle_game_selection(event, user_id: str, num: int):
    """معالجة اختيار اللعبة"""
    if 1 <= num <= len(content_manager.games_list):
        game_index = num - 1
        user_game_state[user_id] = {
            "game_index": game_index,
            "question_index": 0,
            "answers": []
        }
        
        game = content_manager.games_list[game_index]
        first_q = game["questions"][0]
        options = "\n".join([f"{k}. {v}" for k, v in first_q["options"].items()])
        
        msg = f"🎮 {game.get('title', f'اللعبة {num}')}\n\n"
        msg += f"❓ {first_q['question']}\n\n{options}\n\n📝 أرسل: أ، ب، ج"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=msg)
        )

def handle_game_answer(event, user_id: str, text: str):
    """معالجة إجابة اللعبة"""
    state = user_game_state[user_id]
    answer_map = {"1": "أ", "2": "ب", "3": "ج", "a": "أ", "b": "ب", "c": "ج"}
    answer = answer_map.get(text.lower(), text)
    
    if answer in ["أ", "ب", "ج"]:
        state["answers"].append(answer)
        game = content_manager.games_list[state["game_index"]]
        state["question_index"] += 1
        
        if state["question_index"] < len(game["questions"]):
            q = game["questions"][state["question_index"]]
            options = "\n".join([f"{k}. {v}" for k, v in q["options"].items()])
            progress = f"[{state['question_index'] + 1}/{len(game['questions'])}]"
            msg = f"{progress} ❓ {q['question']}\n\n{options}\n\n📝 أرسل: أ، ب، ج"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=msg)
            )
        else:
            result = calculate_result(state["answers"], state["game_index"])
            final_msg = f"🎉 انتهت اللعبة!\n\n{result}\n\n💬 أرسل 'لعبه' لتجربة لعبة أخرى!"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=final_msg, quick_reply=create_main_menu())
            )
            del user_game_state[user_id]

# === تشغيل التطبيق ===
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"البوت المطور يعمل على المنفذ {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

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
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
    QuickReply, QuickReplyButton, MessageAction, PostbackEvent,
    RichMenu, RichMenuSize, RichMenuArea, RichMenuBounds, URIAction
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
        self.arab_poets: List[dict] = []  # قصائد الشعراء العرب
        self.quotes_list: List[dict] = []
        self.stories_list: List[dict] = []
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
            "شعر": [], "قصيدة": [], "حكمة": [], "قصة": []
        }
        
        # تحميل المحتوى الإضافي
        self.poems_list = self.load_json_file("poems.json")
        self.arab_poets = self.load_json_file("arab_poets.json")  # قصائد الشعراء العرب
        self.quotes_list = self.load_json_file("quotes.json")
        self.stories_list = self.load_json_file("stories.json")
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
    
    def get_arab_poem(self) -> Optional[dict]:
        """الحصول على قصيدة لشاعر عربي"""
        if not self.arab_poets:
            return None
        
        index = self.get_random_index("قصيدة", len(self.arab_poets))
        return self.arab_poets[index]
    
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
    "شعر": ["شعر", "ابيات"],
    "قصيدة": ["قصيدة", "قصيده", "شاعر", "شعراء"],
    "حكمة": ["حكمة", "حكم", "اقتباس", "اقتباسات"],
    "قصة": ["قصة", "قصه", "حكاية"]
}

def find_command(text: str) -> Optional[str]:
    """البحث عن الأمر المطابق"""
    text_lower = text.lower().strip()
    for key, variants in COMMANDS_MAP.items():
        if text_lower in [v.lower() for v in variants]:
            return key
    return None

# === Flex Messages للعرض الاحترافي ===

def create_welcome_flex() -> dict:
    """إنشاء رسالة ترحيب احترافية بتصميم Flex"""
    return {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "مرحباً بك",
                            "weight": "bold",
                            "size": "xxl",
                            "align": "center",
                            "color": "#1a1a1a"
                        },
                        {
                            "type": "text",
                            "text": "في بوت الأسئلة والأشعار",
                            "size": "md",
                            "align": "center",
                            "color": "#666666",
                            "margin": "md"
                        }
                    ],
                    "paddingBottom": "20px"
                },
                {
                    "type": "separator",
                    "color": "#d9d9d9"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "الميزات المتاحة",
                            "weight": "bold",
                            "size": "lg",
                            "color": "#1a1a1a",
                            "margin": "lg"
                        },
                        create_feature_box("💭", "أسئلة عميقة", "اكتشف أسئلة مثيرة للتفكير"),
                        create_feature_box("🎯", "تحديات", "تحديات ممتعة ومشوقة"),
                        create_feature_box("💬", "اعترافات", "شارك اعترافاتك بصراحة"),
                        create_feature_box("📖", "قصائد الشعراء", "قصائد من كبار الشعراء العرب"),
                        create_feature_box("✨", "أبيات شعرية", "أشعار منوعة وجميلة"),
                        create_feature_box("💡", "حكم واقتباسات", "حكم ملهمة من التراث"),
                        create_feature_box("📚", "قصص", "قصص هادفة وممتعة"),
                        create_feature_box("🎮", "ألعاب شخصية", "اكتشف شخصيتك")
                    ],
                    "spacing": "sm",
                    "margin": "lg"
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#ffffff"
        },
        "styles": {
            "body": {
                "separator": True
            }
        }
    }

def create_feature_box(emoji: str, title: str, desc: str) -> dict:
    """إنشاء صندوق ميزة"""
    return {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            {
                "type": "text",
                "text": emoji,
                "size": "xl",
                "flex": 0
            },
            {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": title,
                        "weight": "bold",
                        "size": "sm",
                        "color": "#1a1a1a"
                    },
                    {
                        "type": "text",
                        "text": desc,
                        "size": "xs",
                        "color": "#8c8c8c",
                        "wrap": True
                    }
                ],
                "spacing": "xs",
                "margin": "md"
            }
        ],
        "spacing": "md",
        "margin": "md"
    }

def create_content_flex(title: str, content: str, emoji: str, footer: str = None) -> dict:
    """إنشاء Flex Message لعرض المحتوى"""
    contents = [
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": emoji,
                    "size": "xxl",
                    "flex": 0,
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1a1a1a",
                    "margin": "md",
                    "wrap": True
                }
            ],
            "paddingBottom": "15px"
        },
        {
            "type": "separator",
            "color": "#d9d9d9"
        },
        {
            "type": "text",
            "text": content,
            "size": "md",
            "color": "#333333",
            "wrap": True,
            "margin": "lg",
            "lineSpacing": "8px"
        }
    ]
    
    if footer:
        contents.extend([
            {
                "type": "separator",
                "color": "#d9d9d9",
                "margin": "lg"
            },
            {
                "type": "text",
                "text": footer,
                "size": "sm",
                "color": "#8c8c8c",
                "margin": "md",
                "align": "center",
                "wrap": True
            }
        ])
    
    return {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": contents,
            "paddingAll": "20px",
            "backgroundColor": "#ffffff"
        }
    }

def create_poem_flex(poem: dict) -> dict:
    """إنشاء Flex Message للقصائد"""
    title = poem.get('title', 'قصيدة')
    poet = poem.get('poet', 'شاعر')
    text = poem.get('text', '')
    meaning = poem.get('meaning', '')
    era = poem.get('era', '')  # العصر
    
    footer_text = f"✍️ {poet}"
    if era:
        footer_text += f" • {era}"
    if meaning:
        footer_text += f"\n\n💡 {meaning}"
    
    return create_content_flex(title, text, "📖", footer_text)

def create_quote_flex(quote: dict) -> dict:
    """إنشاء Flex Message للحكم"""
    text = quote.get('text', '')
    author = quote.get('author', '')
    
    footer = f"— {author}" if author else None
    
    return create_content_flex("حكمة", text, "💡", footer)

def create_story_flex(story: dict, show_continue: bool = True) -> dict:
    """إنشاء Flex Message للقصص"""
    title = story.get('title', 'قصة')
    part1 = story.get('part1', '')
    
    footer = "💬 اضغط على زر 'التكملة' لقراءة بقية القصة" if show_continue and 'part2' in story else None
    
    return create_content_flex(title, part1, "📚", footer)

def create_games_list_flex() -> dict:
    """قائمة الألعاب بتصميم Flex"""
    if not content_manager.games_list:
        return None
    
    games_boxes = []
    for i, game in enumerate(content_manager.games_list[:10]):  # حد أقصى 10 ألعاب
        games_boxes.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": f"{i+1}",
                    "size": "lg",
                    "weight": "bold",
                    "color": "#ffffff",
                    "align": "center",
                    "flex": 0,
                    "backgroundColor": "#1a1a1a",
                    "paddingAll": "8px",
                    "cornerRadius": "5px"
                },
                {
                    "type": "text",
                    "text": game.get('title', f'اللعبة {i+1}'),
                    "size": "md",
                    "color": "#1a1a1a",
                    "margin": "md",
                    "wrap": True,
                    "weight": "bold"
                }
            ],
            "margin": "md",
            "action": {
                "type": "message",
                "label": game.get('title', f'اللعبة {i+1}'),
                "text": str(i+1)
            }
        })
    
    return {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "🎮 الألعاب المتاحة",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1a1a1a"
                },
                {
                    "type": "separator",
                    "color": "#d9d9d9",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": games_boxes,
                    "spacing": "sm",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "اضغط على اللعبة للبدء",
                    "size": "xs",
                    "color": "#8c8c8c",
                    "margin": "lg",
                    "align": "center"
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#ffffff"
        }
    }

# === Rich Menu (القائمة الثابتة) ===

def create_rich_menu():
    """إنشاء Rich Menu للبوت"""
    try:
        # حذف القوائم القديمة
        rich_menu_list = line_bot_api.get_rich_menu_list()
        for menu in rich_menu_list:
            line_bot_api.delete_rich_menu(menu.rich_menu_id)
        
        # إنشاء القائمة الجديدة
        rich_menu = RichMenu(
            size=RichMenuSize(width=2500, height=1686),
            selected=True,
            name="القائمة الرئيسية",
            chat_bar_text="القائمة",
            areas=[
                # الصف الأول
                RichMenuArea(
                    bounds=RichMenuBounds(x=0, y=0, width=833, height=843),
                    action=MessageAction(text="سؤال")
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=833, y=0, width=834, height=843),
                    action=MessageAction(text="تحدي")
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1667, y=0, width=833, height=843),
                    action=MessageAction(text="اعتراف")
                ),
                # الصف الثاني
                RichMenuArea(
                    bounds=RichMenuBounds(x=0, y=843, width=625, height=843),
                    action=MessageAction(text="قصيدة")
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=625, y=843, width=625, height=843),
                    action=MessageAction(text="شعر")
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1250, y=843, width=625, height=843),
                    action=MessageAction(text="حكمة")
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1875, y=843, width=625, height=843),
                    action=MessageAction(text="قصة")
                )
            ]
        )
        
        rich_menu_id = line_bot_api.create_rich_menu(rich_menu=rich_menu)
        
        # ملاحظة: يجب رفع صورة القائمة بشكل منفصل
        # line_bot_api.set_rich_menu_image(rich_menu_id, 'image/png', open('rich_menu.png', 'rb'))
        
        # تعيين القائمة كافتراضية
        line_bot_api.set_default_rich_menu(rich_menu_id)
        
        logger.info(f"تم إنشاء Rich Menu: {rich_menu_id}")
        return rich_menu_id
        
    except Exception as e:
        logger.error(f"خطأ في إنشاء Rich Menu: {e}")
        return None

# === Routes ===
@app.route("/", methods=["GET"])
def home():
    return "✅ البوت المطور يعمل بنجاح!", 200

@app.route("/health", methods=["GET"])
def health_check():
    return {"status": "healthy", "service": "enhanced-line-bot-v2"}, 200

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
            flex_message = FlexSendMessage(
                alt_text="مرحباً بك في البوت",
                contents=create_welcome_flex()
            )
            line_bot_api.reply_message(event.reply_token, flex_message)
            return
        
        # معالجة الأوامر الأساسية
        command = find_command(text)
        if command:
            handle_content_command(event, command)
            return
        
        # معالجة طلب تكملة القصة
        if text_lower in ["كمل", "كمل القصة", "التكملة", "استمر", "تكملة"]:
            handle_story_continuation(event, user_id)
            return
        
        # معالجة طلب الألعاب
        if text_lower in ["لعبه", "لعبة", "العاب", "ألعاب", "game"]:
            flex = create_games_list_flex()
            if flex:
                line_bot_api.reply_message(
                    event.reply_token,
                    FlexSendMessage(alt_text="الألعاب المتاحة", contents=flex)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠️ لا توجد ألعاب متاحة حالياً")
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
            TextSendMessage(text="💫 اكتب 'قائمة' لعرض الخيارات المتاحة\nأو استخدم القائمة الثابتة أسفل الشاشة")
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
    """معالجة أوامر المحتوى بتصميم Flex"""
    
    try:
        if command == "شعر":
            poem = content_manager.get_poem()
            if not poem:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠️ لا توجد أبيات شعرية متاحة حالياً")
                )
                return
            
            flex = create_poem_flex(poem)
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text=poem.get('title', 'قصيدة'), contents=flex)
            )
        
        elif command == "قصيدة":
            poem = content_manager.get_arab_poem()
            if not poem:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠️ لا توجد قصائد متاحة حالياً")
                )
                return
            
            flex = create_poem_flex(poem)
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text=poem.get('title', 'قصيدة'), contents=flex)
            )
        
        elif command == "حكمة":
            quote = content_manager.get_quote()
            if not quote:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠️ لا توجد حكم متاحة حالياً")
                )
                return
            
            flex = create_quote_flex(quote)
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text="حكمة", contents=flex)
            )
        
        elif command == "قصة":
            story = content_manager.get_story()
            if not story:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠️ لا توجد قصص متاحة حالياً")
                )
                return
            
            user_story_state[event.source.user_id] = story
            flex = create_story_flex(story, show_continue='part2' in story)
            
            messages = [FlexSendMessage(alt_text=story.get('title', 'قصة'), contents=flex)]
            
            # إضافة زر التكملة
            if 'part2' in story:
                quick_reply = QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="📖 التكملة", text="تكملة"))
                ])
                messages.append(TextSendMessage(text=".", quick_reply=quick_reply))
            
            line_bot_api.reply_message(event.reply_token, messages)
        
        else:
            # الأوامر النصية العادية
            content = content_manager.get_content(command)
            if not content:
                content = f"⚠️ لا توجد بيانات متاحة في قسم '{command}' حالياً"
            
            # تنسيق المحتوى
            emoji_map = {
                "سؤال": "💭",
                "تحدي": "🎯",
                "اعتراف": "💬",
                "أكثر": "✨"
            }
            
            emoji = emoji_map.get(command, "📌")
            flex = create_content_flex(command, content, emoji)
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text=command, contents=flex)
            )
    
    except Exception as e:
        logger.error(f"خطأ في معالجة الأمر {command}: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⚠️ حدث خطأ في عرض المحتوى")
        )

def handle_story_continuation(event, user_id: str):
    """معالجة طلب تكملة القصة"""
    if user_id in user_story_state:
        story = user_story_state.pop(user_id)
        if 'part2' in story:
            part2 = story['part2']
            moral = story.get('moral', '')
            
            full_text = part2
            if moral:
                full_text += f"\n\n🌟 العبرة:\n{moral}"
            
            flex = create_content_flex("تكملة القصة", full_text, "📚")
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text="تكملة القصة", contents=flex)
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
        msg += f"❓ {first_q['question']}\n\n{options}\n\n"
        msg += f"━━━━━━━━━━━━━\n📝 أرسل: أ، ب، أو ج"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=msg)
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⚠️ رقم اللعبة غير صحيح")
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
            
            msg = f"{progress} ❓ {q['question']}\n\n{options}\n\n"
            msg += f"━━━━━━━━━━━━━\n📝 أرسل: أ، ب، أو ج"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=msg)
            )
        else:
            result = calculate_result(state["answers"], state["game_index"])
            
            # إنشاء Flex للنتيجة
            flex = {
                "type": "bubble",
                "size": "mega",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🎉 النتيجة",
                            "weight": "bold",
                            "size": "xxl",
                            "align": "center",
                            "color": "#1a1a1a"
                        },
                        {
                            "type": "separator",
                            "color": "#d9d9d9",
                            "margin": "lg"
                        },
                        {
                            "type": "text",
                            "text": result,
                            "size": "md",
                            "color": "#333333",
                            "wrap": True,
                            "margin": "lg",
                            "lineSpacing": "8px"
                        },
                        {
                            "type": "separator",
                            "color": "#d9d9d9",
                            "margin": "lg"
                        },
                        {
                            "type": "text",
                            "text": "💬 أرسل 'لعبة' لتجربة لعبة أخرى",
                            "size": "sm",
                            "color": "#8c8c8c",
                            "margin": "md",
                            "align": "center"
                        }
                    ],
                    "paddingAll": "20px",
                    "backgroundColor": "#ffffff"
                }
            }
            
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text="نتيجة اللعبة", contents=flex)
            )
            del user_game_state[user_id]
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⚠️ الرجاء الإجابة بـ: أ، ب، أو ج")
        )

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

# === تشغيل التطبيق ===
if __name__ == "__main__":
    # محاولة إنشاء Rich Menu
    try:
        create_rich_menu()
    except Exception as e:
        logger.warning(f"لم يتم إنشاء Rich Menu: {e}")
    
    port = int(os.getenv("PORT", 5000))
    logger.info(f"البوت المطور يعمل على المنفذ {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

# cogs/qotd.py
import discord
from discord.ext import commands, tasks
import datetime
import aiosqlite
import random
import asyncio

# =================================================================================
# === DANH SÁCH CÂU HỎI MỚI - PHONG CÁCH GENZ, HÀI HƯỚC, BẮT TREND ===
# =================================================================================
DEFAULT_QUESTIONS = [
    # --- Check Vibe & Slang ---
    "What's up Homies? Cuối tuần này có kèo gì 'cháy' không?",
    "Hey bro, kể một 'red flag' của bản thân mà bạn vẫn thấy mình 'slay'.",
    "Real talk: Giữa việc 'hít drama' và 'tạo drama', bạn hợp hệ nào hơn?",
    "Drop a song that's been on repeat in your playlist recently.",
    "Nếu phải miêu tả 'vibe' của crush bạn bằng một bài hát, đó sẽ là bài gì?",
    "Kể tên một bộ phim 'overrated' (được đánh giá quá cao) theo ý kiến của bạn.",

    # --- Hài Hước & Tình Huống Khó Đỡ ---
    "Nếu phải từ bỏ vĩnh viễn một trong hai: Lướt TikTok hoặc ăn đồ chiên rán, bạn chọn 'bay màu' cái nào?",
    "Kể về lần 'muối mặt' nhất trong đời bạn.",
    "Nếu điện thoại của bạn bỗng dưng đọc to tất cả những gì bạn search trong 24h qua, bạn sẽ 'toang' đến mức nào?",
    "Nếu có 1 tỷ VNĐ nhưng phải nghe 'Baby Shark' 8 tiếng mỗi ngày trong 1 năm, bạn có chốt kèo không?",
    "Kể tên một 'plot twist' trong đời thực của bạn mà biên kịch phim cũng phải chào thua.",
    "Thú nhận đi, bạn đã bao giờ giả vờ bận để từ chối một chiếc kèo 'chán phèo' chưa?",
    "Nếu crush 'seen' tin nhắn của bạn không 'rep', 'con ma' nào sẽ nhập bạn?",

    # --- Giả Tưởng & Độc Lạ ---
    "Bạn được trao quyền xóa sổ một món ăn khỏi thế giới vĩnh viễn, bạn sẽ chọn món nào?",
    "Nếu cuộc đời bạn là một tựa game, nó sẽ thuộc thể loại gì? (RPG, kinh dị, hài hước,...)",
    "Nếu phải sống trong một bộ phim hoạt hình, bạn sẽ chọn phim nào?",
    "Giữa việc nói chuyện được với động vật và việc biết tất cả các ngôn ngữ trên thế giới, bạn chọn năng lực nào?",
    "Nếu tài khoản ngân hàng của bạn đột nhiên có số tiền bằng với số % pin hiện tại của điện thoại (tính theo triệu VNĐ), bạn sẽ làm gì?",

    # --- Thảo Luận & "Deep" Nhẹ ---
    "Đâu là lời khuyên 'tổn thương' nhất nhưng lại 'hữu ích' nhất bạn từng nhận được?",
    "Nếu được đổi một thói quen xấu lấy một kỹ năng xịn, bạn sẽ đổi gì và lấy gì?",
    "Kể về một lần bạn 'flex' về thành tích của mình và cảm thấy cực kỳ tự hào.",
    "Mô tả 'vibe' của server này bằng 3 emoji.",
    "Điều gì bạn từng rất tin tưởng khi còn nhỏ nhưng giờ nhận ra nó 'ảo ma canada'?",
]

DB_NAME = 'bot_data.db'


class QOTD(commands.Cog):
    """❓ Tự động đặt nhiều câu hỏi trong ngày để tăng tương tác."""
    COG_EMOJI = "❓"

    def __init__(self, bot):
        self.bot = bot
        self.VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
        self.daily_q_count = {}  # Lưu số câu hỏi đã gửi trong ngày cho mỗi guild
        self.last_sent_time = {}  # Lưu thời gian gửi cuối cùng cho mỗi guild
        self.reset_q_count.start()  # Task mới để reset số đếm mỗi ngày
        self.send_qotd_randomly.start()  # Task chính để gửi câu hỏi ngẫu nhiên

    def cog_unload(self):
        self.send_qotd_randomly.cancel()
        self.reset_q_count.cancel()

    async def initialize_questions(self):
        """Thêm các câu hỏi mặc định vào DB nếu chưa có."""
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT question_text FROM qotd") as cursor:
                existing_questions = {row[0] for row in await cursor.fetchall()}

            new_questions = [
                (q,) for q in DEFAULT_QUESTIONS if q not in existing_questions]

            if new_questions:
                await db.executemany("INSERT INTO qotd (question_text) VALUES (?)", new_questions)
                await db.commit()
                print(
                    f"[QOTD] Đã thêm {len(new_questions)} câu hỏi mới vào database.")

    async def get_random_question(self):
        """Lấy một câu hỏi ngẫu nhiên chưa được sử dụng từ DB."""
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM qotd WHERE is_used = 0") as cursor:
                unused_questions = await cursor.fetchall()

            if not unused_questions:
                await db.execute("UPDATE qotd SET is_used = 0")
                await db.commit()
                print(
                    "[QOTD] Tất cả câu hỏi đã được sử dụng. Đang reset lại danh sách.")
                async with db.execute("SELECT * FROM qotd WHERE is_used = 0") as cursor:
                    unused_questions = await cursor.fetchall()

            if not unused_questions:
                return None

            chosen_question = random.choice(unused_questions)

            await db.execute("UPDATE qotd SET is_used = 1 WHERE question_id = ?", (chosen_question['question_id'],))
            await db.commit()

            return chosen_question['question_text']

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone(datetime.timedelta(hours=7))))
    async def reset_q_count(self):
        self.daily_q_count = {}
        print("[QOTD] Đã reset số lượng câu hỏi trong ngày cho tất cả servers.")

    @tasks.loop(minutes=5)
    async def send_qotd_randomly(self):
        MAX_QUESTIONS_PER_DAY = 3
        MIN_INTERVAL_SECONDS = 2 * 3600  # 2 tiếng

        now_vn = datetime.datetime.now(self.VN_TZ)

        for guild in self.bot.guilds:
            guild_q_count = self.daily_q_count.get(guild.id, 0)
            if guild_q_count >= MAX_QUESTIONS_PER_DAY:
                continue

            last_sent = self.last_sent_time.get(guild.id)
            if last_sent and (now_vn - last_sent).total_seconds() < MIN_INTERVAL_SECONDS:
                continue

            if random.randint(1, 12) == 1:
                await self._send_single_qotd_to_guild(guild)
                self.daily_q_count[guild.id] = guild_q_count + 1
                self.last_sent_time[guild.id] = now_vn

    async def _send_single_qotd_to_guild(self, guild: discord.Guild):
        """Hàm gửi một câu hỏi QOTD đến một guild cụ thể."""
        question_text = await self.get_random_question()
        if not question_text:
            print(f"[QOTD] Guild {guild.name}: Không có câu hỏi nào để gửi.")
            return

        try:
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT main_chat_channel_id FROM server_configs WHERE guild_id = ?", (guild.id,)) as cursor:
                    config_row = await cursor.fetchone()

            if config_row and config_row[0]:
                target_channel = self.bot.get_channel(config_row[0])
                if target_channel:
                    embed = discord.Embed(
                        title="❓ CÂU HỎI TRONG NGÀY ❓",
                        description=f"### {question_text}",
                        color=discord.Color.random(),
                        timestamp=datetime.datetime.now(datetime.timezone.utc)
                    )
                    embed.set_footer(text="Anh em vào 'chém' cho vui!")

                    try:
                        await target_channel.send(content="@everyone", embed=embed, allowed_mentions=discord.AllowedMentions(everyone=True))
                        print(
                            f"[QOTD] Đã gửi câu hỏi mới đến #{target_channel.name} của server {guild.name}.")
                    except discord.Forbidden:
                        print(
                            f"[QOTD] Bot không có quyền gửi tin nhắn hoặc ping @everyone trong kênh #{target_channel.name} của server {guild.name}.")
        except Exception as e:
            print(f"[QOTD] Lỗi khi xử lý cho server {guild.name}: {e}")

    @send_qotd_randomly.before_loop
    async def before_send_qotd_randomly(self):
        await self.bot.wait_until_ready()
        await self.initialize_questions()
        print("[QOTD] Task gửi câu hỏi ngẫu nhiên đã sẵn sàng.")

    @reset_q_count.before_loop
    async def before_reset_q_count(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(QOTD(bot))

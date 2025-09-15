# cogs/trivia.py
import discord
from discord.ext import commands, tasks
import database as db
import random
import datetime
import asyncio
import json

try:
    from .economy import SHOP_ITEMS
except (ImportError, SystemError):
    SHOP_ITEMS = {}

class TriviaView(discord.ui.View):
    def __init__(self, question_data: dict = None, rewards: dict = None):
        super().__init__(timeout=None)
        
        # Gán giá trị mặc định nếu không được cung cấp
        self.question_data = question_data or {}
        self.rewards = rewards or {}
        
        # Chỉ xử lý khi có dữ liệu câu hỏi thực sự
        if self.question_data:
            self.correct_answer = self.question_data.get('correct')
            
            # Trộn và tạo nút bấm
            options = self.question_data.get('options', [])
            if options: # Đảm bảo options không rỗng
                shuffled_options = random.sample(options, len(options))
                for option in shuffled_options:
                    button = self.create_button(option, (option == self.correct_answer))
                    self.add_item(button)

    def create_button(self, label: str, is_correct: bool):
        async def button_callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            
            trivia_session = await db.get_active_trivia(interaction.message.id)
            if not trivia_session:
                await interaction.followup.send("Câu đố này đã kết thúc hoặc không còn hợp lệ.", ephemeral=True)
                for item in self.children: item.disabled = True
                try: await interaction.message.edit(view=self)
                except discord.NotFound: pass
                return

            answered_users = json.loads(trivia_session['answered_users_json'])
            if interaction.user.id in answered_users:
                await interaction.followup.send("Bạn đã trả lời câu hỏi này rồi!", ephemeral=True)
                return
            
            await db.update_answered_users(interaction.message.id, interaction.user.id)
            
            if is_correct:
                reward_texts = []
                if self.rewards.get('coins', 0) > 0:
                    await db.update_coins(interaction.user.id, interaction.guild.id, self.rewards['coins'])
                    reward_texts.append(f"**{self.rewards['coins']:,}** coin")
                if self.rewards.get('xp', 0) > 0:
                    await db.update_user_xp(interaction.user.id, interaction.guild.id, self.rewards['xp'])
                    reward_texts.append(f"**{self.rewards['xp']}** XP")
                if self.rewards.get('item_id'):
                    await db.add_item_to_inventory(interaction.user.id, interaction.guild.id, self.rewards['item_id'], 1)
                    item_name = SHOP_ITEMS.get(self.rewards['item_id'], {}).get('name', self.rewards['item_id'])
                    reward_texts.append(f"vật phẩm **{item_name}**")
                
                response_message = f"🎉 Chính xác! Bạn nhận được {', '.join(reward_texts)}."
                await interaction.followup.send(response_message, ephemeral=True)
            else:
                await interaction.followup.send(f"Rất tiếc, đó không phải là câu trả lời đúng.", ephemeral=True)

        # Sử dụng custom_id để bot có thể nhận diện nút bấm sau khi restart
        btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=f"trivia_{label.replace(' ', '_')}")
        btn.callback = button_callback
        return btn

class Trivia(commands.Cog):
    """❓ Gửi các câu đố vui ngẫu nhiên để tăng tương tác."""
    COG_EMOJI = "❓"

    def __init__(self, bot):
        self.bot = bot
        # Khởi tạo view rỗng để bot nhận diện các nút bấm sau khi restart
        self.bot.add_view(TriviaView()) 
        self.send_trivia_randomly.start()

    def cog_unload(self):
        self.send_trivia_randomly.cancel()

    @tasks.loop(minutes=45)
    async def send_trivia_randomly(self):
        if random.randint(1, 3) != 1: return
        for guild in self.bot.guilds:
            try:
                await self._send_single_trivia_to_guild(guild)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"[Trivia] Lỗi khi xử lý cho server {guild.name}: {e}")

    async def _send_single_trivia_to_guild(self, guild: discord.Guild):
        question_data = await db.get_random_trivia_question()
        if not question_data: return

        config = await db.get_or_create_config(guild.id)
        target_channel_id = config.get('main_chat_channel_id')
        if not target_channel_id or not (target_channel := self.bot.get_channel(target_channel_id)):
            return

        rewards = {"coins": random.randint(150, 400), "xp": random.randint(20, 50), "item_id": "lottery_ticket" if random.random() < 0.05 and SHOP_ITEMS else None}
        embed = discord.Embed(title=f"🧠 CÂU ĐỐ VUI CÓ THƯỞNG 🧠", description=f"### {question_data['text']}", color=discord.Color.random())
        embed.set_footer(text=f"Lĩnh vực: {question_data['category']} | Trả lời đúng để nhận thưởng! (Hết hạn sau 24h)")
        
        view = TriviaView(question_data, rewards)
        try:
            message = await target_channel.send(content="@everyone", embed=embed, view=view, allowed_mentions=discord.AllowedMentions(everyone=True))
            
            expiry_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
            await db.add_active_trivia(message.id, guild.id, target_channel.id, question_data['correct'], expiry_time.isoformat())
            
            print(f"[Trivia] Đã gửi câu đố mới đến #{target_channel.name} của server {guild.name}.")
        except discord.Forbidden:
            print(f"[Trivia] Bot không có quyền gửi tin nhắn trong kênh #{target_channel.name}")

    @send_trivia_randomly.before_loop
    async def before_send_trivia_randomly(self):
        await self.bot.wait_until_ready()
        print("[Trivia] Task gửi câu đố vui ngẫu nhiên đã sẵn sàng.")

async def setup(bot):
    await bot.add_cog(Trivia(bot))
# cogs/quests.py
import discord
from discord.ext import commands
import database as db
import datetime

# --- PHÂN LOẠI NHIỆM VỤ ---
QUEST_CATEGORIES = {
    "💬 Hoạt Động Chung": ['CHAT', 'GIVE_COIN', 'CHECK_BALANCE'],
    # <--- THÊM VÀO ĐÂY
    "🎲 Mini-game": ['RPS_WIN', 'FLIP_WIN', 'BLACKJACK_WIN'],
    "💰 Kinh Tế & Giao Dịch": ['DAILY_COMMAND', 'COIN_SPEND', 'SHOP_BUY', 'BID_AUCTION', 'LOAN_TAKEN']
}


class QuestView(discord.ui.View):
    def __init__(self, author: discord.Member, quests: list, cog):
        super().__init__(timeout=180.0)
        self.author = author
        self.quests = quests
        self.cog = cog

        # Sắp xếp các nhiệm vụ đã hoàn thành lên trước để nút bấm gọn gàng hơn
        sorted_quests = sorted(quests, key=lambda q: not q['is_completed'])
        for quest in sorted_quests:
            if quest['is_completed']:
                button = discord.ui.Button(
                    label=f"Nhận thưởng '{quest['name']}'",
                    style=discord.ButtonStyle.green,
                    custom_id=quest['quest_id'],
                    emoji="🎁"
                )
                button.callback = self.claim_reward
                self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Đây không phải bảng nhiệm vụ của bạn!", ephemeral=True)
            return False
        return True

    async def claim_reward(self, interaction: discord.Interaction):
        quest_id = interaction.data['custom_id']

        # Lấy lại dữ liệu quest mới nhất từ DB để tránh lỗi "double-claim"
        current_quests = await db.get_user_quests(self.author.id, self.author.guild.id)
        quest_to_claim = next(
            (q for q in current_quests if q['quest_id'] == quest_id and q['is_completed']), None)

        if not quest_to_claim:
            await interaction.response.send_message("Nhiệm vụ không hợp lệ hoặc đã được nhận thưởng.", ephemeral=True)
            # Cập nhật lại giao diện để xóa nút bấm đã dùng
            await self.cog.send_quest_embed(interaction.message, self.author)
            return

        reward_coin = quest_to_claim['reward_coin']
        reward_xp = quest_to_claim['reward_xp']

        await db.update_coins(self.author.id, self.author.guild.id, reward_coin)
        await db.update_user_xp(self.author.id, self.author.guild.id, reward_xp)
        await db.claim_quest_reward(self.author.id, self.author.guild.id, quest_id)

        await interaction.response.send_message(f"🎉 Bạn đã nhận thành công **{reward_coin:,} coin** và **{reward_xp} XP** từ nhiệm vụ **'{quest_to_claim['name']}'**!", ephemeral=True)

        # Cập nhật lại giao diện sau khi nhận thưởng
        if interaction.message:
            await self.cog.send_quest_embed(interaction.message, self.author)


class Quests(commands.Cog):
    """📜 Hệ thống nhiệm vụ hàng ngày."""
    COG_EMOJI = "📜"

    def __init__(self, bot):
        self.bot = bot

    async def send_quest_embed(self, message_or_ctx, member: discord.Member):
    # """Hàm helper để tạo và gửi/sửa embed nhiệm vụ đã được nâng cấp giao diện."""
        user_quests = await db.get_user_quests(member.id, member.guild.id)

        embed = discord.Embed(
            title=f"📜 Bảng Nhiệm Vụ của {member.display_name}", color=member.color or discord.Color.blue())
        embed.set_footer(
            text="Nhiệm vụ sẽ được làm mới vào 8:00 sáng mỗi ngày.")

        if not user_quests:
            embed.description = "Bạn chưa có nhiệm vụ nào. Hãy chờ đến ngày mai nhé!"
        else:
            # Sắp xếp nhiệm vụ theo category
            categorized_quests = {category: []
                                for category in QUEST_CATEGORIES}
            other_quests = []

            for quest in user_quests:
                found_category = False
                for category, types in QUEST_CATEGORIES.items():
                    if quest['quest_type'] in types:
                        categorized_quests[category].append(quest)
                        found_category = True
                        break
                if not found_category:
                    other_quests.append(quest)

            # Hiển thị nhiệm vụ theo từng category
            for category, quests_in_category in categorized_quests.items():
                if not quests_in_category:
                    continue

                field_value = ""
                for quest in quests_in_category:
                    progress = quest['progress']
                    target = quest['target_value']

                    fill = '🟩'
                    empty = '⬛'
                    bar_len = 10
                    percent = min(1.0, progress /
                                target) if target > 0 else 1.0
                    progress_bar = f"`{fill * int(percent * bar_len)}{empty * (bar_len - int(percent * bar_len))}`"

                    status_icon = "✅" if quest['is_completed'] else "⏳"

                    field_value += (
                        f"{status_icon} **{quest['name']} ({min(progress, target):,}/{target:,}):** *{quest['description']}*\n"
                        f"> {progress_bar} **Thưởng:** {quest['reward_coin']:,} 🪙 • {quest['reward_xp']} ⭐\n\n"
                    )

                embed.add_field(name=f"**{category}**",
                                value=field_value.strip(), inline=False)

        view = QuestView(member, user_quests, self)

        # --- PHẦN SỬA LỖI LOGIC PHẢN HỒI ---
        if isinstance(message_or_ctx, discord.Message):
            # Trường hợp này xảy ra khi nhấn nút "Nhận thưởng", cần EDIT tin nhắn gốc.
            await message_or_ctx.edit(embed=embed, view=view)
        elif isinstance(message_or_ctx, commands.Context):
            # Trường hợp này là khi gọi lệnh /nhiemvu hoặc ?nhiemvu lần đầu.
            # ctx.send() sẽ tự động xử lý đúng cho cả slash và prefix command.
            await message_or_ctx.send(embed=embed, view=view, ephemeral=True)
        else:
            # Fallback an toàn, mặc dù ít khi xảy ra
            print(
                f"DEBUG: message_or_ctx is of unexpected type: {type(message_or_ctx)}")
            # Cố gắng gửi như một context
            try:
                await message_or_ctx.send(embed=embed, view=view, ephemeral=True)
            except Exception as e:
                print(f"Error in fallback send_quest_embed: {e}")

    @commands.hybrid_command(name="nhiemvu", aliases=['nv', 'quest', 'quests'], description="Xem bảng nhiệm vụ hàng ngày của bạn.")
    async def nhiemvu(self, ctx: commands.Context):
        await self.send_quest_embed(ctx, ctx.author)


async def setup(bot):
    await bot.add_cog(Quests(bot))

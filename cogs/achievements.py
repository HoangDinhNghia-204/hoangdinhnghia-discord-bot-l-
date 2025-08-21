# cogs/achievements.py
import discord
from discord.ext import commands
import datetime
import database as db
from .utils import checks
from discord import app_commands


class Achievements(commands.Cog):
    """🏆 Hệ thống Thành Tựu và các mục tiêu dài hạn."""
    COG_EMOJI = "🏆"

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="thanhtuu", aliases=['achievements', 'tt'], description="Xem bảng thành tựu của bạn hoặc người khác.")
    @app_commands.rename(member="tên")
    async def thanhtuu(self, ctx: commands.Context, member: discord.Member = None):
        """Xem bảng thành tựu của bạn hoặc người khác."""
        target = member or ctx.author
        user_achievements = await db.get_user_achievements(target.id, ctx.guild.id)

        if not user_achievements:
            await db.assign_all_achievements_to_user(target.id, ctx.guild.id)
            user_achievements = await db.get_user_achievements(
                target.id, ctx.guild.id)
            if not user_achievements:
                return await ctx.send("Không thể tải dữ liệu thành tựu cho người dùng này.", delete_after=10, ephemeral=True)

        embed = discord.Embed(
            title=f"Bảng Thành Tựu của {target.display_name}", color=target.color)
        embed.set_thumbnail(url=target.display_avatar.url)

        completed_list = []
        incomplete_list = []

        for ach in user_achievements:
            reward_parts = []
            if ach.get('reward_coin', 0) > 0:
                reward_parts.append(f"{ach['reward_coin']:,} 🪙")
            if ach.get('reward_xp', 0) > 0:
                reward_parts.append(f"{ach['reward_xp']} ⭐")

            reward_str = ""
            if reward_parts:
                reward_str = f"\n **Thưởng:** {' • '.join(reward_parts)}"

            if ach['unlocked_timestamp']:
                ts = int(datetime.datetime.fromisoformat(
                    ach['unlocked_timestamp']).timestamp())
                completed_list.append(
                    f"🏆 **{ach['name']}** - *{ach['description']}* (Đạt được <t:{ts}:R>)")
            else:
                progress = ach['progress']
                target_val = ach['target_value']

                fill = '🟩'
                empty = '⬛'
                bar_len = 10
                percent = min(1.0, progress /
                              target_val) if target_val > 0 else 1.0
                progress_bar = f"`{fill * int(percent * bar_len)}{empty * (bar_len - int(percent * bar_len))}`"

                incomplete_list.append(
                    f"⏳ **{ach['name']}**: *{ach['description']}*\n"
                    f"> {progress_bar} ({progress:,}/{target_val:,}) {reward_str}"
                )

        if completed_list:
            embed.add_field(name="✨ Thành Tựu Mới Mở Khóa",
                            value="\n".join(completed_list[:5]), inline=False)

        if incomplete_list:
            embed.add_field(name="🏃 Đang Phấn Đấu", value="\n\n".join(
                incomplete_list), inline=False)

        total_completed = len(completed_list)
        total_achievements = len(user_achievements)
        embed.set_footer(
            text=f"Hoàn thành: {total_completed}/{total_achievements} thành tựu")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Achievements(bot))

# cogs/profile.py
import discord
from discord.ext import commands
import database as db
import datetime
from .utils import checks
from discord import app_commands


class Profile(commands.Cog):
    """🖼️ Lệnh profile và các tùy chỉnh cá nhân."""
    COG_EMOJI = "🖼️"

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="profile", description="Xem thẻ hồ sơ của bạn hoặc thành viên khác.")
    @app_commands.rename(member="thanh_vien")
    async def profile(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author

        user_data = await db.get_or_create_user(target.id, ctx.guild.id)
        completed_badges = await db.get_user_completed_achievements(target.id, ctx.guild.id)
        loan_data = await db.get_loan(target.id, ctx.guild.id)

        # Sửa lỗi: Truyền tham số đúng thứ tự guild_id, user_id
        partner_id = await db.get_partner(ctx.guild.id, target.id)
        partner = ctx.guild.get_member(partner_id) if partner_id else None

        leaderboard_data = await db.get_leaderboard(ctx.guild.id, limit=1000)
        user_rank = "N/A"
        for i, rank_user in enumerate(leaderboard_data):
            if rank_user['user_id'] == target.id:
                user_rank = f"#{i + 1}"
                break

        embed = discord.Embed(
            title=f"Hồ Sơ Thành Viên: {target.name}",
            description=f"Thông tin chi tiết về **{target.display_name}** tại server.",
            color=target.color
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if target.joined_at:
            join_timestamp = int(target.joined_at.timestamp())
            join_text = f"**Tham gia server:** <t:{join_timestamp}:R>\n"
        else:
            join_text = ""

        create_timestamp = int(target.created_at.timestamp())
        top_role = target.top_role.mention if target.top_role.name != "@everyone" else "Không có"
        partner_text = f"**Bạn đời:** {partner.mention}\n" if partner else ""

        general_info = (
            f"**Danh hiệu:** {top_role}\n"
            f"{partner_text}"
            f"{join_text}"
            f"**Tạo tài khoản:** <t:{create_timestamp}:R>"
        )
        embed.add_field(name="👤 Thông Tin Chung",
                        value=general_info, inline=False)

        # ... (các field khác giữ nguyên) ...
        xp = user_data.get('xp', 0)
        level = user_data.get('level', 1)
        xp_needed = 5 * (level**2) + 50 * level + 100

        fill = '🟩'
        empty = '⬛'
        bar_len = 10
        percent = xp / xp_needed if xp_needed > 0 else 1.0
        progress = int(percent * bar_len)
        progress_bar = f"`{fill * progress}{empty * (bar_len - progress)}`"

        level_info = (
            f"**Level:** `{level}`\n"
            f"**XP:** `{int(xp):,}` / `{int(xp_needed):,}`\n"
            f"**Xếp hạng:** `{user_rank}`\n"
            f"{progress_bar} `({percent:.1%})`"
        )
        embed.add_field(name="⭐ Cấp Độ & Xếp Hạng",
                        value=level_info, inline=True)

        coins = user_data.get('coins', 0)
        loan_info_text = f"**Nợ:** `{loan_data['repayment_amount']:,}` 🪙" if loan_data else "**Nợ:** `Không có`"

        eco_info = (
            f"**Số dư:** `{coins:,}` 🪙\n"
            f"{loan_info_text}"
        )
        embed.add_field(name="💰 Tài Sản", value=eco_info, inline=True)

        if completed_badges:
            badge_list = [
                f"{b['badge_emoji']} **{b['name']}**" for b in completed_badges]
            badge_text = "\n".join(badge_list)
            embed.add_field(
                name=f"🏆 Thành tựu Đã Mở Khóa ({len(completed_badges)})", value=badge_text, inline=False)
        else:
            embed.add_field(name="🏆 Thành tựu",
                            value="*Chưa mở khóa Thành tựu nào.*", inline=False)

        embed.set_footer(
            text=f"ID: {target.id} • Yêu cầu bởi: {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Profile(bot))

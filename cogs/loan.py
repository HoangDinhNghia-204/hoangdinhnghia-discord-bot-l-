# cogs/loan.py
import discord
from discord.ext import commands
import datetime
import database as db
from .utils import checks
from discord import app_commands

# Lấy ConfirmationView từ cogs/fun.py
# Điều này giúp tránh định nghĩa lại class và giữ code DRY (Don't Repeat Yourself)
try:
    from .fun import ConfirmationView
except (ImportError, SystemError):
    # Fallback nếu không thể import trực tiếp (ví dụ khi chạy test riêng file)
    from fun import ConfirmationView


LOAN_CONFIG = {
    "MAX_LOAN": 5000,
    "INTEREST_RATE": 0.20,  # 20% lãi suất
    "REPAYMENT_DAYS": 3
}


class LoanSystem(commands.Cog):
    """💸 Hệ thống vay và trả nợ."""
    COG_EMOJI = "💸"

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        """Kiểm tra chung cho tất cả các lệnh trong Cog này."""
        config = await db.get_or_create_config(ctx.guild.id)
        if debtor_role_id := config.get('debtor_role_id'):
            if debtor_role := ctx.guild.get_role(debtor_role_id):
                # Cho phép người nợ dùng lệnh trano
                if debtor_role in ctx.author.roles and ctx.command.name != 'trano':
                    await ctx.send("Bạn đang trong tình trạng vỡ nợ! Dùng `/trano` để trả nợ trước khi dùng các lệnh khác.", delete_after=10, ephemeral=True)
                    return False
        return True

    @commands.hybrid_command(name="vay", description=f"Vay tiền từ ngân hàng (tối đa {LOAN_CONFIG['MAX_LOAN']:,} coin).")
    @app_commands.rename(amount="số_tiền_vay")
    async def vay(self, ctx: commands.Context, amount: int):
        if amount <= 0:
            return await ctx.send("Số tiền vay phải lớn hơn 0.", delete_after=10, ephemeral=True)
        if amount > LOAN_CONFIG["MAX_LOAN"]:
            return await ctx.send(f"Bạn chỉ có thể vay tối đa **{LOAN_CONFIG['MAX_LOAN']:,}** coin.", delete_after=10, ephemeral=True)

        if await db.get_loan(ctx.author.id, ctx.guild.id):
            return await ctx.send("Bạn đang có một khoản nợ chưa trả. Dùng `/trano` để trả nợ trước.", delete_after=10, ephemeral=True)

        repayment_amount = int(amount * (1 + LOAN_CONFIG["INTEREST_RATE"]))
        due_date = datetime.datetime.now(
            datetime.timezone.utc) + datetime.timedelta(days=LOAN_CONFIG["REPAYMENT_DAYS"])

        confirm_embed = discord.Embed(
            title="Xác Nhận Khoản Vay", color=discord.Color.yellow())
        confirm_embed.add_field(
            name="Số tiền vay", value=f"**{amount:,}** coin")
        confirm_embed.add_field(name="Số tiền phải trả",
                                value=f"**{repayment_amount:,}** coin")
        confirm_embed.add_field(
            name="Hạn trả", value=f"<t:{int(due_date.timestamp())}:F> (<t:{int(due_date.timestamp())}:R>)")

        view = ConfirmationView(ctx.author)
        msg = await ctx.send(embed=confirm_embed, view=view)

        await view.wait()
        if view.confirmed:
            await msg.edit(content=f"✅ Giao dịch thành công! Bạn đã vay **{amount:,}** coin.", embed=None, view=None)

            await db.update_coins(ctx.author.id, ctx.guild.id, amount)
            await db.create_loan(ctx.author.id, ctx.guild.id,
                                 repayment_amount, due_date.isoformat())

            await db.update_quest_progress(ctx.author.id, ctx.guild.id, 'LOAN_TAKEN')

            unlocked_loan = await db.update_achievement_progress(
                ctx.author.id, ctx.guild.id, 'LOAN_TAKEN')
            if unlocked_loan:
                for ach in unlocked_loan:
                    await ctx.channel.send(f"🏆 {ctx.author.mention} vừa mở khóa thành tựu mới: **{ach['name']}**! (+{ach['reward_coin']:,} coin, +{ach['reward_xp']} XP)", delete_after=30)

        elif view.confirmed is False:
            await msg.edit(content="Đã hủy giao dịch vay.", embed=None, view=None, delete_after=10)
        else:  # Timeout
            try:
                await msg.delete()
            except discord.NotFound:
                pass

    @commands.hybrid_command(name="trano", description="Trả nợ khoản vay hiện tại của bạn.")
    async def trano(self, ctx: commands.Context):
        loan = await db.get_loan(ctx.author.id, ctx.guild.id)
        if not loan:
            return await ctx.send("Bạn không có khoản nợ nào.", delete_after=10, ephemeral=True)

        user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        repayment_amount = loan['repayment_amount']

        if user_data['coins'] < repayment_amount:
            return await ctx.send(f"Bạn không đủ **{repayment_amount:,}** coin để trả nợ.", delete_after=10, ephemeral=True)

        await db.update_coins(ctx.author.id, ctx.guild.id, -repayment_amount)
        await db.delete_loan(ctx.author.id, ctx.guild.id)

        # Cập nhật thành tựu tiêu tiền khi trả nợ
        unlocked_spend = await db.update_achievement_progress(
            ctx.author.id, ctx.guild.id, 'COIN_SPEND', value_to_add=repayment_amount)
        if unlocked_spend:
            for ach in unlocked_spend:
                await ctx.channel.send(f"🏆 {ctx.author.mention} vừa mở khóa thành tựu mới: **{ach['name']}**! (+{ach['reward_coin']:,} coin, +{ach['reward_xp']} XP)", delete_after=30)

        config = await db.get_or_create_config(ctx.guild.id)
        if debtor_role_id := config.get('debtor_role_id'):
            if debtor_role := ctx.guild.get_role(debtor_role_id):
                if debtor_role in ctx.author.roles:
                    try:
                        await ctx.author.remove_roles(debtor_role, reason="Đã trả hết nợ")
                        await ctx.send(f"✅ Bạn đã trả nợ thành công khoản vay **{repayment_amount:,}** coin và được xóa khỏi danh sách vỡ nợ!")
                        return
                    except discord.Forbidden:
                        pass

        await ctx.send(f"✅ Bạn đã trả nợ thành công khoản vay **{repayment_amount:,}** coin!")

    @commands.hybrid_command(name="no", description="Kiểm tra tình trạng nợ của bạn hoặc người khác.")
    @app_commands.rename(member="thành_viên")
    async def no(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        loan = await db.get_loan(target.id, ctx.guild.id)

        if not loan:
            message = "Chúc mừng! Bạn không có nợ nần gì cả." if target == ctx.author else f"{target.display_name} không có khoản nợ nào."
            return await ctx.send(message, ephemeral=True)

        embed = discord.Embed(
            title=f"Tình Trạng Nợ Của {target.display_name}", color=discord.Color.red())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Số tiền phải trả",
                        value=f"**{loan['repayment_amount']:,}** coin")
        due_date_ts = int(datetime.datetime.fromisoformat(
            loan['due_date']).timestamp())
        embed.add_field(
            name="Hạn trả", value=f"<t:{due_date_ts}:F> (<t:{due_date_ts}:R>)")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(LoanSystem(bot))

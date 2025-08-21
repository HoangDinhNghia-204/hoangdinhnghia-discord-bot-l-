# cogs/social.py
import discord
from discord.ext import commands
import datetime
import database as db
from discord import app_commands

try:
    from .fun import ConfirmationView
except (ImportError, SystemError):
    from fun import ConfirmationView


class Social(commands.Cog):
    """💕 Các lệnh tương tác xã hội."""
    COG_EMOJI = "💕"

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="propose", description="Cầu hôn một thành viên khác.")
    @app_commands.rename(member="nguoi_ay")
    async def propose(self, ctx: commands.Context, member: discord.Member):
        if member == ctx.author:
            return await ctx.send("Bạn không thể tự cầu hôn chính mình!", ephemeral=True)
        if member.bot:
            return await ctx.send("Bạn không thể cầu hôn một con bot!", ephemeral=True)

        # Sửa lỗi: Truyền tham số đúng thứ tự guild_id, user_id
        author_partner_id = await db.get_partner(ctx.guild.id, ctx.author.id)
        if author_partner_id:
            partner = ctx.guild.get_member(author_partner_id)
            partner_mention = partner.display_name if partner else "một người nào đó"
            return await ctx.send(f"Bạn đã kết hôn với **{partner_mention}** rồi! Hãy dùng lệnh `/divorce` trước.", ephemeral=True)

        # Sửa lỗi: Truyền tham số đúng thứ tự guild_id, user_id
        member_partner_id = await db.get_partner(ctx.guild.id, member.id)
        if member_partner_id:
            return await ctx.send(f"{member.display_name} đã kết hôn với người khác.", ephemeral=True)

        view = ConfirmationView(member)
        proposal_msg = await ctx.send(f"{member.mention}, {ctx.author.mention} muốn cầu hôn bạn. Bạn có đồng ý không?", view=view)

        await view.wait()
        if view.confirmed is True:
            await db.create_marriage(ctx.guild.id, ctx.author.id, member.id)
            embed = discord.Embed(
                title="🎉 Chúc Mừng Hạnh Phúc! 🎉",
                description=f"{ctx.author.mention} và {member.mention} đã chính thức trở thành vợ chồng!",
                color=discord.Color.pink()
            )
            await proposal_msg.edit(content=None, embed=embed, view=None)
        elif view.confirmed is False:
            await proposal_msg.edit(content=f"{member.display_name} đã từ chối lời cầu hôn.💔", view=None, delete_after=15)
        else:
            await proposal_msg.edit(content="Lời cầu hôn đã hết hạn.", view=None, delete_after=10)

    @commands.hybrid_command(name="divorce", description="Kết thúc mối quan hệ hôn nhân hiện tại.")
    async def divorce(self, ctx: commands.Context):
        # Sửa lỗi: Truyền tham số đúng thứ tự guild_id, user_id
        partner_id = await db.get_partner(ctx.guild.id, ctx.author.id)
        if not partner_id:
            return await ctx.send("Bạn chưa kết hôn để có thể ly hôn.", ephemeral=True)

        partner = ctx.guild.get_member(partner_id)
        partner_mention = partner.mention if partner else f"Người dùng (ID: {partner_id})"

        view = ConfirmationView(ctx.author)
        divorce_msg = await ctx.send(f"{ctx.author.mention}, bạn có chắc chắn muốn ly hôn với {partner_mention} không?", view=view)

        await view.wait()
        if view.confirmed:
            await db.delete_marriage(ctx.guild.id, ctx.author.id, partner_id)
            await divorce_msg.edit(content=f"💔 {ctx.author.mention} và {partner_mention} đã chính thức đường ai nấy đi.", view=None)
        elif view.confirmed is False:
            await divorce_msg.edit(content="Đã hủy thao tác ly hôn.", view=None, delete_after=10)
        else:
            await divorce_msg.edit(content="Yêu cầu đã hết hạn.", view=None, delete_after=10)


async def setup(bot):
    await bot.add_cog(Social(bot))

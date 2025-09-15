# cogs/voice_creator.py
import discord
from discord.ext import commands
import database as db
from .utils import checks
import asyncio
from discord import app_commands


class VoiceCreator(commands.Cog):
    """🔊 Hệ thống tự động tạo kênh voice."""
    COG_EMOJI = "🔊"

    def __init__(self, bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        config = await db.get_or_create_config(member.guild.id)
        creator_channel_id = config.get('create_vc_channel_id')

        # --- Logic Xóa Kênh Tự Động (PHIÊN BẢN CẢI TIẾN) ---
        if before.channel and before.channel.id != creator_channel_id:
            is_temp_channel = await db.get_temp_vc_by_channel(before.channel.id)
            if is_temp_channel:
                await asyncio.sleep(1)
                try:
                    fresh_channel = await self.bot.fetch_channel(before.channel.id)
                    if len(fresh_channel.members) == 0:
                        try:
                            await fresh_channel.delete(reason="Kênh tạm thời không còn ai sử dụng.")
                            await db.remove_temp_vc(fresh_channel.id)
                            print(
                                f"Đã tự động xóa kênh tạm thời: {fresh_channel.name} (ID: {fresh_channel.id})")
                        except discord.Forbidden:
                            print(
                                f"Lỗi quyền: Bot không thể xóa kênh voice {fresh_channel.name}")
                        except discord.NotFound:
                            await db.remove_temp_vc(fresh_channel.id)
                except discord.NotFound:
                    await db.remove_temp_vc(before.channel.id)
                    return

        # --- Logic Tạo kênh (giữ nguyên như cũ) ---
        if after.channel and after.channel.id == creator_channel_id:
            guild = member.guild
            category = after.channel.category
            channel_name = f"┇﹢˚ও・🏠・{member.display_name} ᴛịɴʜ ᴛʜấᴛ"

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
                member: discord.PermissionOverwrite(
                    manage_channels=True, manage_roles=True, move_members=True,
                    mute_members=True, deafen_members=True
                )
            }

            try:
                new_channel = await guild.create_voice_channel(
                    name=channel_name, category=category, overwrites=overwrites,
                    rtc_region='singapore', reason=f"Tạo kênh tạm thời cho {member.name}"
                )
                await member.move_to(new_channel)
                await new_channel.edit(rtc_region='hongkong', reason="Tự động chuyển vùng mặc định")
                await db.add_temp_vc(guild.id, member.id, new_channel.id)

            except discord.Forbidden:
                print(
                    f"Lỗi: Bot không có quyền tạo kênh hoặc di chuyển thành viên trong server {guild.name}")
            except Exception as e:
                print(f"Lỗi không xác định khi tạo kênh voice: {e}")

    @commands.hybrid_group(name="kenhvoice", description="Nhóm lệnh cài đặt kênh voice tự động.")
    @checks.has_permissions(manage_guild=True)
    async def kenhvoice(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @kenhvoice.command(name="set", description="Đặt một kênh voice làm kênh 'Tạo phòng tự động'.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(channel="kênh_voice")
    async def set_creator_channel(self, ctx: commands.Context, channel: discord.VoiceChannel):
        await db.update_config(ctx.guild.id, 'create_vc_channel_id', channel.id)
        embed = discord.Embed(
            title="✅ Cài Đặt Thành Công",
            description=f"Đã đặt {channel.mention} làm kênh **Tạo Phòng Tự Động**.\nKhi thành viên tham gia kênh này, một phòng riêng sẽ được tạo cho họ.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed, ephemeral=True)

    @kenhvoice.command(name="unset", description="Tắt tính năng tạo phòng tự động.")
    @checks.has_permissions(manage_guild=True)
    async def unset_creator_channel(self, ctx: commands.Context):
        await db.update_config(ctx.guild.id, 'create_vc_channel_id', None)
        embed = discord.Embed(
            title="✅ Đã Tắt Tính Năng",
            description="Đã gỡ cài đặt kênh **Tạo Phòng Tự Động**. Tính năng này hiện không hoạt động.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(VoiceCreator(bot))

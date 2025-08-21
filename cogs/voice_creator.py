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

        # --- Logic Xóa Kênh Tự Động ---
        # Kiểm tra kênh người dùng vừa rời khỏi
        if before.channel and before.channel.id != creator_channel_id:
            # Kiểm tra xem kênh đó có phải là kênh tạm thời không
            is_temp_channel = await db.get_temp_vc_by_channel(before.channel.id)
            if is_temp_channel:
                # Nếu kênh trống sau khi người dùng rời đi
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="Kênh tạm thời không còn ai sử dụng.")
                        await db.remove_temp_vc(before.channel.id)
                    except discord.Forbidden:
                        print(
                            f"Lỗi: Bot không có quyền xóa kênh voice {before.channel.name}")
                    except discord.NotFound:
                        # Kênh có thể đã bị xóa thủ công
                        await db.remove_temp_vc(before.channel.id)

        if after.channel and after.channel.id == creator_channel_id:
            guild = member.guild
            category = after.channel.category

            channel_name = f"┇﹢˚ও・🏠・{member.display_name} ᴛịɴʜ ᴛʜấᴛ"

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
                member: discord.PermissionOverwrite(
                    # Cho phép quản lý (đổi tên, set limit)
                    manage_channels=True,
                    manage_roles=True,  # Cho phép quản lý quyền kênh
                    move_members=True,  # Cho phép kéo người khác
                    mute_members=True,  # Cho phép tắt mic
                    deafen_members=True  # Cho phép điếc
                )
            }

            try:
                # Tạo kênh voice mới
                new_channel = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Kênh tạm thời được tạo bởi {member.name}"
                )

                # Di chuyển người dùng vào kênh mới của họ
                await member.move_to(new_channel)

                # Lưu thông tin kênh mới vào database
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

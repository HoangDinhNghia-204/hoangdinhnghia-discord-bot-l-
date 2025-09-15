# cogs/stats.py
import discord
from discord.ext import commands, tasks
import database as db
from .utils import checks

class Stats(commands.Cog):
    """📊 Hệ thống tự động cập nhật số liệu server trên tên kênh."""
    COG_EMOJI = "📊"

    def __init__(self, bot):
        self.bot = bot
        self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    async def _update_guild_stats(self, guild: discord.Guild):
        """Hàm helper để cập nhật tất cả các kênh đếm cho một server cụ thể."""
        try:
            config = await db.get_or_create_config(guild.id)
            if not config: return

            total_members = guild.member_count
            bot_count = sum(1 for member in guild.members if member.bot)
            user_count = total_members - bot_count

            # Cập nhật kênh Tổng thành viên
            if channel_id := config.get('member_count_channel_id'):
                if channel := guild.get_channel(channel_id):
                    new_name = f"╭﹢˚ও・👑・All-Member: {total_members}"
                    if channel.name != new_name:
                        await channel.edit(name=new_name, reason="Cập nhật số liệu server")

            # Cập nhật kênh chỉ Người dùng
            if channel_id := config.get('user_count_channel_id'):
                if channel := guild.get_channel(channel_id):
                    new_name = f"┇﹢˚ও・🧘・Member: {user_count}"
                    if channel.name != new_name:
                        await channel.edit(name=new_name, reason="Cập nhật số liệu server")

            # Cập nhật kênh chỉ Bot
            if channel_id := config.get('bot_count_channel_id'):
                if channel := guild.get_channel(channel_id):
                    new_name = f"╰﹢˚ও・🤖 Bots: {bot_count}"
                    if channel.name != new_name:
                        await channel.edit(name=new_name, reason="Cập nhật số liệu server")
        except discord.Forbidden:
            print(f"[Stats] Bot thiếu quyền 'Manage Channels' trong server {guild.name}.")
        except Exception as e:
            print(f"[Stats] Lỗi khi cập nhật số liệu cho server {guild.name}: {e}")

    @tasks.loop(minutes=10)
    async def update_stats(self):
        """Tác vụ chạy nền, cập nhật số liệu cho tất cả các server mỗi 10 phút."""
        for guild in self.bot.guilds:
            await self._update_guild_stats(guild)

    @update_stats.before_loop
    async def before_update_stats(self):
        await self.bot.wait_until_ready()
        print("[Stats] Task cập nhật số liệu đã sẵn sàng.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Cập nhật ngay khi có thành viên mới."""
        await self._update_guild_stats(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Cập nhật ngay khi có thành viên rời đi."""
        await self._update_guild_stats(member.guild)

    @commands.hybrid_group(name="serverstats", description="Thiết lập các kênh đếm thành viên tự động.")
    @checks.has_permissions(manage_guild=True)
    async def serverstats(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    async def _setup_channel(self, ctx: commands.Context, channel_type: str, channel_name_template: str):
        """Hàm helper để tạo và thiết lập một kênh đếm."""
        # Tạo kênh voice mới
        try:
            # Vô hiệu hóa quyền kết nối cho @everyone
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(connect=False)
            }
            new_channel = await ctx.guild.create_voice_channel(
                name="Đang tải...", 
                overwrites=overwrites, 
                reason="Thiết lập kênh đếm thành viên"
            )
        except discord.Forbidden:
            return await ctx.send("❌ Bot thiếu quyền `Manage Channels` để tạo kênh mới.", ephemeral=True)

        # Lưu ID kênh vào database
        await db.update_config(ctx.guild.id, f'{channel_type}_count_channel_id', new_channel.id)

        # Cập nhật tên kênh lần đầu
        await self._update_guild_stats(ctx.guild)

        await ctx.send(f"✅ Đã tạo và thiết lập thành công kênh đếm **{channel_type.replace('_', ' ').title()}**.", ephemeral=True)

    @serverstats.command(name="setup", description="Tự động tạo và thiết lập cả 3 kênh đếm (Tổng, Người, Bot).")
    @checks.has_permissions(manage_guild=True)
    async def setup_all(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        await self._setup_channel(ctx, 'member', 'All Members')
        await self._setup_channel(ctx, 'user', 'Members')
        await self._setup_channel(ctx, 'bot', 'Bots')
        await ctx.followup.send("✅ Đã hoàn tất thiết lập hệ thống đếm thành viên!", ephemeral=True)

    @serverstats.command(name="disable", description="Tắt và xóa tất cả các kênh đếm thành viên.")
    @checks.has_permissions(manage_guild=True)
    async def disable_all(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        config = await db.get_or_create_config(ctx.guild.id)
        channel_ids_to_delete = [
            config.get('member_count_channel_id'),
            config.get('user_count_channel_id'),
            config.get('bot_count_channel_id')
        ]
        
        deleted_count = 0
        for channel_id in channel_ids_to_delete:
            if channel_id:
                if channel := ctx.guild.get_channel(channel_id):
                    try:
                        await channel.delete(reason="Tắt hệ thống đếm thành viên")
                        deleted_count += 1
                    except discord.Forbidden:
                        await ctx.followup.send(f"⚠️ Bot thiếu quyền để xóa kênh {channel.name}. Vui lòng xóa thủ công.", ephemeral=True)
        
        # Xóa cài đặt trong DB
        await db.update_config(ctx.guild.id, 'member_count_channel_id', None)
        await db.update_config(ctx.guild.id, 'user_count_channel_id', None)
        await db.update_config(ctx.guild.id, 'bot_count_channel_id', None)

        await ctx.followup.send(f"✅ Đã tắt và xóa **{deleted_count}** kênh đếm thành viên.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Stats(bot))
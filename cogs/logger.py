# cogs/logger.py
import discord
from discord.ext import commands
import datetime
import database as db
import asyncio


class Logger(commands.Cog):
    """Ghi lại các hoạt động quan trọng trong server."""
    COG_EMOJI = "📝"  # Thêm emoji cho đẹp trong lệnh /help

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dùng cache để tránh query database liên tục khi không cần
        self.log_channel_cache = {}
        # Cache tin nhắn để lấy nội dung khi bị xóa
        self.message_cache = {}

    async def get_log_channel(self, guild_id: int) -> discord.TextChannel | None:
        """Hàm helper để lấy kênh log, có sử dụng cache để tối ưu."""
        if guild_id in self.log_channel_cache:
            channel_id = self.log_channel_cache[guild_id]
            if channel_id:
                return self.bot.get_channel(channel_id)
            return None

        config = await db.get_or_create_config(guild_id)
        channel_id = config.get('log_channel_id')
        self.log_channel_cache[guild_id] = channel_id  # Cập nhật cache

        if channel_id:
            return self.bot.get_channel(channel_id)
        return None

    # --- SỰ KIỆN LOG TIN NHẮN ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Lưu tin nhắn và tệp đính kèm vào cache để có thể lấy lại khi bị xóa."""
        if not message.author.bot and message.guild:
            # Lấy danh sách URL của tất cả tệp đính kèm
            attachment_urls = [att.url for att in message.attachments]

            self.message_cache[message.id] = {
                'content': message.content,
                'author': message.author,
                'channel': message.channel,
                'created_at': message.created_at,
                'attachment_urls': attachment_urls  # Lưu danh sách URL vào cache
            }
            # Giữ cache không quá lớn để tiết kiệm bộ nhớ
            if len(self.message_cache) > 200:
                oldest_keys = list(self.message_cache.keys())[:50]
                for key in oldest_keys:
                    del self.message_cache[key]

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        log_channel = await self.get_log_channel(message.guild.id)
        if not log_channel:
            return

        await asyncio.sleep(1.5)

        deleter = None
        try:
            async for entry in message.guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
                if entry.extra.channel.id == message.channel.id and entry.target.id == message.author.id:
                    if (datetime.datetime.now(datetime.timezone.utc) - entry.created_at).total_seconds() < 5:
                        deleter = entry.user
                        break
        except discord.Forbidden:
            pass

        cached_message = self.message_cache.pop(message.id, None)
        author = message.author
        content = cached_message.get('content') if cached_message else None
        attachment_urls = cached_message.get(
            'attachment_urls', []) if cached_message else []

        action_text = ""
        if deleter and deleter.id != author.id:
            action_text = f"bị xóa bởi **{deleter.mention}**."
        else:
            action_text = f"do **chính họ** xóa."

        embed = discord.Embed(
            description=f"**Tin nhắn của {author.mention} trong {message.channel.mention} {action_text}**",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_author(name=str(author), icon_url=author.display_avatar.url)

        # --- Phần Logic Hiển Thị Mới ---
        has_content_to_log = False
        if content:
            embed.add_field(name="Nội dung văn bản",
                            value=f"```{content[:1020]}```", inline=False)
            has_content_to_log = True

        if attachment_urls:
            # Hiển thị hình ảnh đầu tiên trong embed
            embed.set_image(url=attachment_urls[0])

            # Nếu có nhiều hơn 1 tệp, liệt kê các tệp còn lại
            if len(attachment_urls) > 1:
                other_files = "\n".join(
                    f"[Link tệp {i+2}]({url})" for i, url in enumerate(attachment_urls[1:]))
                embed.add_field(name="Các tệp đính kèm khác",
                                value=other_files, inline=False)
            has_content_to_log = True

        if not has_content_to_log:
            embed.add_field(
                name="Nội dung đã xóa", value="*Không thể truy xuất nội dung (tin nhắn được gửi khi bot offline hoặc quá cũ)*", inline=False)

        embed.set_footer(
            text=f"ID Người Gửi: {author.id} | ID Tin Nhắn: {message.id}")

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"Lỗi khi gửi log tin nhắn bị xóa: {e}")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        log_channel = await self.get_log_channel(before.guild.id)
        if not log_channel:
            return

        embed = discord.Embed(
            description=f"**Tin nhắn được sửa trong {before.channel.mention}** [Nhảy tới tin nhắn]({after.jump_url})",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_author(name=str(before.author),
                         icon_url=before.author.display_avatar.url)
        embed.add_field(name="Trước khi sửa",
                        value=f"```{before.content[:1020]}```", inline=False)
        embed.add_field(name="Sau khi sửa",
                        value=f"```{after.content[:1020]}```", inline=False)
        embed.set_footer(
            text=f"ID Người Gửi: {before.author.id} | ID Tin Nhắn: {before.id}")

        await log_channel.send(embed=embed)

    # --- SỰ KIỆN LOG THÀNH VIÊN ---

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        log_channel = await self.get_log_channel(before.guild.id)
        if not log_channel:
            return

        # Log thay đổi nickname
        if before.display_name != after.display_name:
            embed = discord.Embed(
                description=f"**Nickname của {before.mention} đã thay đổi**",
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_author(
                name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(
                name="Tên cũ", value=before.display_name, inline=True)
            embed.add_field(
                name="Tên mới", value=after.display_name, inline=True)
            embed.set_footer(text=f"User ID: {after.id}")
            await log_channel.send(embed=embed)

        # Log thay đổi vai trò
        if before.roles != after.roles:
            added_roles = [r for r in after.roles if r not in before.roles]
            removed_roles = [r for r in before.roles if r not in after.roles]
            if added_roles or removed_roles:
                embed = discord.Embed(
                    description=f"**Vai trò của {before.mention} đã thay đổi**",
                    color=discord.Color.teal(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.set_author(
                    name=str(after), icon_url=after.display_avatar.url)
                if added_roles:
                    embed.add_field(name="✅ Vai trò đã thêm", value=", ".join(
                        [r.mention for r in added_roles]), inline=False)
                if removed_roles:
                    embed.add_field(name="❌ Vai trò đã xóa", value=", ".join(
                        [r.mention for r in removed_roles]), inline=False)
                embed.set_footer(text=f"User ID: {after.id}")
                await log_channel.send(embed=embed)

    # --- SỰ KIỆN LOG KICK/BAN/UNBAN ---

    # Lưu ý: on_member_remove đã có trong cogs/general.py để thông báo tạm biệt.
    # Để tránh xung đột, chúng ta có thể kiểm tra log kick/ban ở một sự kiện khác hoặc gộp chúng lại.
    # Hiện tại, các lệnh kick/ban của bạn đã tự gửi embed, nên phần log này sẽ tập trung vào hành động thực hiện qua giao diện Discord.

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        log_channel = await self.get_log_channel(guild.id)
        if not log_channel:
            return

        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target == user:
                    moderator = entry.user
                    reason = entry.reason or "Không có lý do."
                    embed = discord.Embed(
                        description=f"🔨 **{user} (`{user.id}`) đã bị cấm khỏi server**",
                        color=discord.Color.dark_red(),
                        timestamp=entry.created_at
                    )
                    embed.set_author(name=str(moderator),
                                     icon_url=moderator.display_avatar.url)
                    embed.add_field(name="Lý do", value=reason, inline=False)
                    await log_channel.send(embed=embed)
                    return
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        log_channel = await self.get_log_channel(guild.id)
        if not log_channel:
            return

        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
                if entry.target == user:
                    moderator = entry.user
                    reason = entry.reason or "Không có lý do."
                    embed = discord.Embed(
                        description=f"♻️ **{user} (`{user.id}`) đã được gỡ cấm**",
                        color=discord.Color.green(),
                        timestamp=entry.created_at
                    )
                    embed.set_author(name=str(moderator),
                                     icon_url=moderator.display_avatar.url)
                    embed.add_field(name="Lý do", value=reason, inline=False)
                    await log_channel.send(embed=embed)
                    return
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(Logger(bot))

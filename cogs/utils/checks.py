# cogs/utils/checks.py
from discord.ext import commands
import discord


def is_administrator():
    """Kiểm tra xem người dùng có phải là Admin không. Nếu không, gửi tin nhắn lỗi."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.author.guild_permissions.administrator:
            # Gửi tin nhắn tạm thời và trả về False để dừng lệnh
            await ctx.send("❌ Lệnh này yêu cầu quyền **Administrator**.", ephemeral=True, delete_after=10)
            return False
        return True
    return commands.check(predicate)


def has_permissions(**perms):
    """
    Phiên bản tùy chỉnh của commands.has_permissions.
    Thay vì ẩn lệnh, nó sẽ gửi tin nhắn lỗi khi người dùng không có quyền.
    """
    original_check = commands.has_permissions(**perms).predicate

    async def predicate(ctx: commands.Context) -> bool:
        try:
            # Thử chạy check gốc
            if await original_check(ctx):
                return True
            # Nếu check gốc thất bại (trả về False)
            missing_perms = [perm.replace('_', ' ').replace(
                'guild', 'server').title() for perm, value in perms.items() if value]
            await ctx.send(f"❌ Bạn thiếu quyền: **{', '.join(missing_perms)}**.", ephemeral=True, delete_after=10)
            return False
        except commands.MissingPermissions as e:
            # Xử lý trường hợp check gốc raise lỗi
            missing_perms = [perm.replace('_', ' ').replace(
                'guild', 'server').title() for perm in e.missing_permissions]
            await ctx.send(f"❌ Bạn thiếu quyền: **{', '.join(missing_perms)}**.", ephemeral=True, delete_after=10)
            return False
    return commands.check(predicate)

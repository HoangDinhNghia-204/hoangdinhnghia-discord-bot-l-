# bot.py
import discord
from discord.ext import commands
import os
import asyncio
import datetime
from dotenv import load_dotenv
import database as db

# --- CẤU HÌNH BAN ĐẦU ---
load_dotenv()
BOT_TOKEN = os.getenv('COMMUNITY_BOT_TOKEN')

if not BOT_TOKEN:
    print("Lỗi: Không tìm thấy biến COMMUNITY_BOT_TOKEN trong file .env của bạn.")
    exit()

# --- TẠO LỚP BOT TÙY CHỈNH ĐỂ DÙNG setup_hook ---


class CommunityBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # Đây là nơi hoàn hảo để tải cogs và đồng bộ lệnh.
        # Nó sẽ chạy sau khi bot đăng nhập nhưng trước on_ready.

        # 1. Tải tất cả các cogs
        print("--- Bắt đầu tải Cogs ---")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f'✅ Đã tải thành công: {filename}')
                except Exception as e:
                    print(f'❌ Lỗi khi tải {filename}: {e}')
        print("--- Tải Cogs hoàn tất ---")

        # 2. Đồng bộ lệnh cho từng server sau khi đã tải cogs
        print("--- Bắt đầu đồng bộ lệnh ---")
        for guild in self.guilds:
            try:
                synced = await self.tree.sync(guild=guild)
                print(
                    f"Đã đồng bộ {len(synced)} lệnh cho server: {guild.name} (ID: {guild.id})")
            except Exception as e:
                print(f"Lỗi khi đồng bộ lệnh cho server {guild.name}: {e}")
        print("--- Đồng bộ lệnh hoàn tất ---")


# --- THIẾT LẬP BOT ---
intents = discord.Intents.all()
# Sử dụng lớp CommunityBot mà chúng ta vừa tạo
bot = CommunityBot(command_prefix='?', intents=intents, help_command=None)


# --- SỰ KIỆN TOÀN CỤC (GLOBAL EVENTS) ---

@bot.event
async def on_ready():
    """Sự kiện được kích hoạt sau khi setup_hook đã chạy xong."""
    print(f'Bot đã đăng nhập với tên: {bot.user}')
    db.init_db()
    await bot.change_presence(activity=discord.Game(name="/help để xem mọi thứ"))
    print("Bot đã sẵn sàng!")


@bot.before_invoke
async def cleanup_command_message(ctx):
    """Luôn luôn tự động xóa tin nhắn gọi lệnh của người dùng."""
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass


@bot.event
async def on_command_error(ctx, error):
    """Xử lý các lỗi xảy ra khi dùng lệnh."""
    try:
        if ctx.message:
            await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    error_map = {
        commands.MissingRequiredArgument: f"Lệnh thiếu tham số. Gõ `{bot.command_prefix}help {ctx.command.name}` để xem cách dùng.",
        commands.MissingPermissions: "Bạn không có quyền để sử dụng lệnh này.",
        commands.BotMissingPermissions: f"Bot thiếu quyền: `{' '.join(error.missing_permissions)}`" if isinstance(error, commands.BotMissingPermissions) else "Bot thiếu quyền.",
        commands.CommandOnCooldown: f"Hôm nay bạn đã nhận thưởng rồi, hãy quay lại sau **{datetime.timedelta(seconds=int(error.retry_after))}**." if isinstance(
            error, commands.CommandOnCooldown) else "Lệnh đang hồi."
    }

    error_message = error_map.get(type(error))

    if error_message:
        await ctx.send(f"❌ {error_message}", delete_after=10)
    elif not isinstance(error, commands.CommandNotFound):
        print(f"Lỗi không xác định trong lệnh '{ctx.command}': {error}")
        await ctx.send("❌ Đã có lỗi xảy ra khi thực thi lệnh.", delete_after=10)

# --- HÀM MAIN ĐỂ CHẠY BOT ---


async def main():
    async with bot:
        # Chúng ta không cần gọi load_cogs() ở đây nữa vì nó đã được chuyển vào setup_hook
        await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot đang tắt...")


# # bot.py
# import discord
# from discord.ext import commands
# import os
# import asyncio
# import datetime
# from dotenv import load_dotenv
# import database as db
# from typing import Literal, Optional

# # --- CẤU HÌNH BAN ĐẦU ---
# load_dotenv()
# BOT_TOKEN = os.getenv('COMMUNITY_BOT_TOKEN')

# if not BOT_TOKEN:
#     print("Lỗi: Không tìm thấy biến COMMUNITY_BOT_TOKEN trong file .env của bạn.")
#     exit()

# # --- TẠO LỚP BOT TÙY CHỈNH ĐỂ DÙNG setup_hook ---


# class CommunityBot(commands.Bot):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#     async def setup_hook(self):
#         # 1. Tải tất cả các cogs
#         print("--- Bắt đầu tải Cogs ---")
#         for filename in os.listdir('./cogs'):
#             if filename.endswith('.py') and not filename.startswith('__'):
#                 try:
#                     await self.load_extension(f'cogs.{filename[:-3]}')
#                     print(f'✅ Đã tải thành công: {filename}')
#                 except Exception as e:
#                     print(f'❌ Lỗi khi tải {filename}: {e}')
#         print("--- Tải Cogs hoàn tất ---")

#         # <<< SỬA LỖI TẠI ĐÂY: Đồng bộ toàn cục 1 lần duy nhất >>>
#         # Cách này đáng tin cậy hơn là lặp qua từng guild
#         try:
#             print("--- Bắt đầu đồng bộ lệnh toàn cục ---")
#             synced = await self.tree.sync()
#             print(f"Đã đồng bộ {len(synced)} lệnh slash ra toàn cục.")
#         except Exception as e:
#             print(f"Lỗi khi đồng bộ lệnh toàn cục: {e}")
#         print("--- Đồng bộ lệnh hoàn tất ---")


# # --- THIẾT LẬP BOT ---
# intents = discord.Intents.all()
# bot = CommunityBot(command_prefix='?', intents=intents, help_command=None)


# # --- SỰ KIỆN TOÀN CỤC (GLOBAL EVENTS) ---

# @bot.event
# async def on_ready():
#     """Sự kiện được kích hoạt sau khi setup_hook đã chạy xong."""
#     print(f'Bot đã đăng nhập với tên: {bot.user}')
#     db.init_db()
#     await bot.change_presence(activity=discord.Game(name="?help để xem mọi thứ"))
#     print("Bot đã sẵn sàng!")

# # <<< LỆNH SYNC MỚI, MẠNH MẼ HƠN >>>


# @bot.command()
# @commands.guild_only()
# @commands.is_owner()
# async def sync(
#         ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
#     if not guilds:
#         if spec == "~":
#             synced = await ctx.bot.tree.sync(guild=None)
#         elif spec == "*":
#             ctx.bot.tree.copy_global_to(guild=ctx.guild)
#             synced = await ctx.bot.tree.sync(guild=ctx.guild)
#         elif spec == "^":
#             ctx.bot.tree.clear_commands(guild=ctx.guild)
#             await ctx.bot.tree.sync(guild=ctx.guild)
#             synced = []
#         else:
#             synced = await ctx.bot.tree.sync(guild=ctx.guild)

#         await ctx.send(
#             f"Đã đồng bộ {len(synced)} lệnh {'toàn cục' if spec == '~' else 'cho server này.'}"
#         )
#         return

#     ret = 0
#     for guild in guilds:
#         try:
#             await ctx.bot.tree.sync(guild=guild)
#         except discord.HTTPException:
#             pass
#         else:
#             ret += 1

#     await ctx.send(f"Đã đồng bộ lệnh cho {ret}/{len(guilds)} server.")


# @bot.before_invoke
# async def cleanup_command_message(ctx):
#     """Luôn luôn tự động xóa tin nhắn gọi lệnh của người dùng."""
#     try:
#         if ctx.message:  # Chỉ xóa nếu là lệnh prefix
#             await ctx.message.delete()
#     except (discord.Forbidden, discord.NotFound):
#         pass


# @bot.event
# async def on_command_error(ctx, error):
#     """Xử lý các lỗi xảy ra khi dùng lệnh."""
#     if isinstance(ctx, discord.Interaction):  # Bỏ qua xử lý lỗi cho slash command
#         return

#     try:
#         if ctx.message:
#             await ctx.message.delete()
#     except (discord.Forbidden, discord.NotFound):
#         pass

#     error_map = {
#         commands.MissingRequiredArgument: f"Lệnh thiếu tham số. Gõ `{bot.command_prefix}help {ctx.command.name}` để xem cách dùng.",
#         commands.MissingPermissions: "Bạn không có quyền để sử dụng lệnh này.",
#         commands.BotMissingPermissions: f"Bot thiếu quyền: `{' '.join(error.missing_permissions)}`" if isinstance(error, commands.BotMissingPermissions) else "Bot thiếu quyền.",
#         commands.CommandOnCooldown: f"Lệnh đang hồi. Vui lòng thử lại sau {error.retry_after:.2f} giây."
#     }

#     error_message = error_map.get(type(error))

#     if error_message:
#         await ctx.send(f"❌ {error_message}", delete_after=10)
#     elif not isinstance(error, commands.CommandNotFound):
#         print(f"Lỗi không xác định trong lệnh '{ctx.command}': {error}")
#         await ctx.send("❌ Đã có lỗi xảy ra khi thực thi lệnh.", delete_after=10)

# # --- HÀM MAIN ĐỂ CHẠY BOT ---


# async def main():
#     async with bot:
#         await bot.start(BOT_TOKEN)

# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         print("Bot đang tắt...")
